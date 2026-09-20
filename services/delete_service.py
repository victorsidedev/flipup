from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from models.item import Item
from models.purchase import Purchase
from models.sale_item import SaleItem
from services.purchase_service import get_purchase


def subtree_ids(db: Session, item: Item) -> set[int]:
    children = defaultdict(list)
    for child_id, parent_id in db.query(Item.id, Item.parent_item_id):
        children[parent_id].append(child_id)
    pending = [item.id]
    result = set()
    while pending:
        item_id = pending.pop()
        if item_id not in result:
            result.add(item_id)
            pending.extend(children[item_id])
    return result


def remove_items(db: Session, item_ids: set[int]):
    if db.query(SaleItem.item_id).filter(SaleItem.item_id.in_(item_ids)).first() is not None:
        raise HTTPException(status_code=409, detail="Items with sales history cannot be deleted")
    db.execute(delete(Item).where(Item.id.in_(item_ids)))


def delete_item(db: Session, item_id: int):
    try:
        item = db.get(Item, item_id, with_for_update=True)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        purchase_id = item.purchase_id
        remove_items(db, subtree_ids(db, item))
        db.commit()
        db.expire_all()
    except Exception:
        db.rollback()
        raise
    return get_purchase(db, purchase_id)


def delete_purchase(db: Session, purchase_id: int):
    try:
        purchase = db.get(Purchase, purchase_id, with_for_update=True)
        if purchase is None:
            raise HTTPException(status_code=404, detail="Purchase not found")
        item_ids = {row.id for row in db.query(Item.id).filter(Item.purchase_id == purchase_id)}
        remove_items(db, item_ids)
        db.execute(delete(Purchase).where(Purchase.id == purchase_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
