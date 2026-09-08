from discord.ext import commands

from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from database.engine import AsyncSessionLocal
from main import (
    FeatureUnavailableOnGuild,
    MissingAdminPermission,
    UserBlocked,
    YORU_DUPLICATE_RESTRICTED_GUILD_ID,
    create_bot,
)
from services.admin_permission import grant_permission
from services.bot_access import block_user


async def test_create_bot_has_expected_prefix_and_intents():
    bot = create_bot()

    assert isinstance(bot, commands.Bot)
    assert bot.command_prefix == ["!", "$", ".", "+"]
    assert bot.intents.members is True
    assert bot.intents.message_content is True
    assert bot.intents.voice_states is True

    await bot.close()


async def test_create_bot_wires_session_factory():
    bot = create_bot()

    assert bot.session_factory is AsyncSessionLocal

    await bot.close()


class _FakeCommand:
    def __init__(self, qualified_name):
        self.qualified_name = qualified_name


class _FakeGuild:
    def __init__(self, id):
        self.id = id


def _cog_with_module(module: str):
    cls = type("FakeCog", (), {"__module__": module})
    return cls()


class _FakeUser:
    def __init__(self, id):
        self.id = id


class _FakeRole:
    def __init__(self, id):
        self.id = id


class _FakeMember:
    def __init__(self, id, roles=()):
        self.id = id
        self.roles = list(roles)


class _FakeCtx:
    def __init__(self, qualified_name, prefix, guild=None, cog=None, author=None):
        self.command = _FakeCommand(qualified_name)
        self.prefix = prefix
        self.guild = guild
        self.cog = cog
        self.author = author if author is not None else _FakeUser(id=1)


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_market_admin_commands_require_dot_prefix():
    bot = create_bot()
    check = bot._checks[0]

    for name in ("market", "market add", "market remove", "market edit"):
        assert await check(_FakeCtx(name, ".")) is True
        for wrong_prefix in ("!", "$"):
            try:
                await check(_FakeCtx(name, wrong_prefix))
                assert False, f"{name} with prefix {wrong_prefix!r} should have raised"
            except commands.CheckFailure:
                pass

    await bot.close()


async def test_tour_casino_gacha_blocked_on_restricted_guild():
    bot = create_bot()
    check = bot._checks[0]
    restricted_guild = _FakeGuild(YORU_DUPLICATE_RESTRICTED_GUILD_ID)

    for module, name, prefix in (
        ("cogs.tour", "tour", "!"),
        ("cogs.casino", "slots", "$"),
        ("cogs.gacha", "gacha pull", "$"),
    ):
        ctx = _FakeCtx(name, prefix, guild=restricted_guild, cog=_cog_with_module(module))
        try:
            await check(ctx)
            assert False, f"{name} on the restricted guild should have raised"
        except FeatureUnavailableOnGuild:
            pass

    await bot.close()


async def test_tour_casino_gacha_allowed_on_other_guild():
    bot = create_bot()
    check = bot._checks[0]
    other_guild = _FakeGuild(1297620557927284877)

    for module, name, prefix in (
        ("cogs.tour", "tour", "!"),
        ("cogs.casino", "slots", "$"),
        ("cogs.gacha", "gacha pull", "$"),
    ):
        ctx = _FakeCtx(name, prefix, guild=other_guild, cog=_cog_with_module(module))
        assert await check(ctx) is True

    await bot.close()


async def test_dollar_and_bang_commands_rejected_under_plus_prefix():
    bot = create_bot()
    check = bot._checks[0]

    # A regular ($/!) command invoked under "+" is silently rejected (check
    # returns False, same as an unrelated command under "."), not an exception
    # — discord.py itself turns a False return into a swallowed CheckFailure
    # once wired into the real command-invocation pipeline.
    assert await check(_FakeCtx("balance", "+", cog=_cog_with_module("cogs.economy"))) is False

    await bot.close()


async def test_act_command_requires_dot_prefix():
    bot = create_bot()
    check = bot._checks[0]

    assert await check(_FakeCtx("act", ".")) is True
    for wrong_prefix in ("!", "$", "+"):
        try:
            await check(_FakeCtx("act", wrong_prefix))
            assert False, f"act with prefix {wrong_prefix!r} should have raised"
        except commands.CheckFailure:
            pass

    await bot.close()


