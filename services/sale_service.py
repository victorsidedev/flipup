from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.item import Item
from models.sale import Sale
from models.sale_item import SaleItem
from models.sale_expense import SaleExpense
from schemas.purchase import PurchaseWithItemsResponse
from schemas.sale import CreateSaleRequest
from services.item_status import collect_subtree_ids
from services.purchase_service import get_purchase


def create_sale(db: Session, request: CreateSaleRequest) -> PurchaseWithItemsResponse:
    try:
        requested_ids = [sale_item.itemId for sale_item in request.items]
        # Lock the item rows so concurrent sales see the latest state
        # before deciding whether the items are still available.
        items = {
            item.id: item
            for item in db.query(Item).filter(Item.id.in_(requested_ids)).with_for_update()
        }
        missing = set(requested_ids) - set(items)
        if missing:
            raise HTTPException(status_code=404, detail=f"Item not found: {sorted(missing)[0]}")

        purchase_ids = {item.purchase_id for item in items.values()}
        if len(purchase_ids) > 1:
            raise HTTPException(status_code=422, detail="Sale items must belong to the same purchase")
        purchase_id = next(iter(purchase_ids))

        purchase_items = {
            candidate.id: candidate
            for candidate in db.query(Item).filter(Item.purchase_id == purchase_id)
        }
        expanded_ids = collect_subtree_ids(set(requested_ids), purchase_items)

        already_sold = {
            row.item_id
            for row in db.query(SaleItem.item_id).filter(SaleItem.item_id.in_(expanded_ids))
        }
        if already_sold:
            raise HTTPException(status_code=409, detail=f"Item already sold: {sorted(already_sold)[0]}")

        allocated_prices = {sale_item.itemId: sale_item.allocatedPrice for sale_item in request.items}

        sale = Sale(item_id=requested_ids[0], price=request.price, kind=request.kind)
        if request.soldDate is not None:
            # Preserve the selected calendar date without timezone conversion.
            sale.sold_at = datetime.combine(request.soldDate, time.min)
        db.add(sale)
        db.flush()

        for item_id in expanded_ids:
            db.add(SaleItem(
                sale_id=sale.id,
                item_id=item_id,
                allocated_price=allocated_prices.get(item_id),
            ))

        for expense in request.expenses:
            db.add(SaleExpense(
                sale_id=sale.id,
                item_id=expense.itemId,
                type=expense.type,
                amount=expense.amount,
                description=expense.description,
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise

    # Return the same computed inventory representation as GET /purchases.
    return get_purchase(db, purchase_id)

