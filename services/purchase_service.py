from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.purchase import Purchase
from models.item import Item
from models.sale import Sale
from models.sale_item import SaleItem
from models.sale_expense import SaleExpense
from models.refund import Refund
from schemas.sale import SaleResponse, SaleItemResponse, SaleExpenseResponse
from schemas.purchase import (
    CreatePurchaseRequest,
    SavePurchaseRequest,
    PurchaseWithItemsResponse,
    PurchaseResponse,
    ItemResponse,
)


def get_sales_by_item(db: Session) -> dict[int, SaleResponse]:
    active_sales = {
        sale.id: sale
        for sale in db.query(Sale).filter(
            ~db.query(Refund).filter(Refund.sale_id == Sale.id).exists()
        )
    }

    items_by_sale = defaultdict(list)
    for sale_item in db.query(SaleItem).filter(SaleItem.sale_id.in_(active_sales)):
        items_by_sale[sale_item.sale_id].append(
            SaleItemResponse(itemId=sale_item.item_id, allocatedPrice=sale_item.allocated_price)
        )

    expenses_by_sale = defaultdict(list)
    for expense in db.query(SaleExpense).filter(SaleExpense.sale_id.in_(active_sales)):
        expenses_by_sale[expense.sale_id].append(
            SaleExpenseResponse(
                id=expense.id,
                type=expense.type,
                amount=expense.amount,
                description=expense.description,
                itemId=expense.item_id,
            )
        )

    by_item = {}
    for sale in active_sales.values():
        response = SaleResponse(
            id=sale.id,
            kind=sale.kind,
            soldAt=sale.sold_at,
            price=sale.price,
            items=items_by_sale[sale.id],
            expenses=expenses_by_sale[sale.id],
        )
        for sale_item in items_by_sale[sale.id]:
            by_item[sale_item.itemId] = response
    return by_item


def build_purchase_response(
    purchase: Purchase, sales: dict[int, SaleResponse]
) -> PurchaseWithItemsResponse:
    items = []
    for item in purchase.items:
        sale = sales.get(item.id)
        items.append(ItemResponse(
            id=item.id,
            name=item.name,
            price=item.price,
            parentId=item.parent_item_id,
            purchaseId=item.purchase_id,
            sale=sale,
            status="sold" if sale else "available",
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
                if ancestor is not None and ancestor.itemId in sales:
                    raise HTTPException(status_code=409, detail="Cannot add parts to an item that is already sold")
        purchase.source = request.purchase.source
        purchase.purchased_date = request.purchase.purchaseDate
        write_items(db, purchase, request.items, existing)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_purchase(db, purchase_id)
