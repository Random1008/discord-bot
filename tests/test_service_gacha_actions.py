import random

from config.settings import settings
from models.users import User
import services.gacha_db as db
from services.gacha_actions import perform_pulls


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=settings.guild_id, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


async def test_perform_pulls_returns_the_requested_count(db_session):
    await _make_user(db_session, 70001)

    results = await perform_pulls(db_session, settings.guild_id, 70001, 5, random.Random(1))

    assert len(results) == 5


async def test_perform_pulls_records_history_for_each_pull(db_session):
    await _make_user(db_session, 70002)

    await perform_pulls(db_session, settings.guild_id, 70002, 3, random.Random(1))
    await db_session.commit()

    history = await db.get_gacha_history(db_session, settings.guild_id, 70002)
    assert len(history) == 3


async def test_perform_pulls_persists_pity_progress_across_calls(db_session):
    await _make_user(db_session, 70003)

    class AlwaysCommun(random.Random):
        def random(self):
            return 0.0

    await perform_pulls(db_session, settings.guild_id, 70003, 1, AlwaysCommun())
    await db_session.commit()
    state_after_one = await db.get_gacha_state(db_session, settings.guild_id, 70003)
    assert state_after_one["pulls_since_epique"] == 1

    await perform_pulls(db_session, settings.guild_id, 70003, 1, AlwaysCommun())
    await db_session.commit()
    state_after_two = await db.get_gacha_state(db_session, settings.guild_id, 70003)
    assert state_after_two["pulls_since_epique"] == 2


async def test_perform_pulls_min_rarity_upgrades_a_lower_roll(db_session):
    await _make_user(db_session, 70004)

    class AlwaysCommun(random.Random):
        def random(self):
            return 0.0  # always rolls "Commun" (lowest rate bucket first)

    results = await perform_pulls(
        db_session, settings.guild_id, 70004, 1, AlwaysCommun(), min_rarity="Légendaire"
    )

    assert results[0].rarity == "Légendaire"


async def test_perform_pulls_min_rarity_does_not_downgrade_a_higher_roll(db_session):
    await _make_user(db_session, 70005)

    class AlwaysSecret(random.Random):
        def random(self):
            return 0.9999  # rolls into the top ("Secret") bucket

    results = await perform_pulls(
        db_session, settings.guild_id, 70005, 1, AlwaysSecret(), min_rarity="Rare"
    )

    assert results[0].rarity == "Secret"


async def test_perform_pulls_min_rarity_grants_a_character_for_the_forced_rarity(db_session):
    await _make_user(db_session, 70006)

    class AlwaysCommun(random.Random):
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    results = await perform_pulls(
        db_session, settings.guild_id, 70006, 1, AlwaysCommun(), min_rarity="Épique"
    )
    await db_session.commit()

    assert results[0].rarity == "Épique"
    assert results[0].character in ("Investisseur", "Roi du casino", "Seigneur criminel", "Cartographe", "Mage")

    characters = await db.get_characters(db_session, settings.guild_id, 70006)
    assert any(c["character_name"] == results[0].character for c in characters)


async def test_perform_pulls_mythique_bonus_increases_mythique_rate(db_session):
    await _make_user(db_session, 70007)

    # roll=0.5 falls under the base "Commun" bucket (cumulative 0.60) with no boost;
    # a 0.9 mythique_bonus shifts enough rate off Commun that the same roll only
    # clears the cumulative threshold once it reaches the boosted "Mythique" bucket.
    class FixedRoll(random.Random):
        def random(self):
            return 0.5

    without_boost = await perform_pulls(db_session, settings.guild_id, 70007, 1, FixedRoll(), mythique_bonus=0.0)
    await _make_user(db_session, 70008)
    with_boost = await perform_pulls(db_session, settings.guild_id, 70008, 1, FixedRoll(), mythique_bonus=0.9)

    assert without_boost[0].rarity == "Commun"
    assert with_boost[0].rarity == "Mythique"
