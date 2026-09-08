from datetime import date as PyDate

from sqlalchemy import BigInteger, Date, ForeignKeyConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class VoiceStat(Base):
    __tablename__ = "voice_stats"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
        UniqueConstraint("guild_id", "user_id", "date", name="uq_voice_stats_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[PyDate] = mapped_column(Date, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MessageStat(Base):
    __tablename__ = "message_stats"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
        UniqueConstraint("guild_id", "user_id", "date", name="uq_message_stats_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[PyDate] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ServerStat(Base):
    __tablename__ = "server_stats"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[PyDate] = mapped_column(Date, primary_key=True)
    total_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voice_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
