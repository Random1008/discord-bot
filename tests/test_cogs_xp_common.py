from datetime import datetime, timezone

from config.settings import settings
from models.rewards import Reward
from models.users import User
from cogs._xp_common import award_xp

OLD_ACCOUNT_CREATED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeRole:
    def __init__(self, id):
        self.id = id


class FakeMember:
    def __init__(self, id, display_name, created_at=OLD_ACCOUNT_CREATED_AT):
        self.id = id
        self.display_name = display_name
        self.added_roles = []
        self.created_at = created_at

    async def add_roles(self, role):
        self.added_roles.append(role)


class FakeGuild:
    def __init__(self, roles_by_id, members_by_id=None, id=None):
        self.id = id if id is not None else settings.guild_id
        self._roles_by_id = roles_by_id
        self._members_by_id = members_by_id or {}

    def get_role(self, role_id):
        return self._roles_by_id.get(role_id)

    def get_member(self, member_id):
        return self._members_by_id.get(member_id)


async def test_award_xp_persists_user_and_sends_no_announcement_below_level_up(db_session):
    channel = FakeChannel()
    guild = FakeGuild(roles_by_id={})
    member = FakeMember(id=11001, display_name="Newcomer")

    result = await award_xp(db_session, guild, lambda: channel, member, 50)

    assert result.xp == 50
    fetched = await db_session.get(User, (settings.guild_id, 11001))
    assert fetched is not None
    assert channel.sent == []


async def test_award_xp_announces_level_up_and_reward_and_assigns_role(db_session, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "role_actif_id", "555")

    db_session.add(Reward(level=1, reward_type="role", reward_value="role_actif"))
    await db_session.flush()

    channel = FakeChannel()
    role = FakeRole(id=555)
    guild = FakeGuild(roles_by_id={555: role})
    member = FakeMember(id=11002, display_name="Riser")

    result = await award_xp(db_session, guild, lambda: channel, member, 100)

    assert result.levels_gained == [1]
    assert any("niveau **1**" in message for message in channel.sent)
    assert any("role_actif" in message for message in channel.sent)
    assert member.added_roles == [role]


async def test_award_xp_dispatches_announcements_and_roles_for_inviter_bonus(db_session, monkeypatch):
    from config.settings import settings
    from models.badges import Badge
    from models.users import User
    import services.leveling as leveling_module

    monkeypatch.setattr(settings, "role_actif_id", "555")

    db_session.add(Reward(level=1, reward_type="role", reward_value="role_actif"))
    db_session.add(Badge(key="inviteur", name="Inviteur", description="d", icon="📨", rarity="rare"))

    inviter_member = FakeMember(id=12001, display_name="Inviter")
    invitee_member = FakeMember(id=12002, display_name="Invitee")

    db_session.add(User(guild_id=settings.guild_id, user_id=12001, username="Inviter"))
    db_session.add(User(guild_id=settings.guild_id, user_id=12002, username="Invitee", invited_by_guild_id=settings.guild_id, invited_by_user_id=12001))
    await db_session.flush()

    channel = FakeChannel()
    role = FakeRole(id=555)
    guild = FakeGuild(roles_by_id={555: role}, members_by_id={12001: inviter_member})

    result = await award_xp(
        db_session, guild, lambda: channel, invitee_member, leveling_module.xp_for_level(5)
    )

    assert result.inviter_bonus is not None
    assert result.inviter_bonus.user_id == 12001
    assert result.inviter_bonus.levels_gained == [1]
    assert any("Inviter" in message and "niveau **1**" in message for message in channel.sent)
    assert role in inviter_member.added_roles


async def test_award_xp_skips_inviter_dispatch_when_inviter_not_in_guild_cache(db_session, monkeypatch):
    from config.settings import settings
    from models.badges import Badge
    from models.users import User
    import services.leveling as leveling_module

    monkeypatch.setattr(settings, "role_actif_id", "555")

    db_session.add(Reward(level=1, reward_type="role", reward_value="role_actif"))
    db_session.add(Badge(key="inviteur", name="Inviteur", description="d", icon="📨", rarity="rare"))

    invitee_member = FakeMember(id=12004, display_name="Invitee2")

    db_session.add(User(guild_id=settings.guild_id, user_id=12003, username="Inviter2"))
    db_session.add(User(guild_id=settings.guild_id, user_id=12004, username="Invitee2", invited_by_guild_id=settings.guild_id, invited_by_user_id=12003))
    await db_session.flush()

    channel = FakeChannel()
    role = FakeRole(id=555)
    guild = FakeGuild(roles_by_id={555: role}, members_by_id={})  # inviter not cached

    result = await award_xp(
        db_session, guild, lambda: channel, invitee_member, leveling_module.xp_for_level(5)
    )

    assert result.inviter_bonus is not None
    # No exception raised, and no announcement referencing an inviter member was sent.
    assert not any("Inviter2" in message for message in channel.sent)


async def test_award_xp_announces_key_drop_with_usage_hint(db_session, monkeypatch):
    import services.leveling as leveling_module

    monkeypatch.setattr(leveling_module, "should_drop_key", lambda levels_elapsed, rng=None: True)
    monkeypatch.setattr(leveling_module, "roll_key_rarity", lambda rng=None: "rare")

    channel = FakeChannel()
    guild = FakeGuild(roles_by_id={})
    member = FakeMember(id=14001, display_name="Lucky")

    result = await award_xp(db_session, guild, lambda: channel, member, 100)

    assert len(result.key_drops) == 1
    assert any("obtenu une clé" in message and "$key" in message for message in channel.sent)


async def test_award_xp_reduces_amount_for_recently_created_account(db_session):
    channel = FakeChannel()
    guild = FakeGuild(roles_by_id={})
    member = FakeMember(id=13001, display_name="FreshAlt", created_at=datetime.now(timezone.utc))

    result = await award_xp(db_session, guild, lambda: channel, member, 100)

    assert result.xp == 20


async def test_award_xp_grants_full_amount_for_established_account(db_session):
    channel = FakeChannel()
    guild = FakeGuild(roles_by_id={})
    member = FakeMember(id=13002, display_name="Regular")

    result = await award_xp(db_session, guild, lambda: channel, member, 100)

    assert result.xp == 100
