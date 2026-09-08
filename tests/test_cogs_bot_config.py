from unittest.mock import Mock

import discord

from cogs.bot_config import (
    BotConfigCog,
    ConfigEditModal,
    ConfigEntrySelect,
    ConfigEntrySelectView,
    ConfigOverviewView,
    ConfigSectionSelect,
    ConfigSectionSelectView,
)


class FakeRole:
    def __init__(self, id, mention):
        self.id = id
        self.mention = mention


class FakeChannel:
    def __init__(self, id, mention):
        self.id = id
        self.mention = mention


class FakeGuild:
    def __init__(self, roles=None, channels=None, name="Guild"):
        self._roles = roles or {}
        self._channels = channels or {}
        self.name = name

    def get_role(self, role_id):
        return self._roles.get(role_id)

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


def FakeUser(id, is_admin=True):
    member = Mock(spec=discord.Member)
    member.id = id
    member.guild_permissions = discord.Permissions(administrator=is_admin)
    return member


class FakeMessage:
    def __init__(self, guild=None):
        self.guild = guild
        self.edits = []

    async def edit(self, embed=None, **kwargs):
        self.edits.append(embed)


class FakeContext:
    def __init__(self, guild=None, author=None):
        self.guild = guild
        self.author = author or FakeUser(id=1)
        self.sent = []

    async def send(self, embed=None, view=None, ephemeral=False):
        message = FakeMessage(guild=self.guild)
        self.sent.append((embed, view, ephemeral))
        return message


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.modals = []
        self.edits = []

    async def send_message(self, content=None, view=None, ephemeral=False):
        self.messages.append({"content": content, "view": view, "ephemeral": ephemeral})

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def edit_message(self, content=None, view=None):
        self.edits.append({"content": content, "view": view})


class FakeInteraction:
    def __init__(self, user, guild=None):
        self.user = user
        self.guild = guild
        self.response = FakeResponse()


class FakeBot:
    def __init__(self):
        pass


def _cog(tmp_path, content):
    role_config_path = tmp_path / "leaderboard_roles.txt"
    role_config_path.write_text(content, encoding="utf-8")
    cog = BotConfigCog(bot=FakeBot())
    cog._role_config_path = role_config_path
    # Never let a test touch the real .env: default to an isolated per-test file.
    cog._env_path = tmp_path / ".env"
    cog._env_path.write_text("", encoding="utf-8")
    return cog


async def test_config_reports_unconfigured_settings_when_nothing_is_set(tmp_path, monkeypatch):
    from config.settings import settings

    for field in (
        "level_up_channel_id",
        "alt_account_alert_channel_id",
        "role_actif_id",
        "role_legendaire_id",
        "prestige_1_role_id",
    ):
        monkeypatch.setattr(settings, field, None)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    ctx = FakeContext(guild=FakeGuild())

    await cog.config.callback(cog, ctx)

    embed, view, _ = ctx.sent[0]
    channels_field = next(f for f in embed.fields if f.name == "Salons")
    assert "❌ non configuré" in channels_field.value
    assert isinstance(view, ConfigOverviewView)


