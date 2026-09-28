import random

from sqlalchemy import delete, func, select

from models.active_effects import ActiveEffect
from models.badges import UserBadge
from models.casino import CasinoStats
from models.cosmetic_rewards import UserCosmeticReward
from models.daily_streak import DailyStreak
from models.economy import Economy
from models.gacha import GachaCharacter, GachaHistoryEntry, GachaState, GachaWishlist
from models.inventory import UserItem
from models.invest import InvestDaily
from models.keys import UserKey
from models.levels import Level
from models.market import MarketItem
from models.prestiges import Prestige
from models.quests import UserQuest
from models.rewards import Reward
from models.stats import MessageStat, VoiceStat
from models.users import User
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
from services.casino import reset_jackpot
from services.leveling import get_or_create_level, xp_for_level
from services.rewards import RewardOutcome, grant_reward

RESET_CATEGORIES = ("argent", "monnaie", "tour", "tower", "casino", "gacha", "all")

CASINO_EFFECT_TYPES = ("casino_insurance", "casino_free_bet", "casino_double_win", "casino_jackpot_chance_boost")

RPG_MODELS = (
    RpgPlayerStats,
    RpgDeathRecord,
    RpgCodexVisit,
    RpgUnlockedAchievement,
    RpgNgPlus,
    RpgOrBalance,
    RpgInventory,
    RpgLoadout,
    RpgTitle,
    RpgBossDefeated,
)
GACHA_MODELS = (GachaState, GachaCharacter, GachaHistoryEntry, GachaWishlist)

# Tables vidées par `.reset everything` (TOUS les joueurs de la guilde).
# Volontairement EXCLUS :
#   - `users` / `economy` : les lignes sont CONSERVÉES et remises à zéro (les
#     autres bots de l'écosystème pointent vers `shared.users` — les supprimer
#     casserait leurs clés étrangères) ;
#   - `admin_permissions` / `bot_blocked_users` : état de modération, pas de la
#     progression (sinon il faudrait tout regrant à la main après le reset) ;
#   - tables de guilde (boutique, cagnotte, index d'investissement, salons sans
#     XP) : traitées à part.
EVERYTHING_DELETE_MODELS = (
    ActiveEffect,
    UserBadge,
    UserCosmeticReward,
    CasinoStats,
    DailyStreak,
    UserItem,
    InvestDaily,
    UserKey,
    Prestige,
    UserQuest,
    VoiceStat,
    MessageStat,
    *GACHA_MODELS,
    *RPG_MODELS,
)


async def count_guild_players(session, guild_id: int) -> int:
    """Nombre de joueurs connus du bot sur la guilde (lignes `shared.users`)."""
    result = await session.execute(
        select(func.count()).select_from(User).where(User.guild_id == guild_id)
    )
    return int(result.scalar_one())


async def reset_everything(session, guild_id: int) -> dict[str, int]:
    """Efface TOUTE la progression de TOUS les joueurs de la guilde.

    Supprime les lignes par joueur (Tour RPG, gacha **et clés gacha**, badges,
    inventaire, casino, effets actifs, séries quotidiennes, quêtes, prestiges,
    investissements, stats messages/vocal), remet à zéro les portefeuilles et la
    progression de niveau, puis remet le compteur du jackpot à zéro.

    Les lignes `users` et `economy` sont conservées (voir
    EVERYTHING_DELETE_MODELS) : le joueur existe toujours, il repart juste de
    zéro. Retourne le nombre de lignes supprimées par table.
    """
    counts: dict[str, int] = {}
    for model in EVERYTHING_DELETE_MODELS:
        result = await session.execute(delete(model).where(model.guild_id == guild_id))
        counts[model.__tablename__] = int(result.rowcount or 0)

    economies = (
        await session.execute(select(Economy).where(Economy.guild_id == guild_id))
    ).scalars().all()
    for economy in economies:
        economy.balance = 0
        economy.bank_balance = 0
        economy.last_daily_at = None
        economy.last_work_at = None
        economy.last_weekly_at = None
        economy.last_monthly_at = None
        economy.last_crime_at = None
        economy.last_rob_at = None
        economy.prison_until = None
    counts["economy (remis à zéro)"] = len(economies)

    levels = (
        await session.execute(select(Level).where(Level.guild_id == guild_id))
    ).scalars().all()
    for level_row in levels:
        level_row.xp = 0
        level_row.level = 0
        level_row.prestige = 0
        level_row.last_key_drop_level = 0
    counts["levels (remis à zéro)"] = len(levels)

    await reset_jackpot(session, guild_id)
    counts["casino_jackpot (remis à zéro)"] = 1
    await session.flush()
    return counts


