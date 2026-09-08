from datetime import date

from cogs.leaderboard import LeaderboardCog
from models.economy import Economy
from models.levels import Level
from models.users import User
from config.settings import settings


class FakeGuild:
    def __init__(self):
        self.id = settings.guild_id


class FakeContext:
    def __init__(self):
        self.guild = FakeGuild()
        self.messages = []

    async def send(self, content=None, embed=None):
        self.messages.append(embed if embed is not None else content)


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def get_cog(self, name):
        return None


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


async def test_leaderboard_xp_lists_top_users(db_session):
    db_session.add_all([User(guild_id=settings.guild_id, user_id=27001, username="Low"), User(guild_id=settings.guild_id, user_id=27002, username="High")])
    await db_session.flush()
    db_session.add_all(
        [Level(guild_id=settings.guild_id, user_id=27001, xp=100, level=1, prestige=0), Level(guild_id=settings.guild_id, user_id=27002, xp=500, level=2, prestige=0)]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.leaderboard.callback(cog, ctx, "xp")

    embed = ctx.messages[0]
    assert "Classement" in embed.title
    assert "High" in embed.description
    assert embed.description.index("High") < embed.description.index("Low")
    assert "🥇" in embed.description


async def test_leaderboard_coins_lists_top_users(db_session):
    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=27003, username="Poor"),
            User(guild_id=settings.guild_id, user_id=27004, username="Rich"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Economy(guild_id=settings.guild_id, user_id=27003, balance=50),
            Economy(guild_id=settings.guild_id, user_id=27004, balance=5000),
        ]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.leaderboard.callback(cog, ctx, "coins")

    embed = ctx.messages[0]
    assert "Rich" in embed.description
    assert embed.description.index("Rich") < embed.description.index("Poor")
    assert "🥇" in embed.description


async def test_leaderboard_reports_no_data_for_empty_ranking(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.leaderboard.callback(cog, ctx, "messages")

    embed = ctx.messages[0]
    assert "Aucune donnée" in embed.description


async def test_leaderboard_refreshes_classement_roles(db_session):
    refreshed = []

    class FakeClassement:
        async def refresh_roles(self, guild):
            refreshed.append(guild.id)

    classement = FakeClassement()

    class BotWithClassement(FakeBot):
        def get_cog(self, name):
            return classement if name == "ClassementRolesCog" else None

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=BotWithClassement(session_factory))
    ctx = FakeContext()

    await cog.leaderboard.callback(cog, ctx, "xp")

    assert refreshed == [ctx.guild.id]


async def test_leaderboard_ignores_missing_classement_cog(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))  # get_cog -> None
    ctx = FakeContext()

    await cog.leaderboard.callback(cog, ctx, "coins")

    assert len(ctx.messages) == 1  # l'embed s'affiche normalement
