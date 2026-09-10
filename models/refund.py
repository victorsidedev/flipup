from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Refund(Base):
    """Append-only credit notes; services must never update or delete these rows."""

    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="refund_amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refunded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
