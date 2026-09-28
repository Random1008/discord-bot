from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class MarketItem(Base):
    __tablename__ = "market_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    # BIGINT : les objets premium (accès Casino VIP à 10 Md) dépassent la limite
    # d'un INTEGER 32 bits (2 147 483 647).
    price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_market_items_key"),
        UniqueConstraint("name", name="uq_market_items_name"),
    )
