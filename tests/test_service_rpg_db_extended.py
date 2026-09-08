from config.settings import settings
from models.users import User
import services.rpg_db as db


async def _make_user(session, guild_id, user_id, name="Player"):
    user = User(guild_id=guild_id, user_id=user_id, username=name)
    session.add(user)
    await session.flush()
    return user


async def test_add_inventory_item_and_get_inventory(db_session):
    await _make_user(db_session, settings.guild_id, 70001)
    await db.add_inventory_item(db_session, settings.guild_id, 70001, "weapon", "epee_de_bronze")
    await db.add_inventory_item(db_session, settings.guild_id, 70001, "weapon", "epee_de_bronze")
    await db.add_inventory_item(db_session, settings.guild_id, 70001, "armor", "cotte_du_gardien")
    await db_session.commit()

    inv = await db.get_inventory(db_session, settings.guild_id, 70001)
    assert inv["weapon"]["epee_de_bronze"] == 2
    assert inv["armor"]["cotte_du_gardien"] == 1


async def test_loadout_defaults_to_none_and_can_be_set(db_session):
    await _make_user(db_session, settings.guild_id, 70002)

    weapon, armor = await db.get_loadout(db_session, settings.guild_id, 70002)
    assert weapon is None and armor is None

    await db.set_loadout(db_session, settings.guild_id, 70002, "epee_rouillee", "tunique_usee")
    await db_session.commit()

    weapon, armor = await db.get_loadout(db_session, settings.guild_id, 70002)
    assert weapon == "epee_rouillee"
    assert armor == "tunique_usee"


async def test_unlock_title_is_idempotent(db_session):
    await _make_user(db_session, settings.guild_id, 70003)

    assert await db.unlock_title(db_session, settings.guild_id, 70003, "aventurier_debutant") is True
    assert await db.unlock_title(db_session, settings.guild_id, 70003, "aventurier_debutant") is False
    await db_session.commit()

    assert await db.get_unlocked_titles(db_session, settings.guild_id, 70003) == {"aventurier_debutant"}


async def test_record_boss_defeated_and_get_defeated(db_session):
    await _make_user(db_session, settings.guild_id, 70004)

    assert await db.record_boss_defeated(db_session, settings.guild_id, 70004, "gardien_miroir") is True
    assert await db.record_boss_defeated(db_session, settings.guild_id, 70004, "gardien_miroir") is False
    await db.record_boss_defeated(db_session, settings.guild_id, 70004, "boucher_affame")
    await db_session.commit()

    defeated = await db.get_defeated_bosses(db_session, settings.guild_id, 70004)
    assert defeated == {"gardien_miroir", "boucher_affame"}


async def test_increment_new_counter_fields(db_session):
    await _make_user(db_session, settings.guild_id, 70005)

    await db.increment_player_stat(db_session, settings.guild_id, 70005, "tower_xp", 100)
    await db.increment_player_stat(db_session, settings.guild_id, 70005, "boss_kills", 2)
    await db.increment_player_stat(db_session, settings.guild_id, 70005, "chests_opened", 3)
    await db_session.commit()

    row = await db.get_rpg_stats_row(db_session, settings.guild_id, 70005)
    assert row.tower_xp == 100
    assert row.boss_kills == 2
    assert row.chests_opened == 3


async def test_set_infinite_mode_flag(db_session):
    await _make_user(db_session, settings.guild_id, 70006)

    await db.set_player_flag(db_session, settings.guild_id, 70006, "infinite_mode_reached", True)
    await db_session.commit()

    row = await db.get_rpg_stats_row(db_session, settings.guild_id, 70006)
    assert row.infinite_mode_reached is True


async def test_get_tower_xp_defaults_to_zero(db_session):
    await _make_user(db_session, settings.guild_id, 70007)
    assert await db.get_tower_xp(db_session, settings.guild_id, 70007) == 0
