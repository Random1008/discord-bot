import random
from datetime import datetime, timezone

from config.settings import settings
from services.alt_account_guard import apply_alt_penalty, is_recent_account
from services.announcements import (
    format_key_drop_message,
    format_level_up_message,
    format_prestige_message,
    format_reward_message,
)
from services.leveling import LevelUpResult, add_xp
from services.users import get_or_create_user

REWARD_ROLE_SETTINGS = {
    "role_actif": "role_actif_id",
    "role_habitue": "role_habitue_id",
    "role_veteran": "role_veteran_id",
    "role_legendaire": "role_legendaire_id",
    "role_bronze": "role_bronze_id",
    "role_argent": "role_argent_id",
    "role_or": "role_or_id",
    "role_platine": "role_platine_id",
    "role_diamant": "role_diamant_id",
    "role_mythique": "role_mythique_id",
    "vip_argent": "role_vip_argent_id",
    "premium": "role_premium_id",
}

PRESTIGE_ROLE_SETTINGS = {
    1: "prestige_1_role_id",
    2: "prestige_2_role_id",
    3: "prestige_3_role_id",
    4: "prestige_4_role_id",
}


async def award_xp(
    session, guild, channel_resolver, member, base_amount: int, rng=random, bypass_alt_guard: bool = False
) -> LevelUpResult:
    guild_id = guild.id
    await get_or_create_user(session, guild_id, member.id, member.display_name)

    if bypass_alt_guard:
        amount = base_amount
    else:
        flagged = is_recent_account(member.created_at, datetime.now(timezone.utc))
        amount = apply_alt_penalty(base_amount, flagged)

    result = await add_xp(session, guild_id, member.id, amount, rng=rng)
    await session.commit()

    channel = channel_resolver()

    await _dispatch_level_up_result(guild, channel, member, result)

    if result.inviter_bonus is not None:
        inviter_member = guild.get_member(result.inviter_bonus.user_id)
        if inviter_member is not None:
            await _dispatch_level_up_result(guild, channel, inviter_member, result.inviter_bonus)

    return result


async def _dispatch_level_up_result(guild, channel, member, result: LevelUpResult) -> None:
    for level in result.levels_gained:
        if channel is not None:
            await channel.send(format_level_up_message(member.display_name, level))

    for outcome in result.reward_outcomes:
        if channel is not None:
            await channel.send(format_reward_message(member.display_name, outcome))
        await _maybe_assign_role(guild, member, REWARD_ROLE_SETTINGS.get(outcome.reward_value))

    for drop in result.key_drops:
        if channel is not None:
            await channel.send(format_key_drop_message(member.display_name, drop))

    if result.prestige_reached is not None:
        await _maybe_assign_role(guild, member, PRESTIGE_ROLE_SETTINGS.get(result.prestige_reached))
        if channel is not None:
            await channel.send(format_prestige_message(member.display_name, result.prestige_reached))


async def _maybe_assign_role(guild, member, role_id_setting_name: str | None) -> None:
    if role_id_setting_name is None:
        return
    role_id = getattr(settings, role_id_setting_name, None)
    if not role_id:
        return
    role = guild.get_role(int(role_id))
    if role is not None:
        await member.add_roles(role)
