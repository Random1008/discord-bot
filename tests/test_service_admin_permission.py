from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.users import User
from services.admin_permission import can_bypass, grant_permission, has_permission, revoke_permission

GUILD_ID = settings.guild_id


class _FakeRole:
    def __init__(self, id):
        self.id = id


class _FakeMember:
    def __init__(self, id, roles=()):
        self.id = id
        self.roles = list(roles)


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=GUILD_ID, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


async def test_user_has_no_permission_by_default(db_session):
    await _make_user(db_session, 91001)

    assert await has_permission(db_session, GUILD_ID, 91001) is False


async def test_grant_permission_marks_user_permitted(db_session):
    await _make_user(db_session, 91002)
    await _make_user(db_session, 91099)

    await grant_permission(db_session, GUILD_ID, 91002, granted_by=91099)

    assert await has_permission(db_session, GUILD_ID, 91002) is True


async def test_grant_permission_is_idempotent(db_session):
    await _make_user(db_session, 91003)
    await _make_user(db_session, 91099)

    await grant_permission(db_session, GUILD_ID, 91003, granted_by=91099)
    await grant_permission(db_session, GUILD_ID, 91003, granted_by=91099)

    assert await has_permission(db_session, GUILD_ID, 91003) is True


async def test_permission_is_scoped_per_guild(db_session):
    other_guild = GUILD_ID + 1
    db_session.add(User(guild_id=other_guild, user_id=91004, username="user91004"))
    await _make_user(db_session, 91004)
    await _make_user(db_session, 91099)
    await db_session.flush()

    await grant_permission(db_session, GUILD_ID, 91004, granted_by=91099)

    assert await has_permission(db_session, GUILD_ID, 91004) is True
    assert await has_permission(db_session, other_guild, 91004) is False


async def test_revoke_permission_lifts_it(db_session):
    await _make_user(db_session, 91005)
    await _make_user(db_session, 91099)
    await grant_permission(db_session, GUILD_ID, 91005, granted_by=91099)

    await revoke_permission(db_session, GUILD_ID, 91005)

    assert await has_permission(db_session, GUILD_ID, 91005) is False


async def test_revoke_permission_on_never_granted_user_is_a_noop(db_session):
    await _make_user(db_session, 91006)

    await revoke_permission(db_session, GUILD_ID, 91006)

    assert await has_permission(db_session, GUILD_ID, 91006) is False


async def test_can_bypass_requires_both_role_and_permission_entry(db_session):
    await _make_user(db_session, 91007)
    await _make_user(db_session, 91099)
    await grant_permission(db_session, GUILD_ID, 91007, granted_by=91099)

    member_without_role = _FakeMember(id=91007, roles=[])
    member_with_role = _FakeMember(id=91007, roles=[_FakeRole(id=ADMIN_PERMISSION_ROLE_ID)])

    assert await can_bypass(db_session, GUILD_ID, member_without_role) is False
    assert await can_bypass(db_session, GUILD_ID, member_with_role) is True


async def test_can_bypass_is_false_with_role_but_no_permission_entry(db_session):
    await _make_user(db_session, 91008)

    member = _FakeMember(id=91008, roles=[_FakeRole(id=ADMIN_PERMISSION_ROLE_ID)])

    assert await can_bypass(db_session, GUILD_ID, member) is False
