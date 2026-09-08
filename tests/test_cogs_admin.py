from datetime import datetime, timezone

from cogs.admin import AdminCog
from models.badges import Badge
from models.economy import Economy
from models.levels import Level
from models.rewards import Reward
from config.settings import ADMIN_PERMISSION_OWNER_ID, settings
from services.admin_permission import has_permission
from services.bot_access import is_blocked

OLD_ACCOUNT_CREATED_AT = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeMember:
    def __init__(self, id, display_name, created_at=OLD_ACCOUNT_CREATED_AT):
        self.id = id
        self.display_name = display_name
        self.created_at = created_at
        self.added_roles = []

    async def add_roles(self, role):
        self.added_roles.append(role)


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id

    def get_role(self, role_id):
        return None

    def get_channel(self, channel_id):
        return None

    def get_member(self, member_id):
        return None


class FakeContext:
    def __init__(self, guild, author=None):
        self.guild = guild
        self.author = author if author is not None else FakeMember(id=1, display_name="Admin")
        self.prefix = "."
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _cog(db_session):
    return AdminCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_setlevel_sets_level_and_floor_xp(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41001, display_name="Target")

    await cog.setlevel.callback(cog, ctx, member, 10)

    level_row = await db_session.get(Level, (settings.guild_id, 41001))
    assert level_row.level == 10

    content = ctx.sent[0]
    assert "Target" in content and "10" in content


async def test_setlevel_rejects_negative_level(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41002, display_name="Target")

    await cog.setlevel.callback(cog, ctx, member, -1)

    assert await db_session.get(Level, (settings.guild_id, 41002)) is None
    assert "négatif" in ctx.sent[0]


async def test_addxp_grants_full_amount_even_for_a_recently_created_account(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41003, display_name="FreshAlt", created_at=datetime.now(timezone.utc))

    await cog.addxp.callback(cog, ctx, member, 100)

    level_row = await db_session.get(Level, (settings.guild_id, 41003))
    assert level_row.xp == 100  # not reduced by the alt-account penalty — an admin grant is deliberate


async def test_addxp_rejects_non_positive_amount(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41004, display_name="Target")

    await cog.addxp.callback(cog, ctx, member, 0)

    assert await db_session.get(Level, (settings.guild_id, 41004)) is None


async def test_removexp_subtracts_and_reports_remaining_xp(db_session):
    db_session.add(Level(guild_id=settings.guild_id, user_id=41005, xp=500, level=2, prestige=0, last_key_drop_level=0))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41005, display_name="Target")

    await cog.removexp.callback(cog, ctx, member, 100)

    level_row = await db_session.get(Level, (settings.guild_id, 41005))
    assert level_row.xp == 400
    assert "400" in ctx.sent[0]


async def test_addcoins_credits_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41006, display_name="Target")

    await cog.addcoins.callback(cog, ctx, member, 250)

    economy = await db_session.get(Economy, (settings.guild_id, 41006))
    assert economy.balance == 250


async def test_removecoins_debits_balance(db_session):
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41007, balance=300))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41007, display_name="Target")

    await cog.removecoins.callback(cog, ctx, member, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 41007))
    assert economy.balance == 200


async def test_removecoins_reports_insufficient_balance(db_session):
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41008, balance=10))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41008, display_name="Target")

    await cog.removecoins.callback(cog, ctx, member, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 41008))
    assert economy.balance == 10  # untouched
    assert "10" in ctx.sent[0]


async def test_resetuser_wipes_progression_and_economy(db_session):
    db_session.add(Level(guild_id=settings.guild_id, user_id=41009, xp=9999, level=15, prestige=1, last_key_drop_level=15))
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41009, balance=777))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41009, display_name="Target")

    await cog.resetuser.callback(cog, ctx, member)

    level_row = await db_session.get(Level, (settings.guild_id, 41009))
    economy = await db_session.get(Economy, (settings.guild_id, 41009))
    assert level_row.xp == 0 and level_row.level == 0 and level_row.prestige == 0
    assert economy.balance == 0


