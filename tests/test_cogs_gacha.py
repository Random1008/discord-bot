import random
from unittest.mock import Mock

import discord

from cogs.gacha import GachaCog, build_character_list_embed
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.economy import Economy
from services.admin_permission import grant_permission
from services.economy import add_balance
from services.gacha_logic import CHARACTERS_BY_RARITY, RARITY_ORDER
from services.users import get_or_create_user


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, guild_id if guild_id is not None else settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.messages = []

    async def send(self, content=None, **kwargs):
        self.messages.append(content if content is not None else kwargs.get("embed"))


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


def _cog(db_session):
    return GachaCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


def test_build_character_list_embed_has_one_field_per_rarity_in_order():
    embed = build_character_list_embed()

    field_names = [f.name for f in embed.fields]
    assert len(field_names) == len(RARITY_ORDER)
    for rarity, field_name in zip(RARITY_ORDER, field_names):
        assert rarity in field_name


def test_build_character_list_embed_lists_every_character_of_a_rarity():
    embed = build_character_list_embed()

    epique_field = next(f for f in embed.fields if "Épique" in f.name)
    for character in CHARACTERS_BY_RARITY["Épique"]:
        assert character in epique_field.value


def test_build_character_list_embed_shows_a_placeholder_for_an_empty_rarity():
    embed = build_character_list_embed()

    secret_field = next(f for f in embed.fields if "Secret" in f.name)
    assert CHARACTERS_BY_RARITY["Secret"] == []
    assert "Aucun personnage" in secret_field.value


async def test_gacha_list_command_sends_the_character_list_embed(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90199, display_name="Browser"))

    await cog.gacha_list.callback(cog, ctx)

    embed = ctx.messages[0]
    assert embed.title == "🎲 Personnages du Gacha"
    assert len(embed.fields) == len(RARITY_ORDER)


async def test_gacha_add_grants_a_known_character(db_session):
    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90201, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_add.callback(cog, ctx, member, nom="Comptable")

    import services.gacha_db as gdb

    characters = await gdb.get_characters(db_session, settings.guild_id, 90201)
    assert {c["character_name"]: c["count"] for c in characters} == {"Comptable": 1}
    assert "Comptable" in ctx.messages[0]


async def test_gacha_add_is_case_insensitive(db_session):
    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90202, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_add.callback(cog, ctx, member, nom="comptable")

    import services.gacha_db as gdb

    characters = await gdb.get_characters(db_session, settings.guild_id, 90202)
    assert {c["character_name"] for c in characters} == {"Comptable"}


async def test_gacha_add_rejects_an_unknown_character_name(db_session):
    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90203, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_add.callback(cog, ctx, member, nom="Personnage Inexistant")

    import services.gacha_db as gdb

    characters = await gdb.get_characters(db_session, settings.guild_id, 90203)
    assert characters == []
    assert "Aucun personnage" in ctx.messages[0]


async def test_gacha_remove_removes_one_copy(db_session):
    import services.gacha_db as gdb

    await get_or_create_user(db_session, settings.guild_id, 90204, "Target")
    await gdb.add_character(db_session, settings.guild_id, 90204, "Comptable")
    await gdb.add_character(db_session, settings.guild_id, 90204, "Comptable")
    await db_session.commit()

    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90204, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_remove.callback(cog, ctx, member, nom="Comptable")

    characters = await gdb.get_characters(db_session, settings.guild_id, 90204)
    assert {c["character_name"]: c["count"] for c in characters} == {"Comptable": 1}


async def test_gacha_remove_reports_when_not_owned(db_session):
    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90205, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_remove.callback(cog, ctx, member, nom="Comptable")

    assert "ne possède pas" in ctx.messages[0]


async def test_gacha_reset_wipes_the_entire_collection(db_session):
    import services.gacha_db as gdb

    await get_or_create_user(db_session, settings.guild_id, 90206, "Target")
    await gdb.add_character(db_session, settings.guild_id, 90206, "Comptable")
    await gdb.add_fragments(db_session, settings.guild_id, 90206, 50)
    await db_session.commit()

    cog = _cog(db_session)
    admin = await make_admin(db_session, id=1, display_name="Admin")
    member = FakeUser(id=90206, display_name="Target")
    ctx = FakeContext(admin)

    await cog.gacha_reset.callback(cog, ctx, member)

    characters = await gdb.get_characters(db_session, settings.guild_id, 90206)
    state = await gdb.get_gacha_state(db_session, settings.guild_id, 90206)
    assert characters == []
    assert state["fragments"] == 0


async def test_pull_rejects_insufficient_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90101, display_name="Broke"))

    await cog.gacha_pull_cmd.callback(cog, ctx)

    assert "Pas assez de credits" in ctx.messages[0]


