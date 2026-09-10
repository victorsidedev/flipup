from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas.purchase import CreatePurchaseRequest, PurchaseWithItemsResponse, SavePurchaseRequest
from services import purchase_service, delete_service

purchase_router = APIRouter()

@purchase_router.get(
    "/purchases",
    response_model=list[PurchaseWithItemsResponse]
)
def get_purchases(
    db: Session = Depends(get_db)
):
    return (purchase_service.get_purchases(db))

@purchase_router.post("/purchase")
def create_purchase(
        request: CreatePurchaseRequest,
        db: Session = Depends(get_db)
):
    purchase, item_id_map = purchase_service.create_purchase(db, request)
    return {
        "message": "Purchase request is valid",
        "purchase": purchase,
        "item_id_map": item_id_map
    }


@purchase_router.post("/purchases", response_model=PurchaseWithItemsResponse, status_code=201)
def add_purchase(request: CreatePurchaseRequest, db: Session = Depends(get_db)):
    purchase, _ = purchase_service.create_purchase(db, request)
    return purchase_service.get_purchase(db, purchase.id)


@purchase_router.put("/purchases/{purchase_id}", response_model=PurchaseWithItemsResponse)
def update_purchase(purchase_id: int, request: SavePurchaseRequest, db: Session = Depends(get_db)):
    return purchase_service.update_purchase(db, purchase_id, request)


@purchase_router.delete("/purchases/{purchase_id}", status_code=204)
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    delete_service.delete_purchase(db, purchase_id)


@purchase_router.delete("/items/{item_id}", response_model=PurchaseWithItemsResponse)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    return delete_service.delete_item(db, item_id)
