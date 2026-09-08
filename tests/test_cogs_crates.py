from datetime import datetime, timezone
from unittest.mock import Mock

import discord

from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from cogs.crates import CrateCog, CrateView, RandomCrateButton, build_crate_embed
from models.economy import Economy
from models.keys import UserKey
from models.levels import Level
from models.users import User
from services.admin_permission import grant_permission
from services.crate_loot_table import LOOT_TABLE, LootEntry
from services.keys import add_key

OLD_ACCOUNT_CREATED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakePermissions:
    def __init__(self, administrator):
        self.administrator = administrator


class FakeRole:
    def __init__(self, id):
        self.id = id


class FakeUser:
    def __init__(self, id, display_name, created_at=OLD_ACCOUNT_CREATED_AT, administrator=False):
        self.id = id
        self.display_name = display_name
        self.created_at = created_at
        self.guild_permissions = FakePermissions(administrator)


async def make_admin(db_session, id, display_name, created_at=OLD_ACCOUNT_CREATED_AT, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.created_at = created_at
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, guild_id if guild_id is not None else settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id

    def get_role(self, role_id):
        return None

    def get_channel(self, channel_id):
        return None

    def get_member(self, member_id):
        return None


class FakeContext:
    def __init__(self, author, prefix="$", guild=None):
        self.author = author
        self.prefix = prefix
        self.guild = guild if guild is not None else FakeGuild()
        self.sent = []

    async def send(self, embed=None, view=None):
        self.sent.append({"embed": embed, "view": view})


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, embed=None, view=None):
        self.edits.append({"embed": embed, "view": view})


class FakeInteraction:
    def __init__(self, user, guild=None):
        self.user = user
        self.guild = guild or FakeGuild()
        self.response = FakeResponse()
        self.message = FakeMessage()


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
    return CrateCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_build_crate_embed_lists_all_rarities():
    embed = build_crate_embed({"commun": 3, "rare": 0, "epique": 1, "legendaire": 0, "mythique": 0, "divin": 0})

    assert len(embed.fields) == 6
    field_by_name = {f.name: f.value for f in embed.fields}
    assert "3 clé(s)" in field_by_name["🟢 Commune"]
    assert "0 clé(s)" in field_by_name["🔵 Rare"]


async def test_crate_view_disables_buttons_at_zero_keys(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=1, counts={"commun": 2, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})

    assert view.buttons_by_rarity["commun"].disabled is False
    assert view.buttons_by_rarity["rare"].disabled is True


async def test_key_command_sends_embed_and_view(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=52001, display_name="Player"))

    await cog.key.callback(cog, ctx)

    assert len(ctx.sent) == 1
    assert ctx.sent[0]["embed"] is not None
    assert ctx.sent[0]["view"] is not None
    assert ctx.sent[0]["view"].buttons_by_rarity["commun"].disabled is True  # no keys owned


async def test_key_bypass_as_admin_enables_all_buttons(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=52005, display_name="AdminPlayer"))

    await cog.key.callback(cog, ctx, "bypass")

    view = ctx.sent[0]["view"]
    assert all(not button.disabled for button in view.buttons_by_rarity.values())


async def test_key_bypass_ignored_for_non_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=52006, display_name="RegularPlayer", administrator=False))

    await cog.key.callback(cog, ctx, "bypass")

    view = ctx.sent[0]["view"]
    assert all(button.disabled for button in view.buttons_by_rarity.values())  # no keys owned


async def test_button_bypass_opens_crate_without_owning_a_key(db_session, monkeypatch):
    import random

    user = User(guild_id=settings.guild_id, user_id=52007, username="BypassOpener")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    monkeypatch.setitem(LOOT_TABLE, "commun", [LootEntry(kind="coins", value=100, label="100 Coins")])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    cog = _cog(db_session)
    view = CrateView(cog, author_id=52007, counts={"commun": 0, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0}, bypass=True)
    button = view.buttons_by_rarity["commun"]

    interaction = FakeInteraction(FakeUser(id=52007, display_name="BypassOpener"))
    await button.callback(interaction)

    assert "bypass" in interaction.response.messages[0][0]
    economy = await db_session.get(Economy, (settings.guild_id, 52007))
    assert economy.balance == 100


async def test_button_rejects_non_author_click(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=1, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})
    button = view.buttons_by_rarity["commun"]

    interaction = FakeInteraction(FakeUser(id=2, display_name="Intruder"))
    await button.callback(interaction)

    assert "Seul le joueur" in interaction.response.messages[0][0]


async def test_button_reports_no_key_owned(db_session):
    user = User(guild_id=settings.guild_id, user_id=52002, username="Keyless")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    cog = _cog(db_session)
    view = CrateView(cog, author_id=52002, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})
    button = view.buttons_by_rarity["commun"]

    interaction = FakeInteraction(FakeUser(id=52002, display_name="Keyless"))
    await button.callback(interaction)

    assert "plus de clé" in interaction.response.messages[0][0]


