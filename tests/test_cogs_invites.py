from cogs.invites import InvitesCog
from config.settings import settings


class FakeInvite:
    def __init__(self, code, uses, inviter_id):
        self.code = code
        self.uses = uses
        self.inviter = FakeInviter(inviter_id)


class FakeInviter:
    def __init__(self, id):
        self.id = id
        self.display_name = f"Inviter{id}"


class FakeGuild:
    def __init__(self, id, invites):
        self.id = id
        self._invites = invites

    async def invites(self):
        return self._invites


class FakeMember:
    def __init__(self, id, display_name, guild):
        self.id = id
        self.display_name = display_name
        self.guild = guild


class FakeBot:
    def __init__(self, session_factory, guilds):
        self.session_factory = session_factory
        self.guilds = guilds


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


async def test_on_member_join_sets_invited_by_id_from_diffed_invite(db_session):
    from models.users import User

    inviter = User(guild_id=settings.guild_id, user_id=14001, username="Inviter")
    db_session.add(inviter)
    await db_session.flush()
    await db_session.commit()

    guild = FakeGuild(id=settings.guild_id, invites=[FakeInvite("abc123", uses=0, inviter_id=14001)])
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = InvitesCog(bot=FakeBot(session_factory, guilds=[guild]))

    await cog.on_ready()  # snapshots {"abc123": 0}

    guild._invites = [FakeInvite("abc123", uses=1, inviter_id=14001)]  # someone just used it
    joining_member = FakeMember(id=14002, display_name="Invitee", guild=guild)
    await cog.on_member_join(joining_member)

    fetched = await db_session.get(User, (settings.guild_id, 14002))
    assert fetched.invited_by_user_id == 14001


async def test_on_member_join_creates_inviter_user_row_when_missing(db_session):
    from models.users import User

    # No User row for the inviter (id=14005) exists yet — e.g. they never sent a message.
    guild = FakeGuild(id=settings.guild_id, invites=[FakeInvite("newcode", uses=0, inviter_id=14005)])
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = InvitesCog(bot=FakeBot(session_factory, guilds=[guild]))

    await cog.on_ready()  # snapshots {"newcode": 0}

    guild._invites = [FakeInvite("newcode", uses=1, inviter_id=14005)]
    joining_member = FakeMember(id=14006, display_name="Invitee2", guild=guild)

    await cog.on_member_join(joining_member)  # must not raise an IntegrityError

    invitee = await db_session.get(User, (settings.guild_id, 14006))
    assert invitee.invited_by_user_id == 14005

    inviter = await db_session.get(User, (settings.guild_id, 14005))
    assert inviter is not None


async def test_on_member_join_does_nothing_when_no_invite_use_increased(db_session):
    from models.users import User

    inviter = User(guild_id=settings.guild_id, user_id=14003, username="Inviter2")
    db_session.add(inviter)
    await db_session.flush()
    await db_session.commit()

    guild = FakeGuild(id=settings.guild_id, invites=[FakeInvite("stable", uses=5, inviter_id=14003)])
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = InvitesCog(bot=FakeBot(session_factory, guilds=[guild]))

    await cog.on_ready()
    joining_member = FakeMember(id=14004, display_name="VanityJoiner", guild=guild)
    await cog.on_member_join(joining_member)  # e.g. vanity URL join, uses count unchanged

    fetched = await db_session.get(User, (settings.guild_id, 14004))
    assert fetched.invited_by_user_id is None
