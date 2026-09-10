from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.item import Item
from models.sale import Sale
from schemas.purchase import PurchaseWithItemsResponse
from schemas.sale import CreateSaleRequest
from services.item_status import find_sale_source
from services.purchase_service import get_purchase, get_sales_by_item


def create_sale(db: Session, request: CreateSaleRequest) -> PurchaseWithItemsResponse:
    try:
        # Lock the item row so concurrent sales see the latest state
        # before deciding whether the item is still available.
        item = db.get(Item, request.itemId, with_for_update=True)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        purchase_items = {candidate.id: candidate for candidate in db.query(Item).filter(
            Item.purchase_id == item.purchase_id
        )}
        sale_source = find_sale_source(item.id, purchase_items, get_sales_by_item(db))
        if sale_source is not None:
            detail = "This item is already sold" if sale_source == item.id else f"This item is included in the sale of item #{sale_source}"
            raise HTTPException(status_code=409, detail=detail)

        purchase_id = item.purchase_id
        sale = Sale(item_id=item.id, price=request.price, kind=request.kind)
        if request.soldDate is not None:
            # Preserve the selected calendar date without timezone conversion.
            sale.sold_at = datetime.combine(request.soldDate, time.min)
        db.add(sale)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Return the same computed inventory representation as GET /purchases.
    return get_purchase(db, purchase_id)
