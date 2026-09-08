from datetime import date

from cogs.quests import QuestCog
from models.quests import Quest
from models.users import User
from services.quests import increment_quest_progress
from config.settings import settings


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeGuild:
    def __init__(self):
        self.id = settings.guild_id


class FakeContext:
    def __init__(self, author):
        self.author = author
        self.guild = FakeGuild()
        self.sent = []

    async def send(self, content=None, *, embed=None):
        self.sent.append(embed if embed is not None else content)


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


async def test_quest_command_shows_all_quests_with_progress(db_session, monkeypatch):
    user = User(guild_id=settings.guild_id, user_id=9201, username="Quester")
    quest_a = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    quest_b = Quest(key="channels_3", description="Écrire dans 3 salons", target_count=3, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest_a, quest_b])
    await db_session.flush()
    await increment_quest_progress(db_session, settings.guild_id, user.user_id, "channels_3", 3, date.today())
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = QuestCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_today", lambda: date.today())
    ctx = FakeContext(FakeUser(id=9201, display_name="Quester"))

    await cog.quest.callback(cog, ctx)

    embed = ctx.sent[0]
    fields = {f.name: f.value for f in embed.fields}
    assert any("Envoyer 25 messages" in name and "0/25" in value for name, value in fields.items())
    assert any("Écrire dans 3 salons" in name and "✅" in name and "3/3" in value for name, value in fields.items())


async def test_quest_command_shows_placeholder_when_no_quests(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = QuestCog(bot=FakeBot(session_factory))
    ctx = FakeContext(FakeUser(id=9202, display_name="Nobody"))

    await cog.quest.callback(cog, ctx)

    embed = ctx.sent[0]
    assert "Aucune quête" in embed.description
