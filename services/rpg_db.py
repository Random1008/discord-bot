from sqlalchemy import select

import services.economy as economy_service
from models.rpg import (
    RpgBossDefeated,
    RpgCodexVisit,
    RpgDeathRecord,
    RpgInventory,
    RpgLoadout,
    RpgNgPlus,
    RpgOrBalance,
    RpgPlayerStats,
    RpgTitle,
    RpgUnlockedAchievement,
)
from services.rpg.achievements import PlayerStats
from services.rpg.legacy import DeathRecord, Legacy

_INCREMENTABLE_PLAYER_STAT_FIELDS = {
    "monsters_killed",
    "gold_earned_total",
    "deaths",
    "boss_no_damage_wins",
    "tower_xp",
    "chests_opened",
    "casino_wins",
    "jackpots",
    "boss_kills",
    "curses_survived",
    "pacts_used",
    "runs_completed",
}


async def _get_or_create_stats_row(session, guild_id: int, user_id: int) -> RpgPlayerStats:
    row = await session.get(RpgPlayerStats, (guild_id, user_id))
    if row is None:
        row = RpgPlayerStats(guild_id=guild_id, user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def get_rpg_stats_row(session, guild_id: int, user_id: int) -> RpgPlayerStats:
    return await _get_or_create_stats_row(session, guild_id, user_id)


async def get_player_stats(session, guild_id: int, user_id: int) -> PlayerStats:
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    return PlayerStats(
        floor_reached_max=row.floor_reached_max,
        monsters_killed=row.monsters_killed,
        gold_earned_total=row.gold_earned_total,
        deaths=row.deaths,
        boss_no_damage_wins=row.boss_no_damage_wins,
    )


async def increment_player_stat(session, guild_id: int, user_id: int, field: str, amount: int = 1) -> None:
    if field not in _INCREMENTABLE_PLAYER_STAT_FIELDS:
        raise ValueError(f"Champ non incrémentable : {field}")
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    setattr(row, field, getattr(row, field) + amount)
    await session.flush()


async def set_player_flag(session, guild_id: int, user_id: int, field: str, value: bool = True) -> None:
    if field not in {"infinite_mode_reached"}:
        raise ValueError(f"Champ booléen non modifiable : {field}")
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    setattr(row, field, value)
    await session.flush()


async def get_tower_xp(session, guild_id: int, user_id: int) -> int:
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    return row.tower_xp


async def update_floor_reached_max(session, guild_id: int, user_id: int, floor_number: int) -> None:
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    row.floor_reached_max = max(row.floor_reached_max, floor_number)
    await session.flush()


async def admin_set_floor_reached_max(session, guild_id: int, user_id: int, floor_number: int) -> int:
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    row.floor_reached_max = max(0, floor_number)
    await session.flush()
    return row.floor_reached_max


async def admin_adjust_floor_reached_max(session, guild_id: int, user_id: int, delta: int) -> int:
    row = await _get_or_create_stats_row(session, guild_id, user_id)
    row.floor_reached_max = max(0, row.floor_reached_max + delta)
    await session.flush()
    return row.floor_reached_max


async def record_death(session, guild_id: int, user_id: int, floor_reached: int, monsters_killed: int, gold_earned: int) -> None:
    session.add(
        RpgDeathRecord(
            guild_id=guild_id,
            user_id=user_id,
            floor_reached=floor_reached,
            monsters_killed=monsters_killed,
            gold_earned=gold_earned,
        )
    )
    await session.flush()


async def get_legacy(session, guild_id: int, user_id: int) -> Legacy:
    result = await session.execute(
        select(RpgDeathRecord)
        .where(RpgDeathRecord.guild_id == guild_id, RpgDeathRecord.user_id == user_id)
        .order_by(RpgDeathRecord.id.asc())
    )
    history = [
        DeathRecord(floor_reached=r.floor_reached, monsters_killed=r.monsters_killed, gold_earned=r.gold_earned)
        for r in result.scalars().all()
    ]
    return Legacy(history=history)


async def record_codex_visit(session, guild_id: int, user_id: int, key: str) -> int:
    row = await session.get(RpgCodexVisit, (guild_id, user_id, key))
    if row is None:
        row = RpgCodexVisit(guild_id=guild_id, user_id=user_id, key=key, count=1)
        session.add(row)
    else:
        row.count += 1
    await session.flush()
    return row.count


async def get_codex_visit_count(session, guild_id: int, user_id: int, key: str) -> int:
    row = await session.get(RpgCodexVisit, (guild_id, user_id, key))
    return row.count if row is not None else 0


async def get_all_codex_visits(session, guild_id: int, user_id: int) -> dict[str, int]:
    result = await session.execute(
        select(RpgCodexVisit).where(RpgCodexVisit.guild_id == guild_id, RpgCodexVisit.user_id == user_id)
    )
    return {row.key: row.count for row in result.scalars().all() if not row.key.startswith("event:")}


async def get_unlocked_achievements(session, guild_id: int, user_id: int) -> set[str]:
    result = await session.execute(
        select(RpgUnlockedAchievement.achievement_key).where(
            RpgUnlockedAchievement.guild_id == guild_id, RpgUnlockedAchievement.user_id == user_id
        )
    )
    return {row[0] for row in result.all()}


async def unlock_achievement(session, guild_id: int, user_id: int, achievement_key: str) -> bool:
    existing = await session.get(RpgUnlockedAchievement, (guild_id, user_id, achievement_key))
    if existing is not None:
        return False
    session.add(RpgUnlockedAchievement(guild_id=guild_id, user_id=user_id, achievement_key=achievement_key))
    await session.flush()
    return True


async def get_ng_plus(session, guild_id: int, user_id: int) -> int:
    row = await session.get(RpgNgPlus, (guild_id, user_id))
    return row.tier if row is not None else 0


async def set_ng_plus(session, guild_id: int, user_id: int, tier: int) -> None:
    row = await session.get(RpgNgPlus, (guild_id, user_id))
    if row is None:
        row = RpgNgPlus(guild_id=guild_id, user_id=user_id, tier=tier)
        session.add(row)
    else:
        row.tier = tier
    await session.flush()


async def get_or_balance(session, guild_id: int, user_id: int) -> int:
    row = await session.get(RpgOrBalance, (guild_id, user_id))
    if row is None:
        row = RpgOrBalance(guild_id=guild_id, user_id=user_id, balance=0)
        session.add(row)
        await session.flush()
        return 0
    return row.balance


async def add_or_balance(session, guild_id: int, user_id: int, amount: int) -> None:
    row = await session.get(RpgOrBalance, (guild_id, user_id))
    if row is None:
        row = RpgOrBalance(guild_id=guild_id, user_id=user_id, balance=0)
        session.add(row)
        await session.flush()
    row.balance += amount
    await session.flush()


async def spend_or_balance(session, guild_id: int, user_id: int, amount: int) -> tuple[bool, int]:
    row = await session.get(RpgOrBalance, (guild_id, user_id))
    if row is None:
        row = RpgOrBalance(guild_id=guild_id, user_id=user_id, balance=0)
        session.add(row)
        await session.flush()
    if row.balance < amount:
        return False, row.balance
    row.balance -= amount
    await session.flush()
    return True, row.balance


async def convert_or_to_credits(session, guild_id: int, user_id: int, amount: int) -> tuple[bool, str]:
    if amount <= 0:
        return False, "invalid_amount"
    success, _balance = await spend_or_balance(session, guild_id, user_id, amount)
    if not success:
        return False, "insufficient_or"
    await economy_service.add_balance(session, guild_id, user_id, amount)
    return True, "ok"


# --- Inventaire & équipement ---

async def add_inventory_item(session, guild_id: int, user_id: int, item_type: str, item_key: str) -> int:
    """Ajoute (ou incrémente) un équipement possédé. Retourne la quantité."""
    row = await session.get(RpgInventory, (guild_id, user_id, item_type, item_key))
    if row is None:
        row = RpgInventory(guild_id=guild_id, user_id=user_id, item_type=item_type, item_key=item_key, quantity=1)
        session.add(row)
    else:
        row.quantity += 1
    await session.flush()
    return row.quantity


async def get_inventory(session, guild_id: int, user_id: int) -> dict[str, dict[str, int]]:
    result = await session.execute(
        select(RpgInventory).where(RpgInventory.guild_id == guild_id, RpgInventory.user_id == user_id)
    )
    inventory: dict[str, dict[str, int]] = {}
    for row in result.scalars().all():
        inventory.setdefault(row.item_type, {})[row.item_key] = row.quantity
    return inventory


async def get_loadout(session, guild_id: int, user_id: int) -> tuple[str | None, str | None]:
    row = await session.get(RpgLoadout, (guild_id, user_id))
    if row is None:
        return None, None
    return row.weapon_key, row.armor_key


async def set_loadout(session, guild_id: int, user_id: int, weapon_key: str | None, armor_key: str | None) -> None:
    row = await session.get(RpgLoadout, (guild_id, user_id))
    if row is None:
        row = RpgLoadout(guild_id=guild_id, user_id=user_id, weapon_key=weapon_key, armor_key=armor_key)
        session.add(row)
    else:
        row.weapon_key = weapon_key
        row.armor_key = armor_key
    await session.flush()


# --- Titres ---

async def unlock_title(session, guild_id: int, user_id: int, title_key: str) -> bool:
    existing = await session.get(RpgTitle, (guild_id, user_id, title_key))
    if existing is not None:
        return False
    session.add(RpgTitle(guild_id=guild_id, user_id=user_id, title_key=title_key))
    await session.flush()
    return True


async def get_unlocked_titles(session, guild_id: int, user_id: int) -> set[str]:
    result = await session.execute(
        select(RpgTitle.title_key).where(RpgTitle.guild_id == guild_id, RpgTitle.user_id == user_id)
    )
    return {row[0] for row in result.all()}


# --- Boss vaincus ---

async def record_boss_defeated(session, guild_id: int, user_id: int, boss_key: str) -> bool:
    existing = await session.get(RpgBossDefeated, (guild_id, user_id, boss_key))
    if existing is not None:
        return False
    session.add(RpgBossDefeated(guild_id=guild_id, user_id=user_id, boss_key=boss_key))
    await session.flush()
    return True


async def get_defeated_bosses(session, guild_id: int, user_id: int) -> set[str]:
    result = await session.execute(
        select(RpgBossDefeated.boss_key).where(RpgBossDefeated.guild_id == guild_id, RpgBossDefeated.user_id == user_id)
    )
    return {row[0] for row in result.all()}
