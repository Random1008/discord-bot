import services.gacha_db as db
from services.gacha_logic import (
    PityState,
    PullResult,
    pick_character,
    rarity_rank,
    roll_bonus_fragments,
)
from services.gacha_logic import pull as gacha_pull


def _apply_minimum_rarity(result: PullResult, min_rarity: str, rng) -> PullResult:
    if rarity_rank(result.rarity) >= rarity_rank(min_rarity):
        return result
    character = pick_character(min_rarity, rng)
    bonus_fragments = roll_bonus_fragments(min_rarity, rng)
    return PullResult(rarity=min_rarity, character=character, bonus_fragments=bonus_fragments)


async def perform_pulls(
    session,
    guild_id: int,
    user_id: int,
    count: int,
    rng,
    mythique_bonus: float = 0.0,
    min_rarity: str | None = None,
) -> list[PullResult]:
    results: list[PullResult] = []
    for _ in range(count):
        state = await db.get_gacha_state(session, guild_id, user_id)
        pity = PityState(
            pulls_since_epique=state["pulls_since_epique"],
            pulls_since_legendaire=state["pulls_since_legendaire"],
            pulls_since_mythique=state["pulls_since_mythique"],
        )
        result = gacha_pull(pity, rng, mythique_bonus=mythique_bonus)
        if min_rarity is not None:
            result = _apply_minimum_rarity(result, min_rarity, rng)

        await db.update_gacha_pity(
            session,
            guild_id,
            user_id,
            pity.pulls_since_epique,
            pity.pulls_since_legendaire,
            pity.pulls_since_mythique,
        )
        if result.character is not None:
            await db.add_character(session, guild_id, user_id, result.character)
        if result.bonus_fragments > 0:
            await db.add_fragments(session, guild_id, user_id, result.bonus_fragments)
        if result.rarity == "Secret":
            await db.increment_secret_rolls(session, guild_id, user_id)
        await db.record_gacha_pull(session, guild_id, user_id, result.rarity, result.character)
        results.append(result)
    return results
