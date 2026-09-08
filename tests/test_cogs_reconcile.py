from cogs.reconcile import ReconcileCog
from config.settings import settings
from models.levels import Level
from models.rewards import Reward
from models.users import User


class FakeRole:
    def __init__(self, id):
        self.id = id


class FakeMember:
    def __init__(self, id, roles=None):
        self.id = id
        self.roles = list(roles or [])

    async def add_roles(self, role):
        self.roles.append(role)

    async def remove_roles(self, role):
        self.roles = [r for r in self.roles if r.id != role.id]


class FakeGuild:
    def __init__(self, id, members_by_id=None, roles_by_id=None):
        self.id = id
        self._members_by_id = members_by_id or {}
        self._roles_by_id = roles_by_id or {}

    def get_member(self, user_id):
        return self._members_by_id.get(user_id)

    def get_role(self, role_id):
        return self._roles_by_id.get(role_id)


class FakeContext:
    def __init__(self, guild):
        self.guild = guild
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content)


class FakeBot:
    def __init__(self, session_factory, cogs=None):
        self.session_factory = session_factory
        self._cogs = cogs or {}

    def get_cog(self, name):
        return self._cogs.get(name)


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


def _cog(db_session, cogs=None):
    return ReconcileCog(bot=FakeBot(lambda: _FakeSessionContext(db_session), cogs=cogs))


async def test_act_adds_missing_role_and_removes_unjustified_managed_role(db_session, monkeypatch):
    monkeypatch.setattr(settings, "role_actif_id", "111")
    monkeypatch.setattr(settings, "role_habitue_id", "222")

    db_session.add_all(
        [
            Reward(level=5, reward_type="role", reward_value="role_actif"),
            Reward(level=20, reward_type="role", reward_value="role_habitue"),
        ]
    )
    db_session.add(User(guild_id=settings.guild_id, user_id=41001, username="Member"))
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=41001, xp=2500, level=5, prestige=0))
    await db_session.commit()

    role_actif = FakeRole(id=111)
    role_habitue = FakeRole(id=222)
    # Member is only level 5 but somehow already holds the level-20 role.
    member = FakeMember(id=41001, roles=[role_habitue])
    guild = FakeGuild(
        id=settings.guild_id,
        members_by_id={41001: member},
        roles_by_id={111: role_actif, 222: role_habitue},
    )

    cog = _cog(db_session)
    ctx = FakeContext(guild)

    await cog.act.callback(cog, ctx)

    assert {r.id for r in member.roles} == {111}
    assert len(ctx.sent) == 1


async def test_act_leaves_unmanaged_roles_untouched(db_session, monkeypatch):
    monkeypatch.setattr(settings, "role_actif_id", "111")

    db_session.add(Reward(level=5, reward_type="role", reward_value="role_actif"))
    db_session.add(User(guild_id=settings.guild_id, user_id=41004, username="Colorful"))
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=41004, xp=2500, level=5, prestige=0))
    await db_session.commit()

    role_actif = FakeRole(id=111)
    unrelated_role = FakeRole(id=999)
    member = FakeMember(id=41004, roles=[unrelated_role])
    guild = FakeGuild(
        id=settings.guild_id,
        members_by_id={41004: member},
        roles_by_id={111: role_actif, 999: unrelated_role},
    )

    cog = _cog(db_session)
    ctx = FakeContext(guild)

    await cog.act.callback(cog, ctx)

    assert {r.id for r in member.roles} == {111, 999}


async def test_act_triggers_classement_sweep_when_cog_loaded(db_session):
    guild = FakeGuild(id=settings.guild_id)

    class FakeClassementCog:
        def __init__(self):
            self.called_with = None

        async def run_sweep(self, guild):
            self.called_with = guild

    classement_cog = FakeClassementCog()
    cog = _cog(db_session, cogs={"ClassementRolesCog": classement_cog})
    ctx = FakeContext(guild)

    await cog.act.callback(cog, ctx)

    assert classement_cog.called_with is guild


async def test_act_skips_members_not_cached_in_guild(db_session):
    db_session.add(User(guild_id=settings.guild_id, user_id=41003, username="Ghost"))
    await db_session.flush()
    db_session.add(Level(guild_id=settings.guild_id, user_id=41003, xp=100, level=1, prestige=0))
    await db_session.commit()

    guild = FakeGuild(id=settings.guild_id)
    cog = _cog(db_session)
    ctx = FakeContext(guild)

    await cog.act.callback(cog, ctx)  # must not raise

    assert len(ctx.sent) == 1


async def test_act_does_nothing_in_dm_context(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=None)

    await cog.act.callback(cog, ctx)

    assert ctx.sent == []