async def test_config_resolves_configured_role_to_its_mention(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", "555")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    guild = FakeGuild(roles={555: FakeRole(555, "<@&555>")})
    ctx = FakeContext(guild=guild)

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    rewards_field = next(f for f in embed.fields if f.name == "Rôles de récompense par niveau")
    assert "<@&555>" in rewards_field.value


async def test_config_flags_a_configured_id_that_no_longer_resolves_on_the_server(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", "555")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    ctx = FakeContext(guild=FakeGuild())

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    rewards_field = next(f for f in embed.fields if f.name == "Rôles de récompense par niveau")
    assert "introuvable" in rewards_field.value


async def test_config_resolves_leaderboard_roles_from_the_config_file(tmp_path, monkeypatch):
    from config.settings import settings

    for field in ("role_actif_id", "role_legendaire_id"):
        monkeypatch.setattr(settings, field, None)

    cog = _cog(tmp_path, "roi_du_chat: 42\nmaitre_vocal:\ntop_10:\n")
    guild = FakeGuild(roles={42: FakeRole(42, "<@&42>")})
    ctx = FakeContext(guild=guild)

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    leaderboard_field = next(f for f in embed.fields if f.name == "Classement hebdomadaire")
    assert "<@&42>" in leaderboard_field.value


async def test_edit_button_rejects_non_admin(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    view = ConfigOverviewView(cog, author_id=1)
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=False))

    await view.edit_button.callback(interaction)

    assert "administrateur" in interaction.response.messages[0]["content"]
    assert interaction.response.messages[0]["view"] is None


async def test_edit_button_rejects_wrong_user(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    view = ConfigOverviewView(cog, author_id=1)
    interaction = FakeInteraction(user=FakeUser(id=2, is_admin=True))

    await view.edit_button.callback(interaction)

    assert "administrateur" in interaction.response.messages[0]["content"]


async def test_edit_button_opens_section_select_for_admin_author(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    view = ConfigOverviewView(cog, author_id=1)
    view.message = FakeMessage(guild=FakeGuild())
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True))

    await view.edit_button.callback(interaction)

    sent = interaction.response.messages[0]
    assert isinstance(sent["view"], ConfigSectionSelectView)
    assert sent["ephemeral"] is True


async def test_section_select_never_exceeds_discords_25_option_limit(tmp_path):
    # Regression test: a flat list of every setting across every section
    # previously blew past Discord's 25-option cap on a single select menu
    # (28 settings at the time this broke) and made the whole button fail
    # with "interaction failed". The two-step section -> entry picker keeps
    # each individual select well under that limit.
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()

    section_select = ConfigSectionSelect(cog, None, author_id=1, sections=sections)
    assert 1 <= len(section_select.options) <= 25

    for section in sections:
        entry_select = ConfigEntrySelect(cog, None, author_id=1, section=section)
        assert 1 <= len(entry_select.options) <= 25


async def test_section_select_opens_the_entry_select_for_the_chosen_category(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    rewards_section = next(s for s in sections if s.title == "Rôles de récompense par niveau")
    message = FakeMessage(guild=FakeGuild())
    select = ConfigSectionSelect(cog, message, author_id=1, sections=sections)
    select._values = [rewards_section.title]
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True))

    await select.callback(interaction)

    edit = interaction.response.edits[0]
    assert isinstance(edit["view"], ConfigEntrySelectView)


async def test_section_select_rejects_other_user(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    select = ConfigSectionSelect(cog, None, author_id=1, sections=sections)
    select._values = [sections[0].title]
    interaction = FakeInteraction(user=FakeUser(id=2, is_admin=True))

    await select.callback(interaction)

    assert "pas le tien" in interaction.response.messages[0]["content"]
    assert not interaction.response.edits


async def test_entry_select_opens_modal_for_chosen_entry(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    rewards_section = next(s for s in sections if s.title == "Rôles de récompense par niveau")
    message = FakeMessage(guild=FakeGuild())
    select = ConfigEntrySelect(cog, message, author_id=1, section=rewards_section)
    select._values = ["role_actif_id"]
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True))

    await select.callback(interaction)

    assert len(interaction.response.modals) == 1
    modal = interaction.response.modals[0]
    assert isinstance(modal, ConfigEditModal)
    assert modal.entry.key == "role_actif_id"


async def test_entry_select_rejects_other_user(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    rewards_section = next(s for s in sections if s.title == "Rôles de récompense par niveau")
    select = ConfigEntrySelect(cog, None, author_id=1, section=rewards_section)
    select._values = ["role_actif_id"]
    interaction = FakeInteraction(user=FakeUser(id=2, is_admin=True))

    await select.callback(interaction)

    assert "pas le tien" in interaction.response.messages[0]["content"]
    assert not interaction.response.modals


async def test_modal_submit_updates_settings_value_and_refreshes_message(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", None)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "role_actif_id")
    role_id = 111111111111111111
    guild = FakeGuild(roles={role_id: FakeRole(role_id, f"<@&{role_id}>")})
    message = FakeMessage(guild=guild)

    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, message)
    modal.value_input._value = str(role_id)
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=guild)

    await modal.on_submit(interaction)

    assert settings.role_actif_id == str(role_id)
    assert f"ROLE_ACTIF_ID={role_id}" in env_path.read_text(encoding="utf-8")
    assert len(message.edits) == 1
    assert "✅" in interaction.response.messages[0]["content"]

    monkeypatch.setattr(settings, "role_actif_id", None)


