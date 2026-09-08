from config.settings import settings
from cogs.tour import TourCog, _sanitize_channel_name, _tower_channel_name
from models.users import User
import services.rpg_db as db


class _FakeAvatar:
    url = "https://cdn.example.com/avatar.png"


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.display_avatar = _FakeAvatar()


class FakeGuild:
    def __init__(self, id=None, members=None):
        self.id = id if id is not None else settings.guild_id
        self.members = members or []

    def get_member(self, user_id):
        for m in self.members:
            if m.id == user_id:
                return m
        return None


class FakeContext:
    def __init__(self, author, guild=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.messages = []
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.messages.append(content)
        self.sent.append(kwargs)


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
    return TourCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_show_or_reports_zero_for_new_player(db_session):
    cog = _cog(db_session)
    assert await cog._show_or(settings.guild_id, 70001) == 0


async def test_show_or_reports_existing_balance(db_session):
    user = User(guild_id=settings.guild_id, user_id=70002, username="Banked")
    db_session.add(user)
    await db_session.flush()
    await db.add_or_balance(db_session, settings.guild_id, 70002, 250)
    await db_session.commit()

    cog = _cog(db_session)
    assert await cog._show_or(settings.guild_id, 70002) == 250


async def test_do_convert_rejects_non_positive_amount(db_session):
    cog = _cog(db_session)
    msg = await cog._do_convert(settings.guild_id, 70003, 0)
    assert "positif" in msg


async def test_do_convert_rejects_insufficient_or(db_session):
    cog = _cog(db_session)
    msg = await cog._do_convert(settings.guild_id, 70004, 100)
    assert "assez d'Or" in msg


async def test_do_convert_success_moves_balance(db_session):
    from models.economy import Economy

    user = User(guild_id=settings.guild_id, user_id=70005, username="Converter2")
    db_session.add(user)
    await db_session.flush()
    await db.add_or_balance(db_session, settings.guild_id, 70005, 400)
    await db_session.commit()

    cog = _cog(db_session)
    msg = await cog._do_convert(settings.guild_id, 70005, 150)

    assert "150" in msg
    economy = await db_session.get(Economy, (settings.guild_id, 70005))
    assert economy.balance == 150
    assert await db.get_or_balance(db_session, settings.guild_id, 70005) == 250


async def test_show_codex_reports_no_discoveries_for_new_player(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=70006, display_name="Explorer"))
    await cog._show_codex(ctx, settings.guild_id, 70006)
    assert "0/" in ctx.messages[0]


async def test_show_or_is_isolated_per_guild(db_session):
    other_guild_id = settings.guild_id + 1
    user_here = User(guild_id=settings.guild_id, user_id=70007, username="Traveler")
    user_there = User(guild_id=other_guild_id, user_id=70007, username="Traveler")
    db_session.add_all([user_here, user_there])
    await db_session.flush()
    await db.add_or_balance(db_session, settings.guild_id, 70007, 500)
    await db_session.commit()

    cog = _cog(db_session)
    assert await cog._show_or(settings.guild_id, 70007) == 500
    assert await cog._show_or(other_guild_id, 70007) == 0


def test_sanitize_channel_name():
    assert _sanitize_channel_name("Jean Dupont") == "jean-dupont"
    assert _sanitize_channel_name("Éloïse") == "eloise"
    assert _sanitize_channel_name("  a--b  ") == "a-b"
    assert _sanitize_channel_name("") == "joueur"
    assert _sanitize_channel_name("!!!!") == "joueur"


def test_tower_channel_name():
    assert _tower_channel_name(FakeUser(id=1, display_name="Jean Dupont")) == "tower-of-jean-dupont"


async def test_towerof_shows_profile_embed(db_session):
    await db.add_or_balance(db_session, settings.guild_id, 70008, 300)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=70008, display_name="Profil"))
    await cog.towerof.callback(cog, ctx)

    embed = ctx.sent[0]["embed"]
    assert embed.title == "🗼 Tour — Profil"


async def test_towerof_resolves_mention(db_session):
    target_id = 1173059024661532703
    target = FakeUser(id=target_id, display_name="Cible")
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=70008, display_name="Moi"), guild=FakeGuild(settings.guild_id, members=[target]))
    await cog.towerof.callback(cog, ctx, cible=f"<@{target_id}>")

    embed = ctx.sent[0]["embed"]
    assert "Cible" in embed.title
