from datetime import date, datetime, timezone

from config.settings import settings
from cogs.leveling import LevelingCog
from models.quests import Quest
from services.spam_guard import MAX_MESSAGES_IN_WINDOW
from services.xp import EVENT_PARTICIPATION_XP

OLD_ACCOUNT_CREATED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeAuthor:
    def __init__(self, id, display_name, bot=False, created_at=OLD_ACCOUNT_CREATED_AT):
        self.id = id
        self.display_name = display_name
        self.bot = bot
        self.created_at = created_at
        self.mention = f"<@{id}>"

    def __str__(self):
        return self.display_name


class _FakeChannel:
    def __init__(self, id, mention=None):
        self.id = id
        self.mention = mention if mention is not None else f"<#{id}>"


class FakeMessage:
    def __init__(self, author, guild, channel=None):
        self.author = author
        self.guild = guild
        self.channel = channel if channel is not None else _FakeChannel(id=1)


class FakeReaction:
    def __init__(self, message):
        self.message = message


class FakeGuild:
    def __init__(self, id=None, channels=None):
        self.id = id if id is not None else settings.guild_id
        self._channels = channels or {}

    def get_role(self, role_id):
        return None

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class FakeMember:
    def __init__(self, id, display_name, created_at=OLD_ACCOUNT_CREATED_AT):
        self.id = id
        self.display_name = display_name
        self.added_roles = []
        self.created_at = created_at

    async def add_roles(self, role):
        self.added_roles.append(role)


class FakeContext:
    def __init__(self, guild):
        self.guild = guild
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory


async def test_on_message_awards_xp_to_human_author(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12001, display_name="Chatter")
    message = FakeMessage(author=author, guild=FakeGuild())

    await cog.on_message(message)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12001))
    assert level_row is not None
    assert 5 <= level_row.xp <= 15


async def test_on_message_ignores_bots(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12002, display_name="RobotFriend", bot=True)
    message = FakeMessage(author=author, guild=FakeGuild())

    await cog.on_message(message)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12002))
    assert level_row is None


async def test_on_reaction_add_awards_xp_to_message_author(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12010, display_name="Poster")
    reactor = FakeAuthor(id=12011, display_name="Reactor")
    message = FakeMessage(author=author, guild=FakeGuild())
    reaction = FakeReaction(message=message)

    await cog.on_reaction_add(reaction, reactor)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12010))
    assert level_row is not None
    assert level_row.xp == 2


async def test_on_reaction_add_skips_self_reaction(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12012, display_name="SelfReactor")
    message = FakeMessage(author=author, guild=FakeGuild())
    reaction = FakeReaction(message=message)

    await cog.on_reaction_add(reaction, author)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12012))
    assert level_row is None


async def test_on_reaction_remove_subtracts_xp_without_triggering_award(db_session, monkeypatch):
    from models.levels import Level

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("award_xp must not be called on reaction remove")

    monkeypatch.setattr("cogs.leveling.award_xp", _fail_if_called)

    db_session.add(Level(guild_id=settings.guild_id, user_id=12013, xp=10, level=0, prestige=0, last_key_drop_level=0))
    await db_session.flush()

    author = FakeAuthor(id=12013, display_name="Existing")
    reactor = FakeAuthor(id=12014, display_name="Remover")
    message = FakeMessage(author=author, guild=FakeGuild())
    reaction = FakeReaction(message=message)

    await cog.on_reaction_remove(reaction, reactor)

    level_row = await db_session.get(Level, (settings.guild_id, 12013))
    assert level_row.xp == 8
    assert level_row.level == 0


async def test_event_participation_awards_bonus_xp_and_confirms_ephemerally(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    guild = FakeGuild()
    ctx = FakeContext(guild=guild)
    member = FakeMember(id=12020, display_name="EventGoer")

    await cog.event_participation.callback(cog, ctx, member)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12020))
    assert level_row is not None
    assert level_row.xp == EVENT_PARTICIPATION_XP

    assert len(ctx.sent) == 1
    content = ctx.sent[0]
    assert "EventGoer" in content


async def test_event_participation_awards_full_bonus_even_for_a_recently_created_account(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    guild = FakeGuild()
    ctx = FakeContext(guild=guild)
    member = FakeMember(id=12021, display_name="FreshAlt", created_at=datetime.now(timezone.utc))

    await cog.event_participation.callback(cog, ctx, member)

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 12021))
    # A deliberate admin grant must not be silently cut by the alt-account penalty.
    assert level_row.xp == EVENT_PARTICIPATION_XP


async def test_on_message_increments_messages_quest_and_grants_reward_on_completion(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: date(2026, 7, 21))

    db_session.add(Quest(key="messages_25", description="d", target_count=2, xp_reward=10, coins_reward=20))
    await db_session.commit()

    author = FakeAuthor(id=22001, display_name="Grinder")
    channel_a = _FakeChannel(id=500)
    channel_b = _FakeChannel(id=600)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel_a))
    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel_b))

    from models.quests import UserQuest
    from models.economy import Economy

    result = await db_session.execute(
        __import__("sqlalchemy").select(UserQuest).where(UserQuest.user_id == 22001)
    )
    user_quest = result.scalar_one()
    assert user_quest.completed is True

    economy = await db_session.get(Economy, (settings.guild_id, 22001))
    assert economy.balance == 20


