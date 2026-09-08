from datetime import date

from cogs.classement_roles import ClassementRolesCog
from models.badges import Badge
from models.users import User
from config.settings import settings


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeRole:
    def __init__(self, id, members):
        self.id = id
        self.members = members


class FakeMember:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.added_roles = []
        self.removed_roles = []

    async def add_roles(self, role):
        self.added_roles.append(role)

    async def remove_roles(self, role):
        self.removed_roles.append(role)


class FakeGuild:
    def __init__(self, members_by_id, roles_by_id, id=None):
        self.id = id if id is not None else settings.guild_id
        self._members_by_id = members_by_id
        self._roles_by_id = roles_by_id

    def get_member(self, member_id):
        return self._members_by_id.get(member_id)

    def get_role(self, role_id):
        return self._roles_by_id.get(role_id)


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


async def test_run_sweep_grants_badges_and_announces(db_session, monkeypatch, tmp_path):
    from models.stats import MessageStat

    db_session.add(Badge(key="roi_du_chat", name="Roi du Chat", description="d", icon="💬", rarity="epique"))
    db_session.add(Badge(key="maitre_vocal", name="Maître Vocal", description="d", icon="🎙️", rarity="epique"))
    db_session.add(Badge(key="top_10", name="Top 10", description="d", icon="🔟", rarity="rare"))
    db_session.add(Badge(key="ancien", name="Ancien", description="d", icon="⏳", rarity="epique"))
    user = User(guild_id=settings.guild_id, user_id=28001, username="Chatty")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MessageStat(guild_id=settings.guild_id, user_id=28001, date=date(2026, 7, 21), count=50))
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: FakeChannel())
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10_vocal:\ntop_10_message:\n", encoding="utf-8")
    cog._role_config_path = config_path

    member = FakeMember(id=28001, display_name="Chatty")
    guild = FakeGuild(members_by_id={28001: member}, roles_by_id={})

    await cog.run_sweep(guild)

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 28001))
    assert result.scalar_one_or_none() is not None


async def test_rotate_roles_moves_role_from_old_holder_to_new_leader(db_session, tmp_path):
    from models.stats import MessageStat

    db_session.add_all([User(guild_id=settings.guild_id, user_id=28101, username="OldLeader"), User(guild_id=settings.guild_id, user_id=28102, username="NewLeader")])
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(guild_id=settings.guild_id, user_id=28101, date=date(2026, 7, 20), count=5),
            MessageStat(guild_id=settings.guild_id, user_id=28102, date=date(2026, 7, 21), count=500),
        ]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat: 555\nmaitre_vocal:\n", encoding="utf-8")
    cog._role_config_path = config_path

    old_leader = FakeMember(id=28101, display_name="OldLeader")
    new_leader = FakeMember(id=28102, display_name="NewLeader")
    role = FakeRole(id=555, members=[old_leader])
    guild = FakeGuild(members_by_id={28101: old_leader, 28102: new_leader}, roles_by_id={555: role})

    await cog._rotate_roles(guild)

    assert role in old_leader.removed_roles
    assert role in new_leader.added_roles


async def test_rotate_multi_holder_role_adds_top_10_and_removes_others(db_session, tmp_path):
    from models.stats import MessageStat

    user_ids = list(range(28200, 28212))  # 12 users: 10 should qualify, 2 should not
    db_session.add_all([User(guild_id=settings.guild_id, user_id=uid, username=str(uid)) for uid in user_ids])
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(guild_id=settings.guild_id, user_id=uid, date=date(2026, 7, 21), count=len(user_ids) - i)
            for i, uid in enumerate(user_ids)
        ]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("top_10_message: 777\n", encoding="utf-8")
    cog._role_config_path = config_path

    # user_ids[10] and [11] rank outside the top 10 and should never have had the role.
    outsider = FakeMember(id=user_ids[11], display_name="Outsider")
    # user_ids[0] is currently the holder from a previous run but is still in the top 10.
    stale_holder = FakeMember(id=user_ids[9], display_name="StaleHolder")
    members_by_id = {uid: FakeMember(id=uid, display_name=str(uid)) for uid in user_ids}
    members_by_id[user_ids[9]] = stale_holder
    members_by_id[user_ids[11]] = outsider
    role = FakeRole(id=777, members=[stale_holder, outsider])
    guild = FakeGuild(members_by_id=members_by_id, roles_by_id={777: role})

    await cog._rotate_roles(guild)

    assert role not in outsider.added_roles
    assert role in outsider.removed_roles
    for uid in user_ids[:10]:
        member = members_by_id[uid]
        if member is stale_holder:
            assert role not in member.removed_roles
        else:
            assert role in member.added_roles


async def test_rotate_roles_moves_riche_role_from_old_holder_to_new_leader(db_session, tmp_path):
    from models.economy import Economy

    db_session.add_all(
        [
            User(guild_id=settings.guild_id, user_id=28301, username="OldRich"),
            User(guild_id=settings.guild_id, user_id=28302, username="NewRich"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Economy(guild_id=settings.guild_id, user_id=28301, balance=50),
            Economy(guild_id=settings.guild_id, user_id=28302, balance=5000),
        ]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("riche: 666\n", encoding="utf-8")
    cog._role_config_path = config_path

    old_holder = FakeMember(id=28301, display_name="OldRich")
    new_holder = FakeMember(id=28302, display_name="NewRich")
    role = FakeRole(id=666, members=[old_holder])
    guild = FakeGuild(members_by_id={28301: old_holder, 28302: new_holder}, roles_by_id={666: role})

    await cog._rotate_roles(guild)

    assert role in old_holder.removed_roles
    assert role in new_holder.added_roles


async def test_rotate_multi_holder_role_adds_top_10_argent_and_removes_others(db_session, tmp_path):
    from models.economy import Economy

    user_ids = list(range(28400, 28412))  # 12 users: 10 should qualify, 2 should not
    db_session.add_all([User(guild_id=settings.guild_id, user_id=uid, username=str(uid)) for uid in user_ids])
    await db_session.flush()
    db_session.add_all(
        [Economy(guild_id=settings.guild_id, user_id=uid, balance=len(user_ids) - i) for i, uid in enumerate(user_ids)]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("top_10_argent: 888\n", encoding="utf-8")
    cog._role_config_path = config_path

    outsider = FakeMember(id=user_ids[11], display_name="Outsider")
    stale_holder = FakeMember(id=user_ids[9], display_name="StaleHolder")
    members_by_id = {uid: FakeMember(id=uid, display_name=str(uid)) for uid in user_ids}
    members_by_id[user_ids[9]] = stale_holder
    members_by_id[user_ids[11]] = outsider
    role = FakeRole(id=888, members=[stale_holder, outsider])
    guild = FakeGuild(members_by_id=members_by_id, roles_by_id={888: role})

    await cog._rotate_roles(guild)

    assert role not in outsider.added_roles
    assert role in outsider.removed_roles
    for uid in user_ids[:10]:
        member = members_by_id[uid]
        if member is stale_holder:
            assert role not in member.removed_roles
        else:
            assert role in member.added_roles


async def test_rotate_roles_skips_unconfigured_rankings(db_session, tmp_path):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10_vocal:\ntop_10_message:\n", encoding="utf-8")
    cog._role_config_path = config_path

    guild = FakeGuild(members_by_id={}, roles_by_id={})

    await cog._rotate_roles(guild)  # must not raise
