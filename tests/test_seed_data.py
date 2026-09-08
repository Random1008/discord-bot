import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_engine_and_session
from models.badges import Badge
from models.market import MarketItem
from models.quests import Quest
from models.rewards import Reward


async def test_seed_data_present():
    engine, session_factory = create_engine_and_session(os.environ["DATABASE_URL"])

    async with session_factory() as session:
        badges = (await session.execute(select(Badge))).scalars().all()
        rewards = (await session.execute(select(Reward))).scalars().all()
        quests = (await session.execute(select(Quest))).scalars().all()
        market_items = (await session.execute(select(MarketItem))).scalars().all()

    await engine.dispose()

    assert len(badges) == 14
    assert len(rewards) == 19
    assert len(quests) == 3
    assert any(r.level == 100 and r.reward_type == "badge" and r.reward_value == "diamant" for r in rewards)
    level_badges = {"debutant", "actif", "habitue", "veteran", "legendaire", "diamant"}
    granted_badge_values = {r.reward_value for r in rewards if r.reward_type == "badge"}
    assert level_badges <= granted_badge_values

    role_ladder = {"role_bronze", "role_argent", "role_or", "role_platine", "role_diamant", "role_mythique"}
    granted_role_values = {r.reward_value for r in rewards if r.reward_type == "role"}
    assert role_ladder <= granted_role_values

    assert len(market_items) == 7
    assert all(item.price == 0 for item in market_items)
    item_values = {item.item_value for item in market_items}
    assert item_values == {"aleatoire", "commun", "rare", "epique", "legendaire", "mythique", "divin"}