async def test_unrelated_command_not_blocked_on_restricted_guild():
    bot = create_bot()
    check = bot._checks[0]
    restricted_guild = _FakeGuild(YORU_DUPLICATE_RESTRICTED_GUILD_ID)

    ctx = _FakeCtx("balance", "$", guild=restricted_guild, cog=_cog_with_module("cogs.economy"))
    assert await check(ctx) is True

    await bot.close()


async def test_non_blocked_user_passes_the_access_check(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[1]
    guild = _FakeGuild(settings.guild_id)

    ctx = _FakeCtx("balance", "$", guild=guild, author=_FakeUser(id=98001))
    assert await check(ctx) is True

    await bot.close()


async def test_blocked_user_cannot_run_any_command_including_bot_on(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[1]
    guild = _FakeGuild(settings.guild_id)
    blocked_user = _FakeUser(id=98002)

    await block_user(db_session, guild.id, blocked_user.id, blocked_by=1)
    await db_session.commit()

    # Even the reactivation command itself must be blocked, otherwise a
    # blocked user could run `.bot on @self` to undo their own block.
    for name in ("balance", "bot on"):
        ctx = _FakeCtx(name, "$" if name == "balance" else ".", guild=guild, author=blocked_user)
        try:
            await check(ctx)
            assert False, f"blocked user running {name!r} should have raised"
        except UserBlocked:
            pass

    await bot.close()


async def test_dm_context_without_guild_is_not_subject_to_the_block_check(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[1]

    ctx = _FakeCtx("balance", "$", guild=None, author=_FakeUser(id=98003))
    assert await check(ctx) is True

    await bot.close()


async def test_non_admin_command_is_not_subject_to_the_permission_check(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)

    ctx = _FakeCtx("balance", "$", guild=guild, author=_FakeMember(id=99001))
    assert await check(ctx) is True

    await bot.close()


async def test_permadd_and_permremove_require_the_role_but_not_a_whitelist_entry(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)

    # No whitelist entry needed — these two commands manage whitelist entries
    # themselves, cogs/admin.py restricts them separately to
    # ADMIN_PERMISSION_OWNER_ID — but the role itself is still required, like
    # every other admin command.
    for i, name in enumerate(("permadd", "permremove")):
        member = _FakeMember(id=99002 + i, roles=[_FakeRole(id=ADMIN_PERMISSION_ROLE_ID)])
        ctx = _FakeCtx(name, ".", guild=guild, author=member)
        assert await check(ctx) is True

    await bot.close()


async def test_permadd_and_permremove_rejected_without_the_required_role(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)

    for i, name in enumerate(("permadd", "permremove")):
        ctx = _FakeCtx(name, ".", guild=guild, author=_FakeMember(id=99006 + i, roles=[]))
        try:
            await check(ctx)
            assert False, f"{name} without the admin role should have raised"
        except MissingAdminPermission:
            pass

    await bot.close()


async def test_admin_command_rejected_without_the_required_role(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)
    member = _FakeMember(id=99003, roles=[])

    ctx = _FakeCtx("addcoins", ".", guild=guild, author=member)
    try:
        await check(ctx)
        assert False, "member without the admin role should have raised"
    except MissingAdminPermission:
        pass

    await bot.close()


async def test_admin_command_rejected_with_role_but_without_whitelist_entry(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)
    member = _FakeMember(id=99004, roles=[_FakeRole(id=ADMIN_PERMISSION_ROLE_ID)])

    ctx = _FakeCtx("addcoins", ".", guild=guild, author=member)
    try:
        await check(ctx)
        assert False, "member without a whitelist entry should have raised"
    except MissingAdminPermission:
        pass

    await bot.close()


async def test_admin_command_allowed_with_role_and_whitelist_entry(db_session):
    bot = create_bot()
    bot.session_factory = lambda: _FakeSessionContext(db_session)
    check = bot._checks[2]
    guild = _FakeGuild(settings.guild_id)
    member = _FakeMember(id=99005, roles=[_FakeRole(id=ADMIN_PERMISSION_ROLE_ID)])
    await grant_permission(db_session, guild.id, member.id, granted_by=1)
    await db_session.commit()

    ctx = _FakeCtx("addcoins", ".", guild=guild, author=member)
    assert await check(ctx) is True

    await bot.close()
