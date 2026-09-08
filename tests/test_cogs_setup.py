from unittest.mock import Mock

import discord

from cogs.setup import SetupCog, WelcomeConfigView, WelcomeEditModal
from config.settings import settings


def FakeUser(id, is_admin=True):
    member = Mock(spec=discord.Member)
    member.id = id
    member.guild_permissions = discord.Permissions(administrator=is_admin)
    return member


class FakeChannel:
    def __init__(self, id):
        self.id = id
        self.sent = []

    async def send(self, embed=None):
        self.sent.append(embed)


class FakeGuild:
    def __init__(self, id=None, channels=None):
        self.id = id if id is not None else settings.guild_id
        self._channels = channels or {}

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, embed=None, **kwargs):
        self.edits.append(embed)


class FakeContext:
    def __init__(self, guild=None, author=None, prefix="."):
        self.guild = guild or FakeGuild()
        self.author = author or FakeUser(id=1)
        self.prefix = prefix
        self.sent = []

    async def send(self, content=None, *, embed=None, view=None):
        message = FakeMessage()
        self.sent.append((content, embed, view))
        return message


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.modals = []

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()


class FakeBot:
    pass


def _cog(tmp_path):
    cog = SetupCog(bot=FakeBot())
    cog._welcome_config_path = tmp_path / "welcome_config.json"
    return cog


async def test_setup_welcome_shows_default_preview_when_unconfigured(tmp_path):
    cog = _cog(tmp_path)
    ctx = FakeContext()

    await cog.setup_welcome.callback(cog, ctx)

    _, embed, view = ctx.sent[0]
    assert "Bienvenue" in embed.title
    assert isinstance(view, WelcomeConfigView)


async def test_edit_button_rejects_non_author():
    view = WelcomeConfigView(cog=Mock(), author_id=1)
    interaction = FakeInteraction(FakeUser(id=2))

    await view.edit_button.callback(interaction)

    assert "Seul l'administrateur" in interaction.response.messages[0]["content"]
    assert interaction.response.modals == []


async def test_edit_button_opens_modal_for_the_author(tmp_path):
    cog = _cog(tmp_path)
    view = WelcomeConfigView(cog=cog, author_id=1)
    interaction = FakeInteraction(FakeUser(id=1))

    await view.edit_button.callback(interaction)

    assert len(interaction.response.modals) == 1
    assert isinstance(interaction.response.modals[0], WelcomeEditModal)


async def test_welcome_edit_modal_saves_config_and_shows_a_preview(tmp_path):
    cog = _cog(tmp_path)
    config = {"title": "Old", "text": "Old text", "image_url": None}
    modal = WelcomeEditModal(cog, config, message=None)
    modal.title_input._value = "Nouveau titre"
    modal.text_input._value = "Salut {membre} !"
    modal.image_input._value = "https://example.com/img.png"

    interaction = FakeInteraction(FakeUser(id=1))
    await modal.on_submit(interaction)

    saved = interaction.response.messages[0]
    assert saved["embed"].title == "Nouveau titre"
    assert saved["embed"].description == "Salut {membre} !"

    from services.welcome_config import load_welcome_config

    persisted = load_welcome_config(cog._welcome_config_path)
    assert persisted == {"title": "Nouveau titre", "text": "Salut {membre} !", "image_url": "https://example.com/img.png"}


async def test_welcome_edit_modal_clears_image_url_when_left_blank(tmp_path):
    cog = _cog(tmp_path)
    config = {"title": "T", "text": "X", "image_url": "https://example.com/old.png"}
    modal = WelcomeEditModal(cog, config, message=None)
    modal.title_input._value = "T"
    modal.text_input._value = "X"
    modal.image_input._value = "   "

    interaction = FakeInteraction(FakeUser(id=1))
    await modal.on_submit(interaction)

    from services.welcome_config import load_welcome_config

    persisted = load_welcome_config(cog._welcome_config_path)
    assert persisted["image_url"] is None


async def test_welcome_edit_modal_updates_the_original_preview_message(tmp_path):
    cog = _cog(tmp_path)
    config = {"title": "Old", "text": "Old", "image_url": None}
    message = FakeMessage()
    modal = WelcomeEditModal(cog, config, message=message)
    modal.title_input._value = "New"
    modal.text_input._value = "New text"
    modal.image_input._value = ""

    interaction = FakeInteraction(FakeUser(id=1))
    await modal.on_submit(interaction)

    assert message.edits[0].title == "New"


async def test_on_member_join_posts_to_the_configured_welcome_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "welcome_channel_id", "555")
    cog = _cog(tmp_path)
    from services.welcome_config import save_welcome_config

    save_welcome_config(cog._welcome_config_path, "Salut", "Bienvenue {membre}", None)

    channel = FakeChannel(id=555)
    guild = FakeGuild(channels={555: channel})
    member = Mock(spec=discord.Member)
    member.guild = guild
    member.mention = "<@777>"

    await cog.on_member_join(member)

    assert len(channel.sent) == 1
    assert channel.sent[0].description == "Bienvenue <@777>"


async def test_on_member_join_does_nothing_when_no_channel_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "welcome_channel_id", None)
    cog = _cog(tmp_path)
    guild = FakeGuild(channels={})
    member = Mock(spec=discord.Member)
    member.guild = guild

    await cog.on_member_join(member)  # must not raise


async def test_on_member_join_does_nothing_when_configured_channel_is_not_on_this_guild(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "welcome_channel_id", "555")
    cog = _cog(tmp_path)
    guild = FakeGuild(channels={})
    member = Mock(spec=discord.Member)
    member.guild = guild

    await cog.on_member_join(member)  # must not raise