async def test_button_applies_coins_reward_and_refreshes_message(db_session, monkeypatch):
    import random

    user = User(guild_id=settings.guild_id, user_id=52003, username="CoinPlayer")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await db_session.commit()

    monkeypatch.setitem(LOOT_TABLE, "commun", [LootEntry(kind="coins", value=100, label="100 Coins")])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    cog = _cog(db_session)
    view = CrateView(cog, author_id=52003, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})
    button = view.buttons_by_rarity["commun"]

    interaction = FakeInteraction(FakeUser(id=52003, display_name="CoinPlayer"))
    await button.callback(interaction)

    assert "100 Coins" in interaction.response.messages[0][0]
    economy = await db_session.get(Economy, (settings.guild_id, 52003))
    assert economy.balance == 100

    assert len(interaction.message.edits) == 1
    new_view = interaction.message.edits[0]["view"]
    assert new_view.buttons_by_rarity["commun"].disabled is True  # key was consumed, none left


async def test_button_applies_xp_reward_via_award_xp(db_session, monkeypatch):
    import random

    user = User(guild_id=settings.guild_id, user_id=52004, username="XpPlayer")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await db_session.commit()

    monkeypatch.setitem(LOOT_TABLE, "commun", [LootEntry(kind="xp", value=500, label="500 XP")])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    cog = _cog(db_session)
    view = CrateView(cog, author_id=52004, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})
    button = view.buttons_by_rarity["commun"]

    interaction = FakeInteraction(FakeUser(id=52004, display_name="XpPlayer"))
    await button.callback(interaction)

    level_row = await db_session.get(Level, (settings.guild_id, 52004))
    assert level_row is not None
    assert level_row.xp == 500


async def test_crate_view_lays_out_six_rarities_across_two_rows_plus_random(db_session):
    cog = _cog(db_session)
    view = CrateView(
        cog,
        author_id=1,
        counts={"commun": 0, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0},
    )

    assert set(view.buttons_by_rarity.keys()) == {"commun", "rare", "epique", "legendaire", "mythique", "divin"}
    assert view.buttons_by_rarity["commun"].row == 0
    assert view.buttons_by_rarity["epique"].row == 0
    assert view.buttons_by_rarity["legendaire"].row == 1
    assert view.buttons_by_rarity["divin"].row == 1
    assert view.random_button.row == 2


async def test_random_button_disabled_with_no_keys_and_no_bypass(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=1, counts={"commun": 0, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})

    assert view.random_button.disabled is True


async def test_random_button_enabled_with_at_least_one_key(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=1, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})

    assert view.random_button.disabled is False


async def test_random_button_enabled_under_bypass_with_no_keys(db_session):
    cog = _cog(db_session)
    view = CrateView(
        cog, author_id=1, counts={"commun": 0, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0}, bypass=True
    )

    assert view.random_button.disabled is False


async def test_random_button_rejects_non_author_click(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=1, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})

    interaction = FakeInteraction(FakeUser(id=2, display_name="Intruder"))
    await view.random_button.callback(interaction)

    assert "Seul le joueur" in interaction.response.messages[0][0]


async def test_random_button_reports_no_crate_when_nothing_eligible(db_session):
    cog = _cog(db_session)
    view = CrateView(cog, author_id=52008, counts={"commun": 0, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})
    # Force-enable to exercise the runtime guard even though the view would normally disable this button.
    button = RandomCrateButton(disabled=False)
    button._view = view
    view.random_button = button

    interaction = FakeInteraction(FakeUser(id=52008, display_name="Empty"))
    await button.callback(interaction)

    assert "aucune caisse" in interaction.response.messages[0][0]


async def test_random_button_opens_only_owned_rarity(db_session, monkeypatch):
    import random

    user = User(guild_id=settings.guild_id, user_id=52009, username="RandomOpener")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await db_session.commit()

    # Only "commun" is eligible (the only rarity owned).
    monkeypatch.setitem(LOOT_TABLE, "commun", [LootEntry(kind="coins", value=100, label="100 Coins")])
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])

    cog = _cog(db_session)
    view = CrateView(cog, author_id=52009, counts={"commun": 1, "rare": 0, "epique": 0, "legendaire": 0, "mythique": 0, "divin": 0})

    interaction = FakeInteraction(FakeUser(id=52009, display_name="RandomOpener"))
    await view.random_button.callback(interaction)

    assert "Commune" in interaction.response.messages[0][0]
    economy = await db_session.get(Economy, (settings.guild_id, 52009))
    assert economy.balance == 100
