from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CreateSaleRequest(BaseModel):
    itemId: int = Field(gt=0)
    kind: Literal["sale", "loss"] = "sale"
    soldDate: date | None = None
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class SaleResponse(BaseModel):
    id: int
    kind: Literal["sale", "loss"]
    soldAt: datetime
    itemId: int
    price: Decimal

