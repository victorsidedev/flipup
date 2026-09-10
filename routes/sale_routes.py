from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas.sale import CreateSaleRequest
from schemas.purchase import PurchaseWithItemsResponse
from services import sale_service, refund_service

sale_router = APIRouter()


@sale_router.post("/sales", response_model=PurchaseWithItemsResponse, status_code=201)
def create_sale(request: CreateSaleRequest, db: Session = Depends(get_db)):
    return sale_service.create_sale(db, request)


@sale_router.post("/sales/{sale_id}/refund", response_model=PurchaseWithItemsResponse, status_code=201)
def refund_sale(sale_id: int, db: Session = Depends(get_db)):
    return refund_service.refund_sale(db, sale_id)
