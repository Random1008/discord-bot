import random

import services.gacha_db as gacha_db
from models.cosmetic_rewards import UserCosmeticReward
from services.crate_loot_table import LOOT_TABLE, LootEntry
from services.economy import add_balance
from services.effects import grant_effect
from services.gacha_actions import perform_pulls
from services.keys import add_key, get_key_count, remove_key, upgrade_key
from services.rewards import grant_badge_by_key

CRATE_RARITIES = ["commun", "rare", "epique", "legendaire", "mythique", "divin"]

MYSTERY_ELIGIBLE_KINDS = ("coins", "xp", "key")


class NoKeyOwnedError(Exception):
    pass


class CrateOpenResult:
    def __init__(self, rarity: str, entry: LootEntry):
        self.rarity = rarity
        self.kind = entry.kind
        self.value = entry.value
        self.label = entry.label
        self.pull_results: list | None = None
        self.extra_results: list["CrateOpenResult"] = []


async def _resolve_entry(session, guild_id: int, user_id: int, rarity: str, entry: LootEntry, rng) -> CrateOpenResult:
    result = CrateOpenResult(rarity=rarity, entry=entry)

    if entry.kind == "coins":
        await add_balance(session, guild_id, user_id, entry.value)
    elif entry.kind == "badge":
        await grant_badge_by_key(session, guild_id, user_id, entry.value)
    elif entry.kind == "key":
        await add_key(session, guild_id, user_id, entry.value)
    elif entry.kind == "key_bundle":
        bundle_rarity, count = entry.value
        for _ in range(count):
            await add_key(session, guild_id, user_id, bundle_rarity)
    elif entry.kind == "cosmetic":
        session.add(UserCosmeticReward(guild_id=guild_id, user_id=user_id, reward_label=entry.label, rarity=rarity))
        await session.flush()
    elif entry.kind == "gacha_pull":
        result.pull_results = await perform_pulls(session, guild_id, user_id, entry.value, rng)
    elif entry.kind == "gacha_pull_guaranteed":
        min_rarity, count = entry.value
        result.pull_results = await perform_pulls(session, guild_id, user_id, count, rng, min_rarity=min_rarity)
    elif entry.kind == "gacha_fragments":
        await gacha_db.add_fragments(session, guild_id, user_id, entry.value)
    elif entry.kind == "gacha_boost":
        bonus, duration_seconds = entry.value
        await grant_effect(
            session, guild_id, user_id, "gacha_rate_boost", magnitude=bonus, duration_seconds=duration_seconds
        )
    elif entry.kind == "effect":
        payload = entry.value
        await grant_effect(
            session,
            guild_id,
            user_id,
            payload["effect_type"],
            magnitude=payload.get("magnitude"),
            uses=payload.get("uses"),
            duration_seconds=payload.get("duration_seconds"),
        )
    elif entry.kind == "key_upgrade":
        result.value = await upgrade_key(session, guild_id, user_id, from_rarity=entry.value, rng=rng)
    elif entry.kind == "bonus_open":
        bonus_rarity, count = entry.value
        result.extra_results = [
            await open_crate(session, guild_id, user_id, bonus_rarity, rng=rng, bypass=True) for _ in range(count)
        ]
    elif entry.kind == "reroll":
        candidates = [e for e in LOOT_TABLE[rarity] if e.kind != "reroll"]
        result = await _resolve_entry(session, guild_id, user_id, rarity, rng.choice(candidates), rng)
    elif entry.kind == "mystery":
        candidates = [e for e in LOOT_TABLE[rarity] if e.kind in MYSTERY_ELIGIBLE_KINDS]
        result = await _resolve_entry(session, guild_id, user_id, rarity, rng.choice(candidates), rng)
    # "xp" is intentionally left unapplied here — awarding XP needs a discord.Guild/Member
    # for level-up announcements and role grants, which this session-only service layer
    # doesn't have. The caller (cog) applies it via award_xp using the result's value.

    return result


async def open_crate(
    session, guild_id: int, user_id: int, rarity: str, rng=random, bypass: bool = False
) -> CrateOpenResult:
    if not bypass:
        removed = await remove_key(session, guild_id, user_id, rarity)
        if not removed:
            raise NoKeyOwnedError(rarity)

    entry = rng.choice(LOOT_TABLE[rarity])
    return await _resolve_entry(session, guild_id, user_id, rarity, entry, rng)


async def get_key_counts(session, guild_id: int, user_id: int) -> dict[str, int]:
    return {rarity: await get_key_count(session, guild_id, user_id, rarity) for rarity in CRATE_RARITIES}