async def test_pull_deducts_cost_and_records_history(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 90102, "Puller")
    await add_balance(db_session, settings.guild_id, 90102, 500)
    await db_session.commit()

    fixed_rng = random.Random(1)
    monkeypatch.setattr(random, "Random", lambda: fixed_rng)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90102, display_name="Puller"))
    await cog.gacha_pull_cmd.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 90102))
    assert economy.balance == 400

    import services.gacha_db as db

    history = await db.get_gacha_history(db_session, settings.guild_id, 90102)
    assert len(history) == 1


async def test_multi_rejects_insufficient_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90103, display_name="Broke2"))

    await cog.gacha_multi.callback(cog, ctx)

    assert "Pas assez de credits" in ctx.messages[0]


async def test_multi_performs_ten_pulls(db_session):
    await get_or_create_user(db_session, settings.guild_id, 90104, "MultiPuller")
    await add_balance(db_session, settings.guild_id, 90104, 1000)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90104, display_name="MultiPuller"))
    await cog.gacha_multi.callback(cog, ctx)

    economy = await db_session.get(Economy, (settings.guild_id, 90104))
    assert economy.balance == 100

    import services.gacha_db as db

    history = await db.get_gacha_history(db_session, settings.guild_id, 90104)
    assert len(history) == 10


async def test_pity_reports_defaults_for_new_player(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90105, display_name="NewPlayer"))

    await cog.gacha_pity.callback(cog, ctx)

    assert "Épique dans 10 pulls" in ctx.messages[0]
    assert "Fragments : 0" in ctx.messages[0]


async def test_inventory_reports_empty_for_new_player(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90106, display_name="Empty"))

    await cog.gacha_inventory.callback(cog, ctx)

    assert "Aucun personnage" in ctx.messages[0]


async def test_inventory_lists_owned_characters(db_session):
    import services.gacha_db as db

    await get_or_create_user(db_session, settings.guild_id, 90107, "Collector")
    await db.add_character(db_session, settings.guild_id, 90107, "Comptable")
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90107, display_name="Collector"))
    await cog.gacha_inventory.callback(cog, ctx)

    assert "Comptable x1" in ctx.messages[0]


async def test_history_reports_empty_for_new_player(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90108, display_name="NoHistory"))

    await cog.gacha_history.callback(cog, ctx)

    assert "Aucun historique" in ctx.messages[0]


async def test_wishlist_default_is_empty(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90109, display_name="Wisher"))

    await cog.gacha_wishlist.callback(cog, ctx)

    assert "Aucun personnage en wishlist" in ctx.messages[0]


async def test_wishlist_set_then_get(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90110, display_name="Wisher2"))

    await cog.gacha_wishlist_set.callback(cog, ctx, character_name="Dragonier")
    await cog.gacha_wishlist.callback(cog, ctx)

    assert "Dragonier" in ctx.messages[-1]


async def test_wishlist_clear_removes_it(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90111, display_name="Wisher3"))

    await cog.gacha_wishlist_set.callback(cog, ctx, character_name="Archer")
    await cog.gacha_wishlist_clear.callback(cog, ctx)
    await cog.gacha_wishlist.callback(cog, ctx)

    assert "Aucun personnage en wishlist" in ctx.messages[-1]


async def test_rates_lists_all_rarities(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90112, display_name="RateChecker"))

    await cog.gacha_rates.callback(cog, ctx)

    assert "Commun" in ctx.messages[0]
    assert "Secret" in ctx.messages[0]


async def test_pull_cost_is_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    await get_or_create_user(db_session, settings.guild_id, 90113, "Traveler")
    await get_or_create_user(db_session, other_guild_id, 90113, "Traveler")
    await add_balance(db_session, settings.guild_id, 90113, 500)
    await db_session.commit()

    cog = _cog(db_session)
    ctx_other = FakeContext(FakeUser(id=90113, display_name="Traveler"), guild=FakeGuild(other_guild_id))
    await cog.gacha_pull_cmd.callback(cog, ctx_other)

    assert "Pas assez de credits" in ctx_other.messages[0]
    economy_here = await db_session.get(Economy, (settings.guild_id, 90113))
    assert economy_here.balance == 500


async def test_pull_bypass_skips_cost_for_admin_with_no_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=90114, display_name="AdminPuller"))

    await cog.gacha_pull_cmd.callback(cog, ctx, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 90114))
    assert economy is None or economy.balance == 0
    assert "bypass" in ctx.messages[0]

    import services.gacha_db as db

    history = await db.get_gacha_history(db_session, settings.guild_id, 90114)
    assert len(history) == 1


async def test_pull_bypass_ignored_for_non_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=90115, display_name="RegularPlayer"))

    await cog.gacha_pull_cmd.callback(cog, ctx, "bypass")

    assert "Pas assez de credits" in ctx.messages[0]


async def test_multi_bypass_skips_cost_for_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=90116, display_name="AdminMultiPuller"))

    await cog.gacha_multi.callback(cog, ctx, "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 90116))
    assert economy is None or economy.balance == 0
    assert "bypass" in ctx.messages[0]

    import services.gacha_db as db

    history = await db.get_gacha_history(db_session, settings.guild_id, 90116)
    assert len(history) == 10
