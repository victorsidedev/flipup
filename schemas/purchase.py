from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas.sale import SaleResponse

class PurchaseResponse(BaseModel):
    id: int
    source: str | None
    purchaseDate: date | None

class ItemResponse(BaseModel):
    id: int
    name: str | None
    price: Decimal | None
    parentId: int | None
    purchaseId: int
    sale: SaleResponse | None = None
    status: Literal["available", "sold"] = "available"

class PurchaseWithItemsResponse(BaseModel):
    purchase: PurchaseResponse
    items: list[ItemResponse]

class PurchaseRequest(BaseModel):
    source: str = Field(min_length=1)
    purchaseDate: date | None


class PurchaseItemRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    parentId: str | None = None
    itemId: int | None = Field(default=None, gt=0)


class SavePurchaseRequest(BaseModel):
    purchase: PurchaseRequest
    items: list[PurchaseItemRequest]

    @model_validator(mode="after")
    def validate_item_relationships(self):
        item_ids = {item.id for item in self.items}

        if len(item_ids) != len(self.items):
            raise ValueError("Item IDs must be unique")

        for item in self.items:
            if item.parentId is not None and item.parentId not in item_ids:
                raise ValueError(
                    f"Parent item '{item.parentId}' does not exist"
                )

        persisted_ids = [item.itemId for item in self.items if item.itemId is not None]
        if len(set(persisted_ids)) != len(persisted_ids):
            raise ValueError("Database item IDs must be unique")
        by_id = {item.id: item for item in self.items}
        for item in self.items:
            visited = set()
            current = item
            while current is not None:
                if current.id in visited:
                    raise ValueError("Items cannot form a parent cycle")
                visited.add(current.id)
                current = by_id.get(current.parentId)
        return self


class CreatePurchaseRequest(SavePurchaseRequest):
    items: list[PurchaseItemRequest] = Field(min_length=1)
