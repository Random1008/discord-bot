from sqlalchemy import BigInteger, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class GachaState(Base):
    __tablename__ = "gacha_state"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pulls_since_epique: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pulls_since_legendaire: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pulls_since_mythique: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fragments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    secret_rolls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GachaCharacter(Base):
    __tablename__ = "gacha_characters"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    character_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class GachaHistoryEntry(Base):
    __tablename__ = "gacha_history"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)
    character_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GachaWishlist(Base):
    __tablename__ = "gacha_wishlist"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    character_name: Mapped[str] = mapped_column(String(100), nullable=False)
