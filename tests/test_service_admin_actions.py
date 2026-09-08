from sqlalchemy import select

from models.active_effects import ActiveEffect
from models.badges import Badge, UserBadge
from models.casino import CasinoStats
from models.daily_streak import DailyStreak
from models.economy import Economy
from models.gacha import GachaCharacter, GachaState
from models.inventory import UserItem
from models.keys import UserKey
from models.levels import Level
from models.market import MarketItem
from models.rewards import Reward
from models.users import User
from services.admin_actions import (
    grant_reward_by_level,
    reset_casino,
    reset_currency,
    reset_gacha,
    reset_market,
    reset_tower,
    reset_user,
    set_level,
)
from services.leveling import xp_for_level
from config.settings import settings


async def test_set_level_creates_level_row_at_the_target_levels_floor_xp(db_session):
    user = User(guild_id=settings.guild_id, user_id=31001, username="Newbie")
    db_session.add(user)
    await db_session.flush()

    level_row = await set_level(db_session, settings.guild_id, 31001, 10)

    assert level_row.level == 10
    assert level_row.xp == xp_for_level(10)


async def test_set_level_overrides_an_existing_level_row(db_session):
    user = User(guild_id=settings.guild_id, user_id=31002, username="Existing")
    db_session.add(user)
    db_session.add(Level(guild_id=settings.guild_id, user_id=31002, xp=99999, level=30, prestige=1, last_key_drop_level=25))
    await db_session.flush()

    level_row = await set_level(db_session, settings.guild_id, 31002, 5)

    assert level_row.level == 5
    assert level_row.xp == xp_for_level(5)
    assert level_row.prestige == 1  # set_level does not touch prestige


async def test_reset_user_zeroes_progression_and_economy(db_session):
    user = User(guild_id=settings.guild_id, user_id=31003, username="Loaded")
    db_session.add(user)
    db_session.add(Level(guild_id=settings.guild_id, user_id=31003, xp=50000, level=20, prestige=2, last_key_drop_level=20))
    db_session.add(Economy(guild_id=settings.guild_id, user_id=31003, balance=500))
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31003)

    level_row = await db_session.get(Level, (settings.guild_id, 31003))
    assert level_row.xp == 0
    assert level_row.level == 0
    assert level_row.prestige == 0
    assert level_row.last_key_drop_level == 0

    economy = await db_session.get(Economy, (settings.guild_id, 31003))
    assert economy.balance == 0


async def test_reset_user_removes_badges_but_keeps_keys(db_session):
    user = User(guild_id=settings.guild_id, user_id=31004, username="Decorated")
    badge = Badge(key="veteran", name="Vétéran", description="d", icon="🎖️", rarity="rare")
    db_session.add_all([user, badge])
    await db_session.flush()

    db_session.add(UserBadge(guild_id=settings.guild_id, user_id=31004, badge_id=badge.id))
    db_session.add(UserKey(guild_id=settings.guild_id, user_id=31004, rarity="commun", count=3))
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31004)

    badges = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 31004))
    assert badges.scalars().all() == []

    # Les clés gacha restent permanentes (plus supprimées par reset_user).
    keys = await db_session.execute(select(UserKey).where(UserKey.user_id == 31004))
    remaining = keys.scalars().all()
    assert len(remaining) == 1
    assert remaining[0].count == 3


async def test_reset_market_delete_removes_guild_items(db_session):
    guild_item = MarketItem(key="guild_only", name="Objet guilde", description="d", price=100, item_type="generic", item_value=None, guild_id=settings.guild_id)
    global_item = MarketItem(key="global_item", name="Objet global", description="d", price=50, item_type="generic", item_value=None, guild_id=None)
    db_session.add_all([guild_item, global_item])
    await db_session.flush()

    count = await reset_market(db_session, settings.guild_id, mode="delete")
    await db_session.commit()

    assert count == 1
    remaining = await db_session.execute(select(MarketItem).where(MarketItem.key == "guild_only"))
    assert remaining.scalars().all() == []
    # L'article global est conservé.
    kept = await db_session.execute(select(MarketItem).where(MarketItem.key == "global_item"))
    assert kept.scalars().one_or_none() is not None


