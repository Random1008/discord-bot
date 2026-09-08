import io

from PIL import Image

from cogs.profile import ProfileCog
from models.badges import Badge, UserBadge
from models.economy import Economy
from models.levels import Level
from models.users import User
from config.settings import settings


def _fake_avatar_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), (10, 20, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeAvatar:
    async def read(self):
        return _fake_avatar_bytes()


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.display_avatar = FakeAvatar()


class FakeGuild:
    def __init__(self):
        self.id = settings.guild_id


class FakeContext:
    def __init__(self, author):
        self.author = author
        self.guild = FakeGuild()
        self.calls = []

    async def send(self, **kwargs):
        self.calls.append(kwargs)


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


async def test_profile_sends_image_and_stats_embed_for_caller(db_session):
    from datetime import date

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ProfileCog(bot=FakeBot(session_factory))
    import cogs.profile as profile_module

    original_today = cog._today
    cog._today = lambda: date(2026, 7, 21)

    user = User(guild_id=settings.guild_id, user_id=26001, username="Ashen")
    badge = Badge(key="debutant", name="Débutant", description="d", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()
    db_session.add_all(
        [
            Level(guild_id=settings.guild_id, user_id=26001, xp=250, level=1, prestige=0),
            Economy(guild_id=settings.guild_id, user_id=26001, balance=500),
            UserBadge(guild_id=settings.guild_id, user_id=26001, badge_id=badge.id),
        ]
    )
    await db_session.commit()

    ctx = FakeContext(FakeUser(id=26001, display_name="Ashen"))

    await cog.profile.callback(cog, ctx, None)

    assert len(ctx.calls) == 1
    call = ctx.calls[0]
    assert "file" in call
    assert "embed" in call
    embed = call["embed"]
    field_names = [f.name for f in embed.fields]
    assert "Messages envoyés" in field_names
    assert "Prestige" in field_names
    assert "Solde" in field_names
    assert "Badges" in field_names
    fields_by_name = {f.name: f.value for f in embed.fields}
    assert fields_by_name["Solde"] == "500 coins"
    assert "Débutant" in fields_by_name["Badges"]

    cog._today = original_today


async def test_profile_defaults_to_caller_when_no_target_given(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ProfileCog(bot=FakeBot(session_factory))

    user = User(guild_id=settings.guild_id, user_id=26002, username="Solo")
    db_session.add(user)
    await db_session.commit()

    ctx = FakeContext(FakeUser(id=26002, display_name="Solo"))

    await cog.profile.callback(cog, ctx, None)

    assert len(ctx.calls) == 1