async def test_on_message_increments_channels_quest_only_for_new_channels(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: date(2026, 7, 21))

    db_session.add(Quest(key="channels_3", description="d", target_count=2, xp_reward=10, coins_reward=20))
    await db_session.commit()

    author = FakeAuthor(id=22002, display_name="Explorer")
    same_channel = _FakeChannel(id=700)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=same_channel))
    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=same_channel))

    from sqlalchemy import select
    from models.quests import UserQuest

    result = await db_session.execute(select(UserQuest).where(UserQuest.user_id == 22002))
    user_quest = result.scalar_one()
    assert user_quest.progress == 1  # second message was the same channel, no increment


from datetime import date as _date
from config.settings import settings


async def test_on_message_increments_message_stat_for_the_day(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: _date(2026, 7, 21))

    author = FakeAuthor(id=24001, display_name="Statful")
    channel = _FakeChannel(id=800)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))
    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))

    from sqlalchemy import select
    from models.stats import MessageStat

    result = await db_session.execute(
        select(MessageStat).where(MessageStat.user_id == 24001, MessageStat.date == _date(2026, 7, 21))
    )
    stat = result.scalar_one()
    assert stat.count == 2


async def test_on_message_suppresses_xp_after_five_rapid_messages_but_keeps_tracking_stats(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: date(2026, 7, 21))
    cog.spam_guard._clock = lambda: cog._fake_now
    cog._fake_now = 0.0

    author = FakeAuthor(id=23001, display_name="Spammer")
    channel = _FakeChannel(id=900)

    from models.levels import Level

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))
        cog._fake_now += 0.5  # well under the 5s window between each message

    xp_after_burst = (await db_session.get(Level, (settings.guild_id, 23001))).xp
    assert 5 * (MAX_MESSAGES_IN_WINDOW - 1) <= xp_after_burst <= 15 * (MAX_MESSAGES_IN_WINDOW - 1)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))  # 5th, triggers the mute

    from models.stats import MessageStat
    from sqlalchemy import select

    level_row = await db_session.get(Level, (settings.guild_id, 23001))
    assert level_row.xp == 0  # the triggering message earned nothing, and the burst's XP was clawed back

    result = await db_session.execute(
        select(MessageStat).where(MessageStat.user_id == 23001, MessageStat.date == date(2026, 7, 21))
    )
    stat = result.scalar_one()
    assert stat.count == MAX_MESSAGES_IN_WINDOW  # every message still counted for stats, XP or not


async def test_on_message_resumes_awarding_xp_after_a_gap_wider_than_the_window(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.spam_guard._clock = lambda: cog._fake_now
    cog._fake_now = 0.0

    author = FakeAuthor(id=23002, display_name="NormalPace")
    channel = _FakeChannel(id=901)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))
        cog._fake_now += 0.5

    from models.levels import Level

    xp_after_burst = (await db_session.get(Level, (settings.guild_id, 23002))).xp

    cog._fake_now += 10.0  # gap wider than the 5s window
    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))

    xp_after_gap = (await db_session.get(Level, (settings.guild_id, 23002))).xp
    assert 5 <= xp_after_gap - xp_after_burst <= 15  # the post-gap message awarded XP again


async def test_on_message_mutes_xp_for_ten_minutes_and_claws_back_the_burst_xp(db_session, monkeypatch):
    monkeypatch.setattr(settings, "admin_log_channel_id", "42")
    monkeypatch.setattr("cogs.leveling.roll_message_xp", lambda: 10)
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.spam_guard._clock = lambda: cog._fake_now
    cog._fake_now = 0.0

    log_channel = _FakeLogChannel(id=42)
    guild = FakeGuild(channels={42: log_channel})
    author = FakeAuthor(id=23004, display_name="Flooder")
    channel = _FakeChannel(id=902)

    for _ in range(MAX_MESSAGES_IN_WINDOW - 1):
        await cog.on_message(FakeMessage(author=author, guild=guild, channel=channel))
        cog._fake_now += 0.5
    assert log_channel.sent == []  # not muted yet

    from models.levels import Level

    xp_before_trigger = (await db_session.get(Level, (settings.guild_id, 23004))).xp
    assert xp_before_trigger == 10 * (MAX_MESSAGES_IN_WINDOW - 1)

    await cog.on_message(FakeMessage(author=author, guild=guild, channel=channel))  # 5th triggers the mute

    assert len(log_channel.sent) == 1
    embed = log_channel.sent[0]
    assert "10 minutes" in embed.fields[2].value
    assert f"{xp_before_trigger} XP" in embed.fields[2].value

    level_row = await db_session.get(Level, (settings.guild_id, 23004))
    assert level_row.xp == 0  # the burst's XP was clawed back

    cog._fake_now += 5.0  # still muted, well under 600s
    await cog.on_message(FakeMessage(author=author, guild=guild, channel=channel))
    assert len(log_channel.sent) == 1  # mute is not re-logged on every suppressed message

    cog._fake_now += 600.0  # mute duration elapses
    await cog.on_message(FakeMessage(author=author, guild=guild, channel=channel))

    level_row = await db_session.get(Level, (settings.guild_id, 23004))
    assert level_row.xp == 10  # XP gain resumed after the mute expired


class _FakeLogChannel:
    def __init__(self, id):
        self.id = id
        self.sent = []

    async def send(self, embed=None):
        self.sent.append(embed)


async def test_on_message_grants_no_xp_in_a_channel_excluded_via_unxp(db_session, monkeypatch):
    from services.no_xp_channels import add_no_xp_channel

    await add_no_xp_channel(db_session, settings.guild_id, 909)

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=23003, display_name="Excluded")
    channel = _FakeChannel(id=909)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))

    from models.levels import Level

    level_row = await db_session.get(Level, (settings.guild_id, 23003))
    assert level_row is None  # no XP means the user's level row was never created


class _FakeSessionContext:
    """Minimal async context manager so cog code can do `async with self._session() as session`."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False
