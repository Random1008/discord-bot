from config.settings import settings
from models.users import User
import services.gacha_db as db


async def _make_user(session, guild_id, user_id, name="Player"):
    user = User(guild_id=guild_id, user_id=user_id, username=name)
    session.add(user)
    await session.flush()
    return user


async def test_get_gacha_state_defaults_to_zero(db_session):
    await _make_user(db_session, settings.guild_id, 90001)

    state = await db.get_gacha_state(db_session, settings.guild_id, 90001)

    assert state == {
        "pulls_since_epique": 0,
        "pulls_since_legendaire": 0,
        "pulls_since_mythique": 0,
        "fragments": 0,
        "secret_rolls": 0,
    }


async def test_update_gacha_pity_persists_counters(db_session):
    await _make_user(db_session, settings.guild_id, 90002)

    await db.update_gacha_pity(db_session, settings.guild_id, 90002, 3, 7, 42)
    await db_session.commit()

    state = await db.get_gacha_state(db_session, settings.guild_id, 90002)
    assert state["pulls_since_epique"] == 3
    assert state["pulls_since_legendaire"] == 7
    assert state["pulls_since_mythique"] == 42


async def test_add_fragments_accumulates_and_floors_at_zero(db_session):
    await _make_user(db_session, settings.guild_id, 90003)

    await db.add_fragments(db_session, settings.guild_id, 90003, 5)
    total = await db.add_fragments(db_session, settings.guild_id, 90003, -10)
    await db_session.commit()

    assert total == 0


async def test_spend_fragments_succeeds_when_enough(db_session):
    await _make_user(db_session, settings.guild_id, 90004)
    await db.add_fragments(db_session, settings.guild_id, 90004, 20)
    await db_session.commit()

    ok, remaining = await db.spend_fragments(db_session, settings.guild_id, 90004, 15)
    await db_session.commit()

    assert ok is True
    assert remaining == 5


async def test_spend_fragments_rejects_insufficient(db_session):
    await _make_user(db_session, settings.guild_id, 90005)
    await db.add_fragments(db_session, settings.guild_id, 90005, 5)
    await db_session.commit()

    ok, remaining = await db.spend_fragments(db_session, settings.guild_id, 90005, 10)

    assert ok is False
    assert remaining == 5


async def test_add_character_creates_then_increments(db_session):
    await _make_user(db_session, settings.guild_id, 90006)

    await db.add_character(db_session, settings.guild_id, 90006, "Comptable")
    await db.add_character(db_session, settings.guild_id, 90006, "Comptable")
    await db_session.commit()

    characters = await db.get_characters(db_session, settings.guild_id, 90006)
    assert characters == [{"character_name": "Comptable", "count": 2}]


async def test_remove_character_decrements_then_deletes(db_session):
    await _make_user(db_session, settings.guild_id, 90007)
    await db.add_character(db_session, settings.guild_id, 90007, "Banquier")
    await db_session.commit()

    removed = await db.remove_character(db_session, settings.guild_id, 90007, "Banquier")
    await db_session.commit()

    assert removed is True
    assert await db.get_characters(db_session, settings.guild_id, 90007) == []


async def test_remove_character_returns_false_when_not_owned(db_session):
    await _make_user(db_session, settings.guild_id, 90008)

    removed = await db.remove_character(db_session, settings.guild_id, 90008, "Nobody")

    assert removed is False


async def test_record_and_get_gacha_history_most_recent_first(db_session):
    await _make_user(db_session, settings.guild_id, 90009)

    await db.record_gacha_pull(db_session, settings.guild_id, 90009, "Commun", "Comptable")
    await db.record_gacha_pull(db_session, settings.guild_id, 90009, "Rare", "Banquier")
    await db_session.commit()

    history = await db.get_gacha_history(db_session, settings.guild_id, 90009)
    assert history[0] == {"rarity": "Rare", "character_name": "Banquier"}
    assert history[1] == {"rarity": "Commun", "character_name": "Comptable"}


async def test_wishlist_set_get_and_clear(db_session):
    await _make_user(db_session, settings.guild_id, 90010)

    assert await db.get_wishlist_character(db_session, settings.guild_id, 90010) is None

    await db.set_wishlist_character(db_session, settings.guild_id, 90010, "Dragonier")
    await db_session.commit()
    assert await db.get_wishlist_character(db_session, settings.guild_id, 90010) == "Dragonier"

    await db.set_wishlist_character(db_session, settings.guild_id, 90010, None)
    await db_session.commit()
    assert await db.get_wishlist_character(db_session, settings.guild_id, 90010) is None


async def test_gacha_state_is_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await _make_user(db_session, settings.guild_id, 90011)
    await _make_user(db_session, other_guild_id, 90011)

    await db.add_fragments(db_session, settings.guild_id, 90011, 50)
    await db_session.commit()

    state_here = await db.get_gacha_state(db_session, settings.guild_id, 90011)
    state_other = await db.get_gacha_state(db_session, other_guild_id, 90011)
    assert state_here["fragments"] == 50
    assert state_other["fragments"] == 0


async def test_characters_are_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await _make_user(db_session, settings.guild_id, 90012)
    await _make_user(db_session, other_guild_id, 90012)

    await db.add_character(db_session, settings.guild_id, 90012, "Archer")
    await db_session.commit()

    assert await db.get_characters(db_session, settings.guild_id, 90012) == [
        {"character_name": "Archer", "count": 1}
    ]
    assert await db.get_characters(db_session, other_guild_id, 90012) == []