async def set_level(session, guild_id: int, user_id: int, level: int) -> Level:
    """Force a user's level, setting their XP to that level's floor. Does not retroactively
    grant the rewards crossed to get there, and does not touch prestige — a blunt override
    tool for correcting a level, not a level-up simulation."""
    level_row = await get_or_create_level(session, guild_id, user_id)
    level_row.level = level
    level_row.xp = xp_for_level(level)
    await session.flush()
    return level_row


async def reset_currency(session, guild_id: int, user_id: int) -> None:
    """Wipe a user's coin balance, daily streak, and any active coins-boost effect."""
    economy = await session.get(Economy, (guild_id, user_id))
    if economy is not None:
        economy.balance = 0

    await session.execute(
        delete(DailyStreak).where(DailyStreak.guild_id == guild_id, DailyStreak.user_id == user_id)
    )
    await session.execute(
        delete(ActiveEffect).where(
            ActiveEffect.guild_id == guild_id, ActiveEffect.user_id == user_id, ActiveEffect.effect_type == "coins_boost"
        )
    )
    await session.flush()


async def reset_tower(session, guild_id: int, user_id: int) -> None:
    """Wipe a user's RPG Tower progression: stats, deaths, codex visits, achievements, NG+ and Or balance."""
    for model in RPG_MODELS:
        await session.execute(delete(model).where(model.guild_id == guild_id, model.user_id == user_id))
    await session.flush()


async def reset_casino(session, guild_id: int, user_id: int) -> None:
    """Wipe a user's casino stats and any active casino effect (insurance, free bet, double win, chance boost)."""
    await session.execute(
        delete(CasinoStats).where(CasinoStats.guild_id == guild_id, CasinoStats.user_id == user_id)
    )
    await session.execute(
        delete(ActiveEffect).where(
            ActiveEffect.guild_id == guild_id,
            ActiveEffect.user_id == user_id,
            ActiveEffect.effect_type.in_(CASINO_EFFECT_TYPES),
        )
    )
    await session.flush()


async def reset_market(session, guild_id: int, mode: str = "delete") -> int:
    """Réinitialise la boutique de la guilde (articles propres à la guilde, pas
    les articles globaux). mode='delete' supprime les articles ; mode='reset_price'
    met leur prix à 0 (inachetables tant que le prix n'est pas redéfini).
    Retourne le nombre d'articles affectés."""
    result = await session.execute(select(MarketItem).where(MarketItem.guild_id == guild_id))
    items = result.scalars().all()
    for item in items:
        if mode == "reset_price":
            item.price = 0
        else:
            await session.delete(item)
    await session.flush()
    return len(items)


async def reset_gacha(session, guild_id: int, user_id: int) -> None:
    """Wipe a user's gacha pity/fragments, collected characters, pull history, wishlist, and any active rate-boost effect."""
    for model in GACHA_MODELS:
        await session.execute(delete(model).where(model.guild_id == guild_id, model.user_id == user_id))
    await session.execute(
        delete(ActiveEffect).where(
            ActiveEffect.guild_id == guild_id,
            ActiveEffect.user_id == user_id,
            ActiveEffect.effect_type == "gacha_rate_boost",
        )
    )
    await session.flush()


async def reset_user(session, guild_id: int, user_id: int) -> None:
    """Wipe a user's progression, currency, tower, casino, gacha, badges, inventory, and any
    remaining active effect (e.g. xp_boost). Gacha keys are deliberately kept (permanent).
    Daily quest progress and message/voice stats are left untouched — they're already date-scoped
    and reset naturally, not part of a user's standing progression."""
    level_row = await session.get(Level, (guild_id, user_id))
    if level_row is not None:
        level_row.xp = 0
        level_row.level = 0
        level_row.prestige = 0
        level_row.last_key_drop_level = 0

    await reset_currency(session, guild_id, user_id)
    await reset_tower(session, guild_id, user_id)
    await reset_casino(session, guild_id, user_id)
    await reset_gacha(session, guild_id, user_id)

    await session.execute(
        delete(UserBadge).where(UserBadge.guild_id == guild_id, UserBadge.user_id == user_id)
    )
    await session.execute(
        delete(UserItem).where(UserItem.guild_id == guild_id, UserItem.user_id == user_id)
    )
    await session.execute(
        delete(ActiveEffect).where(ActiveEffect.guild_id == guild_id, ActiveEffect.user_id == user_id)
    )
    await session.flush()


async def grant_reward_by_level(session, guild_id: int, user_id: int, level: int, rng=random) -> list[RewardOutcome]:
    """Replay every reward defined for `level` (mirrors the level-crossing loop in
    services/leveling.py::add_xp), independent of the user's actual current level."""
    result = await session.execute(select(Reward).where(Reward.level == level))
    rewards = result.scalars().all()
    outcomes = [await grant_reward(session, guild_id, user_id, reward, rng=rng) for reward in rewards]
    await session.flush()
    return outcomes
