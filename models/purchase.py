from datetime import date

from sqlalchemy import Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str | None]
    purchased_date: Mapped[date | None] = mapped_column(Date)

    items: Mapped[list["Item"]] = relationship(
        "Item",
        back_populates="purchase",
        cascade="all, delete-orphan"
    )