async def test_modal_submit_clears_value_when_input_is_empty(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", "999")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "role_actif_id")

    env_path = tmp_path / ".env"
    env_path.write_text("ROLE_ACTIF_ID=999\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = ""
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert settings.role_actif_id is None
    assert "ROLE_ACTIF_ID=" in env_path.read_text(encoding="utf-8")
    assert "999" not in env_path.read_text(encoding="utf-8")
    assert "effacé" in interaction.response.messages[0]["content"]

    monkeypatch.setattr(settings, "role_actif_id", None)


async def test_modal_submit_rejects_invalid_value(tmp_path):
    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "role_actif_id")

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = "not-an-id"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert "invalide" in interaction.response.messages[0]["content"]


async def test_config_shows_the_raw_amount_for_daily_and_work_entries(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "daily_amount", 100)
    monkeypatch.setattr(settings, "work_amount", 125)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    ctx = FakeContext(guild=FakeGuild())

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    economie_field = next(f for f in embed.fields if f.name == "Économie")
    assert "100" in economie_field.value
    assert "125" in economie_field.value
    assert "non configuré" not in economie_field.value


async def test_modal_submit_updates_an_amount_setting(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "work_amount", 125)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "work_amount")

    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, None)
    assert modal.value_input.default == "125"
    modal.value_input._value = "300"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert settings.work_amount == 300
    assert "WORK_AMOUNT=300" in env_path.read_text(encoding="utf-8")
    assert "✅" in interaction.response.messages[0]["content"]

    monkeypatch.setattr(settings, "work_amount", 125)


async def test_modal_submit_accepts_zero_as_a_valid_amount(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "work_amount", 125)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "work_amount")

    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = "0"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert settings.work_amount == 0
    assert "WORK_AMOUNT=0" in env_path.read_text(encoding="utf-8")

    monkeypatch.setattr(settings, "work_amount", 125)


async def test_modal_submit_rejects_a_negative_amount(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "work_amount", 125)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "work_amount")

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = "-10"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert "invalide" in interaction.response.messages[0]["content"]
    assert settings.work_amount == 125

    monkeypatch.setattr(settings, "work_amount", 125)


async def test_config_never_displays_the_raw_secret_value(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-super-secret-value")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    ctx = FakeContext(guild=FakeGuild())

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    integrations_field = next(f for f in embed.fields if f.name == "Intégrations IA")
    assert "sk-super-secret-value" not in integrations_field.value
    assert "✅ configurée" in integrations_field.value

    monkeypatch.setattr(settings, "deepseek_api_key", None)


async def test_config_flags_a_missing_secret_as_unconfigured(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", None)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    ctx = FakeContext(guild=FakeGuild())

    await cog.config.callback(cog, ctx)

    embed, _, _ = ctx.sent[0]
    integrations_field = next(f for f in embed.fields if f.name == "Intégrations IA")
    assert "❌ non configurée" in integrations_field.value


async def test_select_description_never_leaks_a_configured_secret(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-super-secret-value")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    integrations_section = next(s for s in sections if s.title == "Intégrations IA")
    message = FakeMessage(guild=FakeGuild())
    select = ConfigEntrySelect(cog, message, author_id=1, section=integrations_section)

    option = next(o for o in select.options if o.value == "deepseek_api_key")
    assert "sk-super-secret-value" not in option.description
    assert option.description == "Configurée"

    monkeypatch.setattr(settings, "deepseek_api_key", None)


async def test_modal_for_secret_never_prefills_the_current_value(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-super-secret-value")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "deepseek_api_key")

    modal = ConfigEditModal(cog, entry, None)

    assert modal.value_input.default == ""

    monkeypatch.setattr(settings, "deepseek_api_key", None)


async def test_modal_submit_sets_a_secret_without_echoing_it_back(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", None)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "deepseek_api_key")

    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = "sk-new-secret-value"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert settings.deepseek_api_key == "sk-new-secret-value"
    assert "DEEPSEEK_API_KEY=sk-new-secret-value" in env_path.read_text(encoding="utf-8")
    response_content = interaction.response.messages[0]["content"]
    assert "sk-new-secret-value" not in response_content
    assert "configurée" in response_content

    monkeypatch.setattr(settings, "deepseek_api_key", None)


async def test_modal_submit_clears_a_secret_when_input_is_empty(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-old-value")

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "deepseek_api_key")

    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=sk-old-value\n", encoding="utf-8")
    cog._env_path = env_path

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = ""
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert settings.deepseek_api_key is None
    assert "effacée" in interaction.response.messages[0]["content"]

    monkeypatch.setattr(settings, "deepseek_api_key", None)


async def test_modal_submit_updates_leaderboard_role_via_file(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", None)

    cog = _cog(tmp_path, "roi_du_chat:\nmaitre_vocal:\ntop_10:\n")
    sections = cog._sections()
    entry = next(e for s in sections for e in s.entries if e.key == "roi_du_chat")

    modal = ConfigEditModal(cog, entry, None)
    modal.value_input._value = "<@&222222222222222222>"
    interaction = FakeInteraction(user=FakeUser(id=1, is_admin=True), guild=FakeGuild())

    await modal.on_submit(interaction)

    assert "roi_du_chat:222222222222222222" in cog._role_config_path.read_text(encoding="utf-8")
