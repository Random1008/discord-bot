from sqlalchemy import BigInteger, ForeignKeyConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class DailyStreak(Base):
    __tablename__ = "daily_streaks"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
