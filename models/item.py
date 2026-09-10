from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True
    )

    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"),
        nullable=False
    )

    parent_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id"),
        nullable=True
    )

    purchase: Mapped["Purchase"] = relationship(
        "Purchase",
        back_populates="items"
    )

    parent: Mapped["Item | None"] = relationship(
        "Item",
        remote_side="Item.id",
        back_populates="children"
    )

    children: Mapped[list["Item"]] = relationship(
        "Item",
        back_populates="parent"
    )
