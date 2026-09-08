from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class NoXpChannel(Base):
    __tablename__ = "no_xp_channels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
