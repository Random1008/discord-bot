from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ActiveEffect(Base):
    __tablename__ = "active_effects"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effect_type: Mapped[str] = mapped_column(String(40), nullable=False)
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    uses_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
