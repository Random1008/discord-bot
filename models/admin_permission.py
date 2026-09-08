from sqlalchemy import BigInteger, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class AdminPermission(Base):
    __tablename__ = "admin_permissions"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    granted_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