async def test_reset_market_reset_price_sets_price_to_zero(db_session):
    guild_item = MarketItem(key="pricey", name="Cher", description="d", price=500, item_type="generic", item_value=None, guild_id=settings.guild_id)
    db_session.add(guild_item)
    await db_session.flush()

    count = await reset_market(db_session, settings.guild_id, mode="reset_price")
    await db_session.commit()

    assert count == 1
    item = await db_session.execute(select(MarketItem).where(MarketItem.key == "pricey"))
    assert item.scalars().one().price == 0


async def test_reset_user_removes_inventory(db_session):
    user = User(guild_id=settings.guild_id, user_id=31006, username="Stocked")
    item = MarketItem(key="cadre", name="Cadre", description="d", price=100, item_type="generic", item_value=None)
    db_session.add_all([user, item])
    await db_session.flush()

    db_session.add(UserItem(guild_id=settings.guild_id, user_id=31006, item_id=item.id, count=2))
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31006)

    inventory = await db_session.execute(select(UserItem).where(UserItem.user_id == 31006))
    assert inventory.scalars().all() == []


async def test_reset_user_removes_rpg_tower_progress(db_session):
    from models.rpg import RpgOrBalance, RpgPlayerStats, RpgUnlockedAchievement
    import services.rpg_db as rpg_db

    user = User(guild_id=settings.guild_id, user_id=31008, username="Climber")
    db_session.add(user)
    await db_session.flush()
    await rpg_db.increment_player_stat(db_session, settings.guild_id, 31008, "monsters_killed", 5)
    await rpg_db.add_or_balance(db_session, settings.guild_id, 31008, 300)
    await rpg_db.unlock_achievement(db_session, settings.guild_id, 31008, "etage_10")
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31008)

    assert await db_session.get(RpgPlayerStats, (settings.guild_id, 31008)) is None
    assert await db_session.get(RpgOrBalance, (settings.guild_id, 31008)) is None
    achievements = await db_session.execute(
        select(RpgUnlockedAchievement).where(RpgUnlockedAchievement.user_id == 31008)
    )
    assert achievements.scalars().all() == []


async def test_reset_user_does_not_fail_when_user_has_no_level_or_economy_row(db_session):
    user = User(guild_id=settings.guild_id, user_id=31005, username="Bare")
    db_session.add(user)
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31005)  # must not raise


async def test_grant_reward_by_level_grants_every_reward_defined_for_that_level(db_session):
    user = User(guild_id=settings.guild_id, user_id=31006, username="Lucky")
    badge = Badge(key="debutant", name="Débutant", description="d", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    db_session.add(Reward(level=3, reward_type="badge", reward_value="debutant"))
    db_session.add(Reward(level=3, reward_type="coins", reward_value="50"))
    await db_session.flush()

    outcomes = await grant_reward_by_level(db_session, settings.guild_id, 31006, 3)

    assert {outcome.reward_type for outcome in outcomes} == {"badge", "coins"}

    economy = await db_session.get(Economy, (settings.guild_id, 31006))
    assert economy.balance == 50

    badges = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 31006))
    assert badges.scalar_one_or_none() is not None


async def test_reset_currency_zeroes_balance_streak_and_coins_boost_only(db_session):
    user = User(guild_id=settings.guild_id, user_id=31009, username="Rich")
    db_session.add(user)
    db_session.add(Economy(guild_id=settings.guild_id, user_id=31009, balance=999))
    db_session.add(DailyStreak(guild_id=settings.guild_id, user_id=31009, streak_count=7))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31009, effect_type="coins_boost", magnitude=2.0))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31009, effect_type="xp_boost", magnitude=2.0))
    await db_session.flush()

    await reset_currency(db_session, settings.guild_id, 31009)

    economy = await db_session.get(Economy, (settings.guild_id, 31009))
    assert economy.balance == 0
    assert await db_session.get(DailyStreak, (settings.guild_id, 31009)) is None

    remaining = await db_session.execute(select(ActiveEffect).where(ActiveEffect.user_id == 31009))
    remaining_types = {row.effect_type for row in remaining.scalars().all()}
    assert remaining_types == {"xp_boost"}  # untouched — not a coins effect