async def test_reset_monnaie_zeroes_balance_only_leaves_level_untouched(db_session):
    db_session.add(Level(guild_id=settings.guild_id, user_id=41016, xp=9999, level=15, prestige=1, last_key_drop_level=15))
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41016, balance=777))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41016, display_name="Target")

    await cog.reset.callback(cog, ctx, member, "monnaie")

    economy = await db_session.get(Economy, (settings.guild_id, 41016))
    level_row = await db_session.get(Level, (settings.guild_id, 41016))
    assert economy.balance == 0
    assert level_row.level == 15  # untouched — only "all" resets progression


async def test_reset_rejects_unknown_category(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41017, display_name="Target")

    await cog.reset.callback(cog, ctx, member, "bogus")

    assert "Catégorie invalide" in ctx.sent[0]


async def test_reset_all_wipes_progression_and_economy(db_session, monkeypatch):
    db_session.add(Level(guild_id=settings.guild_id, user_id=41018, xp=9999, level=15, prestige=1, last_key_drop_level=15))
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41018, balance=777))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41018, display_name="Target")

    async def _fake_prompt_market_mode(ctx):
        return "delete"

    monkeypatch.setattr(cog, "_prompt_market_mode", _fake_prompt_market_mode)

    await cog.reset.callback(cog, ctx, member, "ALL")  # category is case-insensitive

    level_row = await db_session.get(Level, (settings.guild_id, 41018))
    economy = await db_session.get(Economy, (settings.guild_id, 41018))
    assert level_row.xp == 0 and level_row.level == 0
    assert economy.balance == 0


async def test_money_add_credits_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41019, display_name="Target")

    await cog.money_add.callback(cog, ctx, member, 250)

    economy = await db_session.get(Economy, (settings.guild_id, 41019))
    assert economy.balance == 250


async def test_money_add_rejects_non_positive_amount(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41020, display_name="Target")

    await cog.money_add.callback(cog, ctx, member, 0)

    assert "positif" in ctx.sent[0]


async def test_money_remove_debits_balance(db_session):
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41021, balance=300))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41021, display_name="Target")

    await cog.money_remove.callback(cog, ctx, member, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 41021))
    assert economy.balance == 200


async def test_money_remove_reports_insufficient_balance(db_session):
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41022, balance=10))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41022, display_name="Target")

    await cog.money_remove.callback(cog, ctx, member, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 41022))
    assert economy.balance == 10


async def test_money_reset_sets_balance_to_zero(db_session):
    db_session.add(Economy(guild_id=settings.guild_id, user_id=41023, balance=777))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41023, display_name="Target")

    await cog.money_reset.callback(cog, ctx, member)

    economy = await db_session.get(Economy, (settings.guild_id, 41023))
    assert economy.balance == 0


async def test_tower_set_fixes_the_floor_to_an_exact_value(db_session):
    from models.rpg import RpgPlayerStats
    import services.rpg_db as rpg_db

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41024, display_name="Target")
    await rpg_db.update_floor_reached_max(db_session, settings.guild_id, 41024, 50)
    await db_session.commit()

    await cog.tower_set.callback(cog, ctx, member, 5)

    stats = await db_session.get(RpgPlayerStats, (settings.guild_id, 41024))
    assert stats.floor_reached_max == 5


async def test_tower_set_rejects_negative_floor(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41025, display_name="Target")

    await cog.tower_set.callback(cog, ctx, member, -1)

    assert "négatif" in ctx.sent[0]


async def test_tower_add_increases_the_floor(db_session):
    from models.rpg import RpgPlayerStats
    import services.rpg_db as rpg_db

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41026, display_name="Target")
    await rpg_db.update_floor_reached_max(db_session, settings.guild_id, 41026, 10)
    await db_session.commit()

    await cog.tower_add.callback(cog, ctx, member, 5)

    stats = await db_session.get(RpgPlayerStats, (settings.guild_id, 41026))
    assert stats.floor_reached_max == 15


async def test_tower_remove_decreases_the_floor_without_going_negative(db_session):
    from models.rpg import RpgPlayerStats
    import services.rpg_db as rpg_db

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41027, display_name="Target")
    await rpg_db.update_floor_reached_max(db_session, settings.guild_id, 41027, 10)
    await db_session.commit()

    await cog.tower_remove.callback(cog, ctx, member, 100)

    stats = await db_session.get(RpgPlayerStats, (settings.guild_id, 41027))
    assert stats.floor_reached_max == 0


