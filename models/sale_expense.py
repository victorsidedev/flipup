from decimal import Decimal

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SaleExpense(Base):
    __tablename__ = "sale_expenses"
    __table_args__ = (
        ForeignKeyConstraint(["sale_id", "item_id"], ["sale_items.sale_id", "sale_items.item_id"]),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None]
