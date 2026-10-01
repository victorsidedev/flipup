import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from database import Base
from models.item import Item
from models.purchase import Purchase
from models.sale import Sale
from models.sale_item import SaleItem
from models.sale_expense import SaleExpense
from routes.sale_routes import create_sale
from schemas.sale import CreateSaleRequest
from services.purchase_service import get_purchases
from services.refund_service import refund_sale


class MultiPurchaseSalesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        event.listen(self.engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([Purchase(id=1, source='A'), Purchase(id=2, source='B')])
        self.db.flush()
        self.db.add_all([
            Item(id=1, purchase_id=1, name='Parent A'),
            Item(id=4, purchase_id=1, name='Parent B'),
            Item(id=6, purchase_id=2, name='Parent C'),
        ])
        self.db.flush()
        self.db.add_all([
            Item(id=2, purchase_id=1, parent_item_id=1, name='Child A'),
            Item(id=5, purchase_id=1, parent_item_id=4, name='Child B'),
            Item(id=7, purchase_id=2, parent_item_id=6, name='Child C'),
        ])
        self.db.flush()
        self.db.add(Item(id=3, purchase_id=1, parent_item_id=2, name='Grandchild A'))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sell(self, *ids, **kwargs):
        return create_sale(CreateSaleRequest(items=[{'itemId': i} for i in ids], price='100', **kwargs), self.db)

    def test_cross_purchase_sale_preserves_allocations_expenses_and_response(self):
        result = create_sale(CreateSaleRequest(
            items=[{'itemId': 7, 'allocatedPrice': '40'}, {'itemId': 2, 'allocatedPrice': '60'}],
            price='100', expenses=[{'type': 'shipping_fee', 'amount': '5', 'itemId': 7}],
        ), self.db)
        self.assertEqual(result.purchase.id, 2)
        sale = self.db.query(Sale).one()
        self.assertEqual(sale.item_id, 7)
        self.assertEqual(sale.price, Decimal('100'))
        self.assertEqual({row.item_id: row.allocated_price for row in self.db.query(SaleItem)},
                         {7: Decimal('40'), 2: Decimal('60'), 3: None})
        self.assertEqual(self.db.query(SaleExpense).one().item_id, 7)
        with Session(self.engine) as fresh_db:
            inventory = {item.id: item for purchase in get_purchases(fresh_db) for item in purchase.items}
            self.assertEqual({i for i, item in inventory.items() if item.status == 'sold'}, {2, 3, 7})
            self.assertEqual({inventory[i].sale.id for i in [2, 3, 7]}, {sale.id})
        refund_sale(self.db, sale.id)
        self.assertTrue(all(item.status == 'available' for p in get_purchases(self.db) for item in p.items))

    def test_items_from_different_parents_in_same_purchase(self):
        self.sell(2, 5)
        self.assertEqual({row.item_id for row in self.db.query(SaleItem)}, {2, 3, 5})

    def test_parent_subtrees_across_purchases_are_deduplicated(self):
        self.sell(1, 2, 6)
        self.assertEqual({row.item_id for row in self.db.query(SaleItem)}, {1, 2, 3, 6, 7})
        self.assertEqual(self.db.query(Sale).count(), 1)

    def test_sold_descendant_in_other_purchase_rejects_entire_sale(self):
        self.sell(7)
        with self.assertRaises(HTTPException) as error:
            self.sell(1, 6)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Sale).count(), 1)
        self.assertEqual({row.item_id for row in self.db.query(SaleItem)}, {7})

    def test_missing_item_rejects_entire_sale(self):
        with self.assertRaises(HTTPException) as error:
            self.sell(2, 7, 999)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.db.query(Sale).count(), 0)

    def test_failed_commit_rolls_back_all_purchases(self):
        with patch.object(self.db, 'commit', side_effect=RuntimeError('Failed')):
            with self.assertRaises(RuntimeError):
                self.sell(1, 6, expenses=[{'type': 'payment_fee', 'amount': '2'}])
        for model in [Sale, SaleItem, SaleExpense]:
            self.assertEqual(self.db.query(model).count(), 0)
