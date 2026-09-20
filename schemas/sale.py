from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SaleItemRequest(BaseModel):
    itemId: int = Field(gt=0)
    allocatedPrice: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class SaleExpenseRequest(BaseModel):
    type: Literal["payment_fee", "shipping_fee"]
    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    description: str | None = None
    itemId: int | None = Field(default=None, gt=0)


class CreateSaleRequest(BaseModel):
    items: list[SaleItemRequest] = Field(min_length=1)
    kind: Literal["sale", "loss"] = "sale"
    soldDate: date | None = None
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    expenses: list[SaleExpenseRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_items(self):
        item_ids = [item.itemId for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Item IDs must be unique")
        return self


class SaleItemResponse(BaseModel):
    itemId: int
    allocatedPrice: Decimal | None


class SaleExpenseResponse(BaseModel):
    id: int
    type: Literal["payment_fee", "shipping_fee"]
    amount: Decimal
    description: str | None
    itemId: int | None


class SaleResponse(BaseModel):
    id: int
    kind: Literal["sale", "loss"]
    soldAt: datetime
    price: Decimal
    items: list[SaleItemResponse]
    expenses: list[SaleExpenseResponse]


