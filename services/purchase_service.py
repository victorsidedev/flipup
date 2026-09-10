from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.purchase import Purchase
from models.item import Item
from models.sale import Sale
from models.refund import Refund
from schemas.sale import SaleResponse
from services.item_status import find_sale_source
from schemas.purchase import (
    CreatePurchaseRequest,
    SavePurchaseRequest,
    PurchaseWithItemsResponse,
    PurchaseResponse,
    ItemResponse,
)


def get_sales_by_item(db: Session) -> dict[int, SaleResponse]:
    return {
        sale.item_id: SaleResponse(
            id=sale.id, itemId=sale.item_id, price=sale.price,
            kind=sale.kind, soldAt=sale.sold_at,
        )
        for sale in db.query(Sale).filter(
            ~db.query(Refund).filter(Refund.sale_id == Sale.id).exists()
        )
    }


def build_purchase_response(
    purchase: Purchase, sales: dict[int, SaleResponse]
) -> PurchaseWithItemsResponse:
    by_id = {item.id: item for item in purchase.items}
    items = []
    for item in purchase.items:
        sale_source = find_sale_source(item.id, by_id, sales)
        direct_sale = sales.get(item.id)
        status = "sold" if direct_sale else "included" if sale_source is not None else "available"
        items.append(ItemResponse(
            id=item.id,
            name=item.name,
            price=item.price,
            parentId=item.parent_item_id,
            purchaseId=item.purchase_id,
            sale=direct_sale,
            status=status,
            soldWithItemId=sale_source if status == "included" else None,
        ))
    return PurchaseWithItemsResponse(
        purchase=PurchaseResponse(
            id=purchase.id,
            source=purchase.source,
            purchaseDate=purchase.purchased_date,
        ),
        items=items,
    )


def get_purchases(db: Session) -> list[PurchaseWithItemsResponse]:
    sales = get_sales_by_item(db)
    return [build_purchase_response(purchase, sales) for purchase in db.query(Purchase).all()]


def get_purchase(db: Session, purchase_id: int) -> PurchaseWithItemsResponse:
    purchase = db.get(Purchase, purchase_id)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return build_purchase_response(purchase, get_sales_by_item(db))


def write_items(db: Session, purchase: Purchase, requests, existing: dict[int, Item]):
    """Resolve any input order while retaining database IDs of existing items."""
    pending = list(requests)
    id_map = {}
    while pending:
        ready = [item for item in pending if item.parentId is None or item.parentId in id_map]
        if not ready:
            raise HTTPException(status_code=422, detail="Invalid item hierarchy")
        for request in ready:
            parent_id = id_map.get(request.parentId)
            item = existing.get(request.itemId)
            if item is None:
                item = Item(purchase_id=purchase.id, parent_item_id=parent_id)
                db.add(item)
            item.name = request.name
            item.price = request.price
            db.flush()
            id_map[request.id] = item.id
            pending.remove(request)
    return id_map


def create_purchase(db: Session, request: CreatePurchaseRequest):
    try:
        if any(item.itemId is not None for item in request.items):
            raise HTTPException(status_code=422, detail="New purchases cannot contain existing items")
        purchase = Purchase(source=request.purchase.source, purchased_date=request.purchase.purchaseDate)
        db.add(purchase)
        db.flush()
        id_map = write_items(db, purchase, request.items, {})
        db.commit()
        return purchase, id_map
    except Exception:
        db.rollback()
        raise


def update_purchase(db: Session, purchase_id: int, request: SavePurchaseRequest):
    try:
        purchase = db.get(Purchase, purchase_id, with_for_update=True)
        if purchase is None:
            raise HTTPException(status_code=404, detail="Purchase not found")
        existing = {item.id: item for item in purchase.items}
        requested_ids = {item.itemId for item in request.items if item.itemId is not None}
        if requested_ids != set(existing):
            raise HTTPException(status_code=409, detail="Items changed. Reopen this purchase before saving. Use Delete to remove items.")
        by_id = {item.id: item for item in request.items}
        sales = get_sales_by_item(db)
        for item in request.items:
            parent = by_id.get(item.parentId)
            parent_db_id = parent.itemId if parent else None
            if item.itemId is not None:
                if existing[item.itemId].parent_item_id != parent_db_id or (parent and parent.itemId is None):
                    raise HTTPException(status_code=422, detail="Existing items cannot be moved to another parent")
            else:
                ancestor = parent
                while ancestor is not None and ancestor.itemId is None:
                    ancestor = by_id.get(ancestor.parentId)
                if ancestor is not None and find_sale_source(ancestor.itemId, existing, sales) is not None:
                    raise HTTPException(status_code=409, detail="Cannot add parts to an item that is already sold")
        purchase.source = request.purchase.source
        purchase.purchased_date = request.purchase.purchaseDate
        write_items(db, purchase, request.items, existing)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_purchase(db, purchase_id)
