from sqlalchemy import BigInteger, Boolean, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class RpgPlayerStats(Base):
    __tablename__ = "rpg_player_stats"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    floor_reached_max: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monsters_killed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gold_earned_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    boss_no_damage_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Progression de niveau propre à la Tour (distincte du leveling messages).
    tower_xp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # ATK permanente gagnée via la Lame de l'Infini (persiste entre les runs).
    permanent_atk: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Compteurs pour les titres.
    chests_opened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    casino_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jackpots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    boss_kills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    curses_survived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pacts_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    infinite_mode_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RpgDeathRecord(Base):
    __tablename__ = "rpg_death_records"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    floor_reached: Mapped[int] = mapped_column(Integer, nullable=False)
    monsters_killed: Mapped[int] = mapped_column(Integer, nullable=False)
    gold_earned: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RpgCodexVisit(Base):
    __tablename__ = "rpg_codex_visits"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RpgUnlockedAchievement(Base):
    __tablename__ = "rpg_unlocked_achievements"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    achievement_key: Mapped[str] = mapped_column(String(50), primary_key=True)


class RpgNgPlus(Base):
    __tablename__ = "rpg_ng_plus"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RpgOrBalance(Base):
    __tablename__ = "rpg_or_balance"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class RpgInventory(Base):
    """Inventaire persistant d'équipement (armes/armures) possédé."""

    __tablename__ = "rpg_inventory"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_type: Mapped[str] = mapped_column(String(20), primary_key=True)  # "weapon" | "armor"
    item_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class RpgLoadout(Base):
    """Arme et armure équipées (une de chaque)."""

    __tablename__ = "rpg_loadout"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    weapon_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    armor_key: Mapped[str | None] = mapped_column(String(50), nullable=True)


class RpgTitle(Base):
    """Titres débloqués."""

    __tablename__ = "rpg_titles"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title_key: Mapped[str] = mapped_column(String(50), primary_key=True)


class RpgBossDefeated(Base):
    """Boss (gimmick) vaincus au moins une fois, pour le titre « Tueur de Titans »."""

    __tablename__ = "rpg_boss_defeated"
    __table_args__ = (
        ForeignKeyConstraint(["guild_id", "user_id"], ["shared.users.guild_id", "shared.users.user_id"]),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    boss_key: Mapped[str] = mapped_column(String(50), primary_key=True)
