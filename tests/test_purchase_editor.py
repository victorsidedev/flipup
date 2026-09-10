import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from database import Base
from models.item import Item
from models.purchase import Purchase
from models.sale import Sale
from schemas.purchase import CreatePurchaseRequest, SavePurchaseRequest
from schemas.sale import CreateSaleRequest
from services.delete_service import delete_item, delete_purchase
from services.purchase_service import create_purchase, get_purchase, update_purchase
from services.sale_service import create_sale


class PurchaseEditorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        event.listen(self.engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        request = CreatePurchaseRequest.model_validate({
            'purchase': {'source': 'Shop', 'purchaseDate': '2026-09-07'},
            'items': [
                {'id': 'cooler', 'name': 'Cooler', 'price': '5', 'parentId': 'gpu'},
                {'id': 'pc', 'name': 'PC', 'price': '100'},
                {'id': 'gpu', 'name': 'GPU', 'price': '20', 'parentId': 'pc'},
                {'id': 'tv', 'name': 'TV', 'price': '50'},
            ],
        })
        purchase, self.ids = create_purchase(self.db, request)
        self.purchase_id = purchase.id
        other = Purchase(source='Other shop')
        self.db.add(other)
        self.db.flush()
        self.other = Item(name='Other item', purchase_id=other.id)
        self.db.add(self.other)
        self.db.commit()
        self.other_id = self.other.id
        self.other_purchase_id = other.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def payload(self):
        result = get_purchase(self.db, self.purchase_id)
        return {
            'purchase': {'source': result.purchase.source, 'purchaseDate': result.purchase.purchaseDate},
            'items': [{'id': str(item.id), 'itemId': item.id, 'name': item.name, 'price': item.price,
                       'parentId': str(item.parentId) if item.parentId else None} for item in result.items],
        }

    def test_update_retains_ids_and_sale_and_can_add_nested_items(self):
        create_sale(self.db, CreateSaleRequest(itemId=self.ids['tv'], price='60'))
        payload = self.payload()
        payload['purchase']['source'] = 'Updated shop'
        payload['items'][0]['name'] = 'Updated name'
        payload['items'].insert(0, {'id': 'new', 'name': 'Fan', 'price': '2', 'parentId': str(self.ids['gpu'])})
        result = update_purchase(self.db, self.purchase_id, SavePurchaseRequest.model_validate(payload))
        self.assertEqual(result.purchase.source, 'Updated shop')
        self.assertEqual(len(result.items), 5)
        self.assertTrue(set(self.ids.values()).issubset({item.id for item in result.items}))
        self.assertIsNotNone(self.db.query(Sale).filter_by(item_id=self.ids['tv']).first())
        self.assertEqual(next(item for item in result.items if item.name == 'Fan').parentId, self.ids['gpu'])

    def test_delete_parent_with_sales_refused(self):
        create_sale(self.db, CreateSaleRequest(itemId=self.ids['cooler'], price='10'))
        with self.assertRaises(HTTPException) as error:
            delete_item(self.db, self.ids['pc'])
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.query(Item).count(), 5)
        self.assertEqual(self.db.query(Sale).count(), 1)

    def test_delete_purchase_with_sales_refused(self):
        create_sale(self.db, CreateSaleRequest(itemId=self.ids['pc'], price='150'))
        with self.assertRaises(HTTPException) as error:
            delete_purchase(self.db, self.purchase_id)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIsNotNone(self.db.get(Purchase, self.purchase_id))

    def test_delete_unsold_parent_removes_subtree(self):
        result = delete_item(self.db, self.ids['pc'])
        self.assertEqual([item.id for item in result.items], [self.ids['tv']])
        self.assertIsNotNone(self.db.get(Item, self.other_id))

    def test_delete_unsold_purchase_removes_items(self):
        delete_purchase(self.db, self.purchase_id)
        self.assertIsNone(self.db.get(Purchase, self.purchase_id))
        self.assertEqual([item.id for item in self.db.query(Item)], [self.other_id])

    def test_delete_failure_rolls_back_items(self):
        with patch.object(self.db, 'commit', side_effect=RuntimeError('Failed commit')):
            with self.assertRaises(RuntimeError):
                delete_purchase(self.db, self.purchase_id)
        self.assertEqual(self.db.query(Item).count(), 5)
        self.assertIsNotNone(self.db.get(Purchase, self.purchase_id))

    def test_missing_deletes_return_not_found(self):
        for action in [delete_item, delete_purchase]:
            with self.assertRaises(HTTPException) as error:
                action(self.db, 999999)
            self.assertEqual(error.exception.status_code, 404)

    def test_stale_or_foreign_item_updates_are_rejected(self):
        payload = self.payload()
        payload['items'][0]['itemId'] = self.other_id
        with self.assertRaises(HTTPException) as error:
            update_purchase(self.db, self.purchase_id, SavePurchaseRequest.model_validate(payload))
        self.assertEqual(error.exception.status_code, 409)
        payload = self.payload()
        payload['items'].pop()
        with self.assertRaises(HTTPException):
            update_purchase(self.db, self.purchase_id, SavePurchaseRequest.model_validate(payload))
        self.assertEqual(self.db.query(Item).count(), 5)

    def test_parent_cycles_rejected(self):
        with self.assertRaises(ValidationError):
            CreatePurchaseRequest.model_validate({
                'purchase': {'source': 'Shop', 'purchaseDate': None},
                'items': [{'id': 'a', 'name': 'A', 'parentId': 'b'}, {'id': 'b', 'name': 'B', 'parentId': 'a'}],
            })