async def test_reset_tower_removes_rpg_progress(db_session):
    from models.rpg import RpgOrBalance, RpgPlayerStats
    import services.rpg_db as rpg_db

    user = User(guild_id=settings.guild_id, user_id=31010, username="Climber2")
    db_session.add(user)
    await db_session.flush()
    await rpg_db.increment_player_stat(db_session, settings.guild_id, 31010, "monsters_killed", 5)
    await rpg_db.add_or_balance(db_session, settings.guild_id, 31010, 300)
    await db_session.flush()

    await reset_tower(db_session, settings.guild_id, 31010)

    assert await db_session.get(RpgPlayerStats, (settings.guild_id, 31010)) is None
    assert await db_session.get(RpgOrBalance, (settings.guild_id, 31010)) is None


async def test_reset_casino_removes_stats_and_casino_effects_only(db_session):
    user = User(guild_id=settings.guild_id, user_id=31011, username="Gambler")
    db_session.add(user)
    db_session.add(CasinoStats(guild_id=settings.guild_id, user_id=31011, total_wagered=500, total_won=100, wins_count=2, jackpots_won=0))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31011, effect_type="casino_insurance", uses_remaining=1))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31011, effect_type="xp_boost", magnitude=1.5))
    await db_session.flush()

    await reset_casino(db_session, settings.guild_id, 31011)

    assert await db_session.get(CasinoStats, (settings.guild_id, 31011)) is None
    remaining = await db_session.execute(select(ActiveEffect).where(ActiveEffect.user_id == 31011))
    remaining_types = {row.effect_type for row in remaining.scalars().all()}
    assert remaining_types == {"xp_boost"}


async def test_reset_gacha_removes_state_characters_and_rate_boost_only(db_session):
    user = User(guild_id=settings.guild_id, user_id=31012, username="Summoner")
    db_session.add(user)
    db_session.add(GachaState(guild_id=settings.guild_id, user_id=31012, fragments=40))
    db_session.add(GachaCharacter(guild_id=settings.guild_id, user_id=31012, character_name="Test Hero", count=3))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31012, effect_type="gacha_rate_boost", magnitude=0.1))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31012, effect_type="coins_boost", magnitude=2.0))
    await db_session.flush()

    await reset_gacha(db_session, settings.guild_id, 31012)

    assert await db_session.get(GachaState, (settings.guild_id, 31012)) is None
    characters = await db_session.execute(select(GachaCharacter).where(GachaCharacter.user_id == 31012))
    assert characters.scalars().all() == []
    remaining = await db_session.execute(select(ActiveEffect).where(ActiveEffect.user_id == 31012))
    remaining_types = {row.effect_type for row in remaining.scalars().all()}
    assert remaining_types == {"coins_boost"}


async def test_reset_user_all_also_wipes_casino_gacha_streak_and_every_active_effect(db_session):
    user = User(guild_id=settings.guild_id, user_id=31013, username="Everything")
    db_session.add(user)
    db_session.add(CasinoStats(guild_id=settings.guild_id, user_id=31013, total_wagered=10, total_won=0, wins_count=0, jackpots_won=0))
    db_session.add(GachaState(guild_id=settings.guild_id, user_id=31013, fragments=5))
    db_session.add(DailyStreak(guild_id=settings.guild_id, user_id=31013, streak_count=3))
    db_session.add(ActiveEffect(guild_id=settings.guild_id, user_id=31013, effect_type="xp_boost", magnitude=2.0))
    await db_session.flush()

    await reset_user(db_session, settings.guild_id, 31013)

    assert await db_session.get(CasinoStats, (settings.guild_id, 31013)) is None
    assert await db_session.get(GachaState, (settings.guild_id, 31013)) is None
    assert await db_session.get(DailyStreak, (settings.guild_id, 31013)) is None
    remaining = await db_session.execute(select(ActiveEffect).where(ActiveEffect.user_id == 31013))
    assert remaining.scalars().all() == []


async def test_grant_reward_by_level_returns_empty_list_when_no_reward_defined(db_session):
    user = User(guild_id=settings.guild_id, user_id=31007, username="Unlucky")
    db_session.add(user)
    await db_session.flush()

    outcomes = await grant_reward_by_level(db_session, settings.guild_id, 31007, 999)

    assert outcomes == []
