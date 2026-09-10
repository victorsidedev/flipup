from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("price >= 0", name="sale_price_nonnegative"),
        CheckConstraint("kind IN ('sale', 'loss')", name="sale_kind_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    kind: Mapped[str] = mapped_column(String(4), default="sale", server_default="sale")
    sold_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
