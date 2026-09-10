from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.item import Item
from models.sale import Sale
from models.refund import Refund
from schemas.purchase import PurchaseWithItemsResponse
from services.purchase_service import get_purchase


def refund_sale(db: Session, sale_id: int) -> PurchaseWithItemsResponse:
    try:
        # Lock the sale row to serialize with sale creation, deletion,
        # and duplicate refunds.
        sale = db.get(Sale, sale_id, with_for_update=True)
        if sale is None:
            raise HTTPException(status_code=404, detail="Sale not found")
        if db.query(Refund).filter(Refund.sale_id == sale_id).first() is not None:
            raise HTTPException(status_code=409, detail="Sale is already refunded")
        if sale.price == 0:
            raise HTTPException(status_code=409, detail="Zero-price sales cannot be refunded")
        purchase_id = db.get(Item, sale.item_id).purchase_id
        db.add(Refund(sale_id=sale.id, amount=sale.price))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_purchase(db, purchase_id)
