from sqlalchemy import BigInteger, ForeignKeyConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class CasinoJackpot(Base):
    __tablename__ = "casino_jackpot"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pool: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CasinoStats(Base):
    __tablename__ = "casino_stats"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    total_wagered: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_won: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    wins_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jackpots_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
