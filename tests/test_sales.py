import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from database import Base
from models.item import Item
from models.purchase import Purchase
from models.sale import Sale
from models.refund import Refund
from services.refund_service import refund_sale
from services.delete_service import delete_item, delete_purchase
from schemas.sale import CreateSaleRequest
from services.purchase_service import get_purchases
from services.sale_service import create_sale


class SalesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([Purchase(id=1, source="Shop"), Purchase(id=2, source="Other shop")])
        self.db.flush()
        self.db.add_all([
            Item(id=1, name="PC", price=100, purchase_id=1),
            Item(id=2, name="GPU", price=20, purchase_id=1, parent_item_id=1),
            Item(id=3, name="Cooler", price=5, purchase_id=1, parent_item_id=2),
            Item(id=4, name="TV", price=50, purchase_id=1),
            Item(id=5, name="Other PC", price=100, purchase_id=2),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_parent_sale_keeps_items_and_counts_price_once(self):
        result = create_sale(self.db, CreateSaleRequest(itemId=1, price="150.25"))
        items = {item.id: item for item in result.items}
        self.assertEqual(len(items), 4)
        self.assertEqual(items[1].status, "sold")
        self.assertEqual(items[1].sale.price, Decimal("150.25"))
        for item_id in [2, 3]:
            self.assertEqual(items[item_id].status, "included")
            self.assertEqual(items[item_id].soldWithItemId, 1)
            self.assertIsNone(items[item_id].sale)
        self.assertEqual(items[4].status, "available")
        with Session(self.engine) as fresh_db:
            purchases = get_purchases(fresh_db)
            self.assertEqual(purchases[0], result)
            self.assertEqual(purchases[1].items[0].status, "available")
            self.assertEqual(fresh_db.query(Item).count(), 5)
            self.assertEqual(sum(sale.price for sale in fresh_db.query(Sale)), Decimal("150.25"))
        self.assertEqual({column['name'] for column in inspect(self.engine).get_columns('sales')}, {'id', 'item_id', 'price', 'kind', 'sold_at'})

    def test_selling_intermediate_parent_only_covers_its_subtree(self):
        result = create_sale(self.db, CreateSaleRequest(itemId=2, price="25"))
        items = {item.id: item for item in result.items}
        self.assertEqual(items[1].status, "available")
        self.assertEqual(items[2].status, "sold")
        self.assertEqual(items[3].status, "included")
        self.assertEqual(items[3].soldWithItemId, 2)
        self.assertEqual(items[4].status, "available")

    def test_leaf_sale_leaves_ancestors_available(self):
        result = create_sale(self.db, CreateSaleRequest(itemId=3, price="0"))
        self.assertEqual([item.status for item in result.items], ["available", "available", "sold", "available"])

    def test_direct_and_inherited_duplicates_and_missing_items_rejected(self):
        create_sale(self.db, CreateSaleRequest(itemId=1, price="100"))
        for item_id, status in [(1, 409), (2, 409), (3, 409), (999, 404)]:
            with self.assertRaises(HTTPException) as caught:
                create_sale(self.db, CreateSaleRequest(itemId=item_id, price="10"))
            self.assertEqual(caught.exception.status_code, status)
        self.assertEqual(self.db.query(Sale).count(), 1)

    def test_prior_child_sale_is_preserved_when_parent_is_sold(self):
        create_sale(self.db, CreateSaleRequest(itemId=2, price="20"))
        result = create_sale(self.db, CreateSaleRequest(itemId=1, price="100"))
        items = {item.id: item for item in result.items}
        self.assertEqual(items[2].status, "sold")
        self.assertEqual(items[2].sale.price, Decimal("20"))
        self.assertEqual(items[3].soldWithItemId, 2)
        self.assertEqual(self.db.query(Sale).count(), 2)

    def test_failed_save_leaves_no_sale_or_derived_status(self):
        with patch.object(self.db, "commit", side_effect=RuntimeError("Commit failed")):
            with self.assertRaises(RuntimeError):
                create_sale(self.db, CreateSaleRequest(itemId=1, price="100"))
        self.assertEqual(self.db.query(Sale).count(), 0)
        self.assertTrue(all(item.status == "available" for group in get_purchases(self.db) for item in group.items))

    def test_refund_releases_subtree_and_resale_preserves_history(self):
        original = create_sale(self.db, CreateSaleRequest(itemId=1, price="100")).items[0].sale
        result = refund_sale(self.db, original.id)
        self.assertTrue(all(item.status == "available" for item in result.items))
        self.assertTrue(all(item.sale is None for item in result.items))
        resale = create_sale(self.db, CreateSaleRequest(itemId=1, price="120")).items[0].sale
        self.assertNotEqual(original.id, resale.id)
        self.assertEqual(resale.kind, "sale")
        self.assertIsNotNone(resale.soldAt)
        self.assertEqual(self.db.query(Sale).count(), 2)
        self.assertEqual(self.db.get(Sale, original.id).price, Decimal("100"))
        refund = self.db.query(Refund).one()
        self.assertEqual(refund.amount, Decimal("100"))
        self.assertIsNotNone(refund.refunded_at)
        with self.assertRaises(HTTPException) as error:
            create_sale(self.db, CreateSaleRequest(itemId=1, price="130"))
        self.assertEqual(error.exception.status_code, 409)

    def test_refund_does_not_override_an_active_ancestor(self):
        child = create_sale(self.db, CreateSaleRequest(itemId=2, price="20")).items[1].sale
        create_sale(self.db, CreateSaleRequest(itemId=1, price="100"))
        items = {item.id: item for item in refund_sale(self.db, child.id).items}
        self.assertEqual(items[2].status, "included")
        self.assertEqual(items[3].soldWithItemId, 1)

    def test_refund_missing_duplicate_and_zero_price(self):
        sale = create_sale(self.db, CreateSaleRequest(itemId=1, price="100")).items[0].sale
        refund_sale(self.db, sale.id)
        zero = create_sale(self.db, CreateSaleRequest(itemId=4, price="0")).items[3].sale
        for sale_id, status in [(sale.id, 409), (999, 404), (zero.id, 409)]:
            with self.assertRaises(HTTPException) as error:
                refund_sale(self.db, sale_id)
            self.assertEqual(error.exception.status_code, status)
        self.assertEqual(self.db.query(Refund).count(), 1)

    def test_failed_refund_rolls_back(self):
        sale = create_sale(self.db, CreateSaleRequest(itemId=1, price="100")).items[0].sale
        with patch.object(self.db, "commit", side_effect=RuntimeError("Failed")):
            with self.assertRaises(RuntimeError):
                refund_sale(self.db, sale.id)
        self.assertEqual(self.db.query(Refund).count(), 0)
        self.assertEqual(get_purchases(self.db)[0].items[0].status, "sold")

    def test_refunded_history_blocks_item_subtree_and_purchase_deletion(self):
        sale = create_sale(self.db, CreateSaleRequest(itemId=2, price="20")).items[1].sale
        refund_sale(self.db, sale.id)
        for action, target in [(delete_item, 2), (delete_item, 1), (delete_purchase, 1)]:
            with self.assertRaises(HTTPException) as error:
                action(self.db, target)
            self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Item).count(), 5)
        self.assertEqual(self.db.query(Sale).count(), 1)
        self.assertEqual(self.db.query(Refund).count(), 1)

    def test_loss_kind_marks_item_sold_independent_of_price(self):
        result = create_sale(self.db, CreateSaleRequest(itemId=1, price="100", kind="loss"))
        self.assertEqual(result.items[0].status, "sold")
        self.assertEqual(result.items[0].sale.kind, "loss")
        self.assertEqual(result.items[1].status, "included")
        with self.assertRaises(ValidationError):
            CreateSaleRequest(itemId=4, price="10", kind="invalid")

    def test_selected_sale_date_is_persisted_and_returned(self):
        result = create_sale(self.db, CreateSaleRequest(itemId=1, price="100", soldDate="2025-12-31"))
        sale = result.items[0].sale
        self.assertEqual(sale.soldAt, datetime(2025, 12, 31))
        with Session(self.engine) as fresh_db:
            self.assertEqual(fresh_db.get(Sale, sale.id).sold_at, datetime(2025, 12, 31))
            self.assertEqual(get_purchases(fresh_db)[0].items[0].sale.soldAt, sale.soldAt)

    def test_invalid_sale_dates_rejected(self):
        for value in ["2025-02-29", "not-a-date", ""]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CreateSaleRequest(itemId=1, price="100", soldDate=value)

    def test_invalid_prices_rejected(self):
        for price in ['-1', '1.001', '100000000', 'NaN', 'Infinity', '']:
            with self.subTest(price=price), self.assertRaises(ValidationError):
                CreateSaleRequest(itemId=1, price=price)


if __name__ == '__main__':
    unittest.main()
