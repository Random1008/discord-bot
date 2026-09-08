from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKeyConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Level(Base):
    __tablename__ = "levels"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    xp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prestige: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voice_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_key_drop_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_voice_reward_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
