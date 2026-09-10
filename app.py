from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.purchase import Purchase
from models.item import Item
from models.sale import Sale
from models.refund import Refund
from routes.purchase_routes import purchase_router
from routes.sale_routes import sale_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://flipup-frontend.onrender.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(purchase_router)
app.include_router(sale_router)

@app.get("/")
def health_check():
    return {"status": "ok"}
