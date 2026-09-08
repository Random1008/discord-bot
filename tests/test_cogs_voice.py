from datetime import datetime, timezone

from config.settings import settings
from cogs.voice import VoiceCog

OLD_ACCOUNT_CREATED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeMember:
    def __init__(
        self, id, display_name, bot=False, self_mute=False, self_deaf=False, created_at=OLD_ACCOUNT_CREATED_AT
    ):
        self.id = id
        self.display_name = display_name
        self.bot = bot
        self.voice = FakeVoiceState(channel=None, self_mute=self_mute, self_deaf=self_deaf)
        self.created_at = created_at
        self.guild = FakeGuild()


class FakeChannelMembers:
    def __init__(self, members, id=100):
        self.members = members
        self.id = id


class FakeVoiceState:
    def __init__(self, channel, self_mute=False, self_deaf=False):
        self.channel = channel
        self.self_mute = self_mute
        self.self_deaf = self_deaf


class FakeContext:
    def __init__(self, prefix="!"):
        self.prefix = prefix
        self.guild = FakeGuild()
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


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


async def test_on_voice_state_update_awards_xp_after_ten_minutes(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=13001, display_name="Talker")
    other = FakeMember(id=13002, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 13001))
    assert level_row is not None
    assert level_row.xp == 10


from datetime import date

from models.quests import Quest


async def test_on_voice_state_update_increments_voice_quest_and_grants_reward(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: date(2026, 7, 21))
    cog.tracker._clock = lambda: cog._fake_now

    db_session.add(Quest(key="voice_60min", description="d", target_count=10, xp_reward=15, coins_reward=25))
    await db_session.commit()

    cog._fake_now = 0.0
    member = FakeMember(id=23001, display_name="Talker")
    other = FakeMember(id=23002, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from sqlalchemy import select
    from models.quests import UserQuest
    from models.economy import Economy

    result = await db_session.execute(select(UserQuest).where(UserQuest.user_id == 23001))
    user_quest = result.scalar_one()
    assert user_quest.progress == 10  # 600 payable seconds -> 10 minutes
    assert user_quest.completed is True

    economy = await db_session.get(Economy, (settings.guild_id, 23001))
    assert economy.balance == 25


from datetime import date as _date
from config.settings import settings


async def test_on_voice_state_update_increments_voice_stat_for_the_day(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: _date(2026, 7, 21))
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=25001, display_name="Statful")
    other = FakeMember(id=25002, display_name="Other")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from sqlalchemy import select
    from models.stats import VoiceStat

    result = await db_session.execute(
        select(VoiceStat).where(VoiceStat.user_id == 25001, VoiceStat.date == _date(2026, 7, 21))
    )
    stat = result.scalar_one()
    assert stat.seconds == 600


async def test_no_payout_when_the_other_member_is_muted(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=26001, display_name="Talker")
    muted_other = FakeMember(id=26002, display_name="SilentAlt", self_mute=True)
    channel = FakeChannelMembers(members=[member, muted_other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 26001))
    assert level_row is None  # muted alt doesn't count towards the >=2 humans threshold


async def test_no_payout_when_the_member_itself_is_muted(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=26003, display_name="MutedSelf", self_mute=True)
    other = FakeMember(id=26004, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(
        member, FakeVoiceState(None), FakeVoiceState(channel, self_mute=True)
    )

    cog._fake_now = 650.0
    await cog.on_voice_state_update(
        member, FakeVoiceState(channel, self_mute=True), FakeVoiceState(None, self_mute=True)
    )

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 26003))
    assert level_row is None  # muting yourself suppresses your own payout


async def test_no_payout_when_deafened_members_are_excluded_from_the_count(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=26005, display_name="Talker")
    deafened_other = FakeMember(id=26006, display_name="DeafenedAlt", self_deaf=True)
    channel = FakeChannelMembers(members=[member, deafened_other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 26005))
    assert level_row is None


async def test_no_payout_in_a_channel_excluded_via_unxp(db_session, monkeypatch):
    from services.no_xp_channels import add_no_xp_channel

    await add_no_xp_channel(db_session, settings.guild_id, 100)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=26007, display_name="Talker")
    other = FakeMember(id=26008, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other], id=100)  # matches the excluded channel id

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 26007))
    assert level_row is None


async def test_unxp_command_excludes_a_channel(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.unxp_channel.callback(cog, ctx, "555")

    from services.no_xp_channels import is_no_xp_channel

    assert await is_no_xp_channel(db_session, settings.guild_id, 555) is True
    assert "555" in ctx.sent[0]


async def test_unxp_command_reports_already_excluded(db_session):
    from services.no_xp_channels import add_no_xp_channel

    await add_no_xp_channel(db_session, settings.guild_id, 555)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.unxp_channel.callback(cog, ctx, "555")

    assert "déjà" in ctx.sent[0]


async def test_unxp_command_lists_excluded_channels(db_session):
    from services.no_xp_channels import add_no_xp_channel

    await add_no_xp_channel(db_session, settings.guild_id, 555)
    await add_no_xp_channel(db_session, settings.guild_id, 777)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.unxp_channel.callback(cog, ctx, "list")

    assert "555" in ctx.sent[0]
    assert "777" in ctx.sent[0]


async def test_unxp_command_rejects_non_numeric_non_list_argument():
    session_factory = lambda: None
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.unxp_channel.callback(cog, ctx, "not-a-number")

    assert "Usage" in ctx.sent[0]


async def test_xp_command_removes_a_channel_from_the_exclusion_list(db_session):
    from services.no_xp_channels import add_no_xp_channel, is_no_xp_channel

    await add_no_xp_channel(db_session, settings.guild_id, 555)
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.xp_channel.callback(cog, ctx, 555)

    assert await is_no_xp_channel(db_session, settings.guild_id, 555) is False
    assert "555" in ctx.sent[0]


async def test_xp_command_reports_when_channel_was_not_excluded(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.xp_channel.callback(cog, ctx, 555)

    assert "n'était pas exclu" in ctx.sent[0]


class FakeGuildWithVoiceChannels:
    def __init__(self, id, voice_channels):
        self.id = id
        self.voice_channels = voice_channels


async def test_sync_voice_activity_awards_xp_without_any_voice_state_event(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    member = FakeMember(id=14001, display_name="Talker")
    other = FakeMember(id=14002, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other])
    member.voice = FakeVoiceState(channel=channel)
    other.voice = FakeVoiceState(channel=channel)
    guild = FakeGuildWithVoiceChannels(id=settings.guild_id, voice_channels=[channel])
    member.guild = guild
    other.guild = guild

    bot = FakeBot(session_factory)
    bot.guilds = [guild]
    cog = VoiceCog(bot=bot)
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    await cog.sync_voice_activity()

    cog._fake_now = 650.0
    await cog.sync_voice_activity()

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 14001))
    assert level_row is not None
    assert level_row.xp == 10


async def test_sync_voice_activity_skips_channels_with_no_human_members(db_session):
    channel = FakeChannelMembers(members=[FakeMember(id=14003, display_name="Bot", bot=True)])
    guild = FakeGuildWithVoiceChannels(id=settings.guild_id, voice_channels=[channel])

    bot = FakeBot(lambda: _FakeSessionContext(db_session))
    bot.guilds = [guild]
    cog = VoiceCog(bot=bot)

    await cog.sync_voice_activity()
