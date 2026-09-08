from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from models.active_effects import ActiveEffect


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_valid(effect: ActiveEffect, now: datetime) -> bool:
    if effect.expires_at is not None:
        expires_at = effect.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return False
    if effect.uses_remaining is not None and effect.uses_remaining <= 0:
        return False
    return True


async def grant_effect(
    session,
    guild_id: int,
    user_id: int,
    effect_type: str,
    magnitude: float | None = None,
    uses: int | None = None,
    duration_seconds: int | None = None,
) -> ActiveEffect:
    expires_at = _now() + timedelta(seconds=duration_seconds) if duration_seconds is not None else None
    effect = ActiveEffect(
        guild_id=guild_id,
        user_id=user_id,
        effect_type=effect_type,
        magnitude=magnitude,
        uses_remaining=uses,
        expires_at=expires_at,
    )
    session.add(effect)
    await session.flush()
    return effect


async def _active_effects(session, guild_id: int, user_id: int, effect_type: str) -> list[ActiveEffect]:
    result = await session.execute(
        select(ActiveEffect).where(
            ActiveEffect.guild_id == guild_id,
            ActiveEffect.user_id == user_id,
            ActiveEffect.effect_type == effect_type,
        )
    )
    now = _now()
    return [effect for effect in result.scalars().all() if _is_valid(effect, now)]


async def get_active_multiplier(session, guild_id: int, user_id: int, effect_type: str) -> float:
    effects = await _active_effects(session, guild_id, user_id, effect_type)
    magnitudes = [effect.magnitude for effect in effects if effect.magnitude is not None]
    return max(magnitudes, default=1.0)


async def get_active_bonus(session, guild_id: int, user_id: int, effect_type: str) -> float:
    effects = await _active_effects(session, guild_id, user_id, effect_type)
    return sum(effect.magnitude for effect in effects if effect.magnitude is not None)


async def has_active(session, guild_id: int, user_id: int, effect_type: str) -> bool:
    effects = await _active_effects(session, guild_id, user_id, effect_type)
    return len(effects) > 0


async def consume_one_shot(session, guild_id: int, user_id: int, effect_type: str) -> bool:
    effects = await _active_effects(session, guild_id, user_id, effect_type)
    if not effects:
        return False
    effect = min(effects, key=lambda e: e.id)
    if effect.uses_remaining is None:
        await session.delete(effect)
    else:
        effect.uses_remaining -= 1
        if effect.uses_remaining <= 0:
            await session.delete(effect)
    await session.flush()
    return True
