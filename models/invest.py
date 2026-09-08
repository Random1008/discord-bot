from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKeyConstraint, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class MarketIndex(Base):
    __tablename__ = "invest_market_index"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    index_value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class MarketHistory(Base):
    __tablename__ = "market_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    index_value: Mapped[float] = mapped_column(Float, nullable=False)
    is_accurate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvestDaily(Base):
    """Compteur journalier d'investissements (limite de 5/jour)."""

    __tablename__ = "invest_daily"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    invest_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    invest_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
