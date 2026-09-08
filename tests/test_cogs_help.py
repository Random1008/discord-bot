from unittest.mock import Mock

import discord

from cogs.help import (
    ADMIN_CATEGORIES,
    MAJ_SECTIONS,
    HelpCategorySelect,
    HelpCog,
    PLAYER_CATEGORIES,
    visible_admin_categories,
    visible_maj_sections,
    visible_player_categories,
)
from config.settings import YORU_DUPLICATE_RESTRICTED_GUILD_ID


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


def make_admin(id, display_name):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.guild_permissions = discord.Permissions(administrator=True)
    return admin


class FakeGuild:
    def __init__(self, id):
        self.id = id


class FakeContext:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild
        self.sent = []

    async def send(self, content=None, embed=None, view=None, **kwargs):
        self.sent.append({"content": content, "embed": embed, "view": view})


class FakeResponse:
    def __init__(self):
        self.edited = []
        self.messages = []

    async def edit_message(self, embed=None, **kwargs):
        self.edited.append(embed)

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()


def _cog():
    return HelpCog(bot=Mock())


EXPECTED_PREFIX_BY_CATEGORY = {
    "economie": "$",
    "boutique": "$",
    "casino": "$",
    "gacha": "$",
    "crime": "$",
    "progression": "!",
}

# "tour" est pilotée par des boutons (+ une commande de consultation !towerof),
# donc pas de préfixe unique pour toute la catégorie.
#
# `!complice` est une commande non-argent (préfixe `!`) documentée dans la
# catégorie « Monde criminel » car elle est liée aux procès : elle échappe à la
# règle « toute la catégorie en `$` ».
NON_MONEY_HELP_ENTRIES = {"!complice [@membre | ID]"}


def test_all_player_entries_use_the_correct_prefix_for_their_category():
    assert {c["key"] for c in PLAYER_CATEGORIES} == set(EXPECTED_PREFIX_BY_CATEGORY) | {"tour"}
    for category in PLAYER_CATEGORIES:
        expected = EXPECTED_PREFIX_BY_CATEGORY.get(category["key"])
        if expected is None:
            continue  # catégorie pilotée par boutons (tour), pas de préfixe
        for usage, _ in category["entries"]:
            if usage in NON_MONEY_HELP_ENTRIES:
                continue
            assert usage.startswith(expected), f"{usage!r} in {category['key']!r} should start with {expected!r}"


def test_visible_player_categories_full_list_off_restricted_guild():
    categories = visible_player_categories(1297620557927284877)
    assert categories == PLAYER_CATEGORIES


def test_visible_player_categories_hides_restricted_ones_on_yoru_guild():
    categories = visible_player_categories(YORU_DUPLICATE_RESTRICTED_GUILD_ID)
    keys = {c["key"] for c in categories}
    assert "casino" not in keys
    assert "gacha" not in keys
    assert "tour" not in keys
    assert "economie" in keys


def test_visible_player_categories_handles_dm_context():
    categories = visible_player_categories(None)
    assert categories == PLAYER_CATEGORIES


async def test_help_command_shows_prefix_legend_footer():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Player"), guild=FakeGuild(1297620557927284877))

    await cog.help_cmd.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    assert "$" in embed.footer.text
    assert "." in embed.footer.text
    assert "!" in embed.footer.text


async def test_adminhelp_shows_prefix_legend_footer():
    cog = _cog()
    admin = make_admin(id=1, display_name="Admin")
    ctx = FakeContext(admin, guild=FakeGuild(1297620557927284877))

    await cog.adminhelp_cmd.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    assert embed.footer.text


async def test_help_command_shows_full_categories_on_serveur_lia():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Player"), guild=FakeGuild(1297620557927284877))

    await cog.help_cmd.callback(cog, ctx)

    view = ctx.sent[0]["view"]
    select = view.children[0]
    values = {opt.value for opt in select.options}
    assert "casino" in values
    assert "tour" in values