async def test_tower_reset_sets_the_floor_to_zero(db_session):
    from models.rpg import RpgPlayerStats
    import services.rpg_db as rpg_db

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41028, display_name="Target")
    await rpg_db.update_floor_reached_max(db_session, settings.guild_id, 41028, 42)
    await db_session.commit()

    await cog.tower_reset.callback(cog, ctx, member)

    stats = await db_session.get(RpgPlayerStats, (settings.guild_id, 41028))
    assert stats.floor_reached_max == 0


async def test_givereward_grants_a_badge_by_key(db_session):
    db_session.add(Badge(key="veteran", name="Vétéran", description="d", icon="🎖️", rarity="rare"))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41010, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge="veteran", niveau=None)

    assert "veteran" in ctx.sent[0]


async def test_givereward_reports_unknown_badge_key(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41011, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge="ne-existe-pas", niveau=None)

    assert "Aucun badge" in ctx.sent[0]


async def test_givereward_grants_the_reward_defined_for_a_level(db_session):
    db_session.add(Reward(level=7, reward_type="coins", reward_value="30"))
    await db_session.flush()

    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41012, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge=None, niveau=7)

    economy = await db_session.get(Economy, (settings.guild_id, 41012))
    assert economy.balance == 30


async def test_givereward_reports_when_no_reward_defined_for_the_level(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41013, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge=None, niveau=999)

    assert "Aucune récompense" in ctx.sent[0]


async def test_givereward_rejects_both_badge_and_niveau(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41014, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge="veteran", niveau=7)

    assert "exactement un des deux" in ctx.sent[0]


async def test_givereward_rejects_neither_badge_nor_niveau(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())
    member = FakeMember(id=41015, display_name="Target")

    await cog.givereward.callback(cog, ctx, member, badge=None, niveau=None)

    assert "exactement un des deux" in ctx.sent[0]


async def test_bot_off_blocks_the_target_member(db_session):
    cog = _cog(db_session)
    admin = FakeMember(id=41100, display_name="Admin")
    ctx = FakeContext(guild=FakeGuild(), author=admin)
    member = FakeMember(id=41016, display_name="Target")

    await cog.access_off.callback(cog, ctx, member)

    assert await is_blocked(db_session, settings.guild_id, member.id) is True
    assert "ne peut plus interagir" in ctx.sent[0]


async def test_bot_on_unblocks_the_target_member(db_session):
    cog = _cog(db_session)
    admin = FakeMember(id=41101, display_name="Admin")
    ctx = FakeContext(guild=FakeGuild(), author=admin)
    member = FakeMember(id=41017, display_name="Target")
    await cog.access_off.callback(cog, ctx, member)

    await cog.access_on.callback(cog, ctx, member)

    assert await is_blocked(db_session, settings.guild_id, member.id) is False
    assert "peut de nouveau interagir" in ctx.sent[-1]


async def test_bot_group_without_subcommand_shows_usage(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(guild=FakeGuild())

    await cog.access_group.callback(cog, ctx)

    assert "bot on|off" in ctx.sent[0]


async def test_permadd_grants_permission_to_the_target_member(db_session):
    cog = _cog(db_session)
    owner = FakeMember(id=ADMIN_PERMISSION_OWNER_ID, display_name="Owner")
    ctx = FakeContext(guild=FakeGuild(), author=owner)
    member = FakeMember(id=41029, display_name="Target")

    await cog.permadd.callback(cog, ctx, member)

    assert await has_permission(db_session, settings.guild_id, member.id) is True
    assert "commandes admin" in ctx.sent[0]


async def test_permremove_revokes_permission_from_the_target_member(db_session):
    cog = _cog(db_session)
    owner = FakeMember(id=ADMIN_PERMISSION_OWNER_ID, display_name="Owner")
    ctx = FakeContext(guild=FakeGuild(), author=owner)
    member = FakeMember(id=41030, display_name="Target")
    await cog.permadd.callback(cog, ctx, member)

    await cog.permremove.callback(cog, ctx, member)

    assert await has_permission(db_session, settings.guild_id, member.id) is False
    assert "ne peut plus utiliser" in ctx.sent[-1]
