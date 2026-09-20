from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SaleItem(Base):
    __tablename__ = "sale_items"

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    allocated_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