async def test_help_command_hides_categories_on_serveur_random():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Player"), guild=FakeGuild(YORU_DUPLICATE_RESTRICTED_GUILD_ID))

    await cog.help_cmd.callback(cog, ctx)

    view = ctx.sent[0]["view"]
    select = view.children[0]
    values = {opt.value for opt in select.options}
    assert "casino" not in values
    assert "gacha" not in values
    assert "tour" not in values


async def test_adminhelp_shows_all_admin_categories_off_restricted_guild():
    cog = _cog()
    admin = make_admin(id=1, display_name="Admin")
    ctx = FakeContext(admin, guild=FakeGuild(1297620557927284877))

    await cog.adminhelp_cmd.callback(cog, ctx)

    view = ctx.sent[0]["view"]
    select = view.children[0]
    assert [opt.value for opt in select.options] == [c["key"] for c in ADMIN_CATEGORIES]


async def test_adminhelp_hides_gacha_admin_category_on_yoru_guild():
    cog = _cog()
    admin = make_admin(id=1, display_name="Admin")
    ctx = FakeContext(admin, guild=FakeGuild(YORU_DUPLICATE_RESTRICTED_GUILD_ID))

    await cog.adminhelp_cmd.callback(cog, ctx)

    view = ctx.sent[0]["view"]
    select = view.children[0]
    assert "admin_gacha" not in {opt.value for opt in select.options}


def test_visible_admin_categories_full_list_off_restricted_guild():
    assert visible_admin_categories(1297620557927284877) == ADMIN_CATEGORIES


def test_visible_admin_categories_hides_restricted_ones_on_yoru_guild():
    categories = visible_admin_categories(YORU_DUPLICATE_RESTRICTED_GUILD_ID)
    keys = {c["key"] for c in categories}
    assert "admin_gacha" not in keys
    assert "admin_general" in keys


def test_visible_maj_sections_full_list_off_restricted_guild():
    sections = visible_maj_sections(1297620557927284877)
    assert sections == MAJ_SECTIONS


def test_visible_maj_sections_hides_restricted_ones_on_yoru_guild():
    sections = visible_maj_sections(YORU_DUPLICATE_RESTRICTED_GUILD_ID)
    titles = {s["title"] for s in sections}
    assert "Casino" not in titles
    assert "Gacha" not in titles
    assert "Tour RPG" not in titles
    assert "Économie & progression" in titles


def test_visible_maj_sections_handles_dm_context():
    assert visible_maj_sections(None) == MAJ_SECTIONS


async def test_maj_command_shows_all_sections_on_serveur_lia():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Visitor"), guild=FakeGuild(1297620557927284877))

    await cog.maj_cmd.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    field_names = {f.name for f in embed.fields}
    assert any("Casino" in name for name in field_names)
    assert any("Tour RPG" in name for name in field_names)
    assert "!help" in embed.footer.text


async def test_maj_command_hides_restricted_sections_on_serveur_random():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Visitor"), guild=FakeGuild(YORU_DUPLICATE_RESTRICTED_GUILD_ID))

    await cog.maj_cmd.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    field_names = {f.name for f in embed.fields}
    assert not any("Casino" in name for name in field_names)
    assert any("Économie" in name for name in field_names)


async def test_maj_command_works_in_dm_context():
    cog = _cog()
    ctx = FakeContext(FakeUser(id=1, display_name="Visitor"), guild=None)

    await cog.maj_cmd.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    assert embed.title


async def test_category_select_callback_switches_embed():
    select = HelpCategorySelect(PLAYER_CATEGORIES, author_id=42)
    select._values = ["casino"]
    interaction = FakeInteraction(FakeUser(id=42, display_name="Player"))

    await select.callback(interaction)

    assert len(interaction.response.edited) == 1
    assert "Casino" in interaction.response.edited[0].title


async def test_category_select_rejects_non_author():
    select = HelpCategorySelect(PLAYER_CATEGORIES, author_id=42)
    select._values = ["casino"]
    interaction = FakeInteraction(FakeUser(id=99, display_name="Intruder"))

    await select.callback(interaction)

    assert interaction.response.messages
    assert "pas le tien" in interaction.response.messages[0][0]
