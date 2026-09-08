import random
from unittest.mock import Mock

import discord

from cogs.casino import CasinoCog
from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.economy import Economy
from services.admin_permission import grant_permission
from services.economy import add_balance
from services.users import get_or_create_user


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, guild_id if guild_id is not None else settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeContext:
    def __init__(self, author, guild=None, channel=None):
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.channel = channel
        self.sent = []

    async def send(self, content=None, embed=None, **kwargs):
        self.sent.append({"content": content, "embed": embed})

    def last_text(self) -> str:
        entry = self.sent[-1]
        if entry["embed"] is not None:
            return f"{entry['embed'].title or ''} {entry['embed'].description or ''}"
        return entry["content"] or ""


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
    return CasinoCog(bot=FakeBot(lambda: _FakeSessionContext(db_session)))


async def test_coinflip_rejects_non_positive_mise(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30001, display_name="Player"))

    await cog.coinflip.callback(cog, ctx, 0)

    assert "positive" in ctx.last_text()


async def test_coinflip_rejects_insufficient_balance(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30002, display_name="Broke"))

    await cog.coinflip.callback(cog, ctx, 100)

    assert "insuffisant" in ctx.last_text()


async def test_coinflip_win_credits_the_stake(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 30003, "Winner")
    await add_balance(db_session, settings.guild_id, 30003, 500)
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "pile")

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30003, display_name="Winner"))

    await cog.coinflip.callback(cog, ctx, 100, "pile")

    economy = await db_session.get(Economy, (settings.guild_id, 30003))
    assert economy.balance == 600


async def test_slots_triple_seven_jackpot(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 30004, "Slotter")
    await add_balance(db_session, settings.guild_id, 30004, 500)
    await db_session.commit()

    monkeypatch.setattr(random, "choices", lambda seq, weights, k: ["7️⃣", "7️⃣", "7️⃣"])

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30004, display_name="Slotter"))

    await cog.slots.callback(cog, ctx, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 30004))
    assert economy.balance == 500 + 1500 - 100


async def test_dice_rejects_out_of_range_guess(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30005, display_name="Guesser"))

    await cog.dice.callback(cog, ctx, 50, 9)

    assert "entre 1 et 6" in ctx.last_text()


async def test_jackpot_loss_feeds_the_pool(db_session, monkeypatch):
    await get_or_create_user(db_session, settings.guild_id, 30006, "Loser")
    await add_balance(db_session, settings.guild_id, 30006, 500)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.99)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30006, display_name="Loser"))

    await cog.jackpot.callback(cog, ctx, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 30006))
    assert economy.balance == 400
    assert "cagnotte" in ctx.last_text()


async def test_jackpot_win_awards_the_pool(db_session, monkeypatch):
    from services.casino import add_to_jackpot

    await get_or_create_user(db_session, settings.guild_id, 30007, "JackpotWinner")
    await add_balance(db_session, settings.guild_id, 30007, 500)
    await add_to_jackpot(db_session, settings.guild_id, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30007, display_name="JackpotWinner"))

    await cog.jackpot.callback(cog, ctx, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 30007))
    assert economy.balance == 500 + 1000
    assert "JACKPOT" in ctx.last_text()


async def test_jackpot_win_records_stats_as_jackpot(db_session, monkeypatch):
    from services.casino import add_to_jackpot, get_casino_stats

    await get_or_create_user(db_session, settings.guild_id, 30008, "StatTracker")
    await add_balance(db_session, settings.guild_id, 30008, 500)
    await add_to_jackpot(db_session, settings.guild_id, 1000)
    await db_session.commit()

    monkeypatch.setattr(random, "random", lambda: 0.0)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30008, display_name="StatTracker"))
    await cog.jackpot.callback(cog, ctx, 100)

    stats = await get_casino_stats(db_session, settings.guild_id, 30008)
    assert stats["jackpots_won"] == 1
    assert stats["wins_count"] == 1


async def test_coinflip_records_casino_stats(db_session, monkeypatch):
    from services.casino import get_casino_stats

    await get_or_create_user(db_session, settings.guild_id, 30009, "Recorder")
    await add_balance(db_session, settings.guild_id, 30009, 500)
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "pile")

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30009, display_name="Recorder"))
    await cog.coinflip.callback(cog, ctx, 100, "pile")

    stats = await get_casino_stats(db_session, settings.guild_id, 30009)
    assert stats["total_wagered"] == 100
    assert stats["wins_count"] == 1


async def test_highlow_rejects_invalid_guess(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30010, display_name="Guesser"))

    await cog.highlow.callback(cog, ctx, 50, "égal")

    assert "plus" in ctx.last_text()


async def test_highlow_correct_guess_pays_2x(db_session, monkeypatch):
    from services.casino import roll_highlow_card as _  # noqa: F401 (documents dependency)

    await get_or_create_user(db_session, settings.guild_id, 30011, "HighLower")
    await add_balance(db_session, settings.guild_id, 30011, 500)
    await db_session.commit()

    calls = iter([3, 9])
    monkeypatch.setattr(random.Random, "randint", lambda self, a, b: next(calls))

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30011, display_name="HighLower"))
    await cog.highlow.callback(cog, ctx, 100, "plus")

    economy = await db_session.get(Economy, (settings.guild_id, 30011))
    assert economy.balance == 500 + 100


async def test_poker_rejects_non_positive_mise(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30012, display_name="PokerPlayer"))

    await cog.poker.callback(cog, ctx, 0)

    assert "positive" in ctx.last_text()


async def test_poker_full_house_pays_9x(db_session, monkeypatch):
    import cogs.casino as casino_cog_module

    await get_or_create_user(db_session, settings.guild_id, 30013, "PokerWinner")
    await add_balance(db_session, settings.guild_id, 30013, 500)
    await db_session.commit()

    fixed_hand = [(5, "♠"), (5, "♥"), (5, "♦"), (9, "♠"), (9, "♥")]
    monkeypatch.setattr(casino_cog_module, "draw_poker_hand", lambda rng: fixed_hand)

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30013, display_name="PokerWinner"))
    await cog.poker.callback(cog, ctx, 100)

    economy = await db_session.get(Economy, (settings.guild_id, 30013))
    assert economy.balance == 500 - 100 + 900


async def test_casinostats_reports_recorded_totals(db_session):
    from services.casino import record_casino_result

    await get_or_create_user(db_session, settings.guild_id, 30014, "StatViewer")
    await record_casino_result(db_session, settings.guild_id, 30014, wagered=300, won=150, is_win=True, is_jackpot=False)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30014, display_name="StatViewer"))
    await cog.casino_stats.callback(cog, ctx)

    field_values = {field.name: field.value for field in ctx.sent[-1]["embed"].fields}
    assert field_values["Total misé"] == "300"
    assert field_values["Total gagné"] == "150"


async def test_coinflip_bypass_allows_play_with_zero_balance(db_session, monkeypatch):
    monkeypatch.setattr(random, "choice", lambda seq: "face")  # player guessed "pile" -> loses

    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=30015, display_name="AdminPlayer"))

    await cog.coinflip.callback(cog, ctx, 100, "pile", "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 30015))
    assert economy is None or economy.balance == 0
    assert "bypass" in ctx.last_text()


async def test_coinflip_bypass_credits_full_gain_on_win(db_session, monkeypatch):
    monkeypatch.setattr(random, "choice", lambda seq: "pile")

    cog = _cog(db_session)
    ctx = FakeContext(await make_admin(db_session, id=30016, display_name="AdminWinner"))

    await cog.coinflip.callback(cog, ctx, 100, "pile", "bypass")

    economy = await db_session.get(Economy, (settings.guild_id, 30016))
    assert economy.balance == 200  # full 2x payout, no stake ever debited


async def test_coinflip_bypass_ignored_for_non_admin(db_session):
    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30017, display_name="RegularPlayer"))

    await cog.coinflip.callback(cog, ctx, 100, "pile", "bypass")

    assert "insuffisant" in ctx.last_text()


async def test_coinflip_insurance_refunds_a_loss(db_session, monkeypatch):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 30018, "Insured")
    await add_balance(db_session, settings.guild_id, 30018, 500)
    await grant_effect(db_session, settings.guild_id, 30018, "casino_insurance")
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "face")  # player guessed "pile" -> loses

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30018, display_name="Insured"))

    await cog.coinflip.callback(cog, ctx, 100, "pile")

    economy = await db_session.get(Economy, (settings.guild_id, 30018))
    assert economy.balance == 500  # stake refunded, net zero
    assert "Assurance" in ctx.last_text()


async def test_coinflip_insurance_is_not_consumed_on_a_win(db_session, monkeypatch):
    from services.effects import grant_effect, has_active

    await get_or_create_user(db_session, settings.guild_id, 30019, "LuckyInsured")
    await add_balance(db_session, settings.guild_id, 30019, 500)
    await grant_effect(db_session, settings.guild_id, 30019, "casino_insurance")
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "pile")

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30019, display_name="LuckyInsured"))

    await cog.coinflip.callback(cog, ctx, 100, "pile")

    assert await has_active(db_session, settings.guild_id, 30019, "casino_insurance") is True


async def test_coinflip_double_win_doubles_the_net_profit(db_session, monkeypatch):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 30020, "DoubleWinner")
    await add_balance(db_session, settings.guild_id, 30020, 500)
    await grant_effect(db_session, settings.guild_id, 30020, "casino_double_win")
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "pile")

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30020, display_name="DoubleWinner"))

    await cog.coinflip.callback(cog, ctx, 100, "pile")

    # Normal win nets +100 (200 gain - 100 stake); doubled net profit -> +200.
    economy = await db_session.get(Economy, (settings.guild_id, 30020))
    assert economy.balance == 700
    assert "Double gain" in ctx.last_text()


async def test_coinflip_free_bet_does_not_debit_the_stake_even_on_a_loss(db_session, monkeypatch):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 30021, "FreeBetter")
    await add_balance(db_session, settings.guild_id, 30021, 500)
    await grant_effect(db_session, settings.guild_id, 30021, "casino_free_bet", uses=1)
    await db_session.commit()

    monkeypatch.setattr(random, "choice", lambda seq: "face")  # player guessed "pile" -> loses

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30021, display_name="FreeBetter"))

    await cog.coinflip.callback(cog, ctx, 100, "pile")

    economy = await db_session.get(Economy, (settings.guild_id, 30021))
    assert economy.balance == 500  # stake never debited
    assert "Pari gratuit" in ctx.last_text()


async def test_jackpot_chance_boost_increases_win_probability(db_session, monkeypatch):
    from services.effects import grant_effect

    await get_or_create_user(db_session, settings.guild_id, 30022, "BoostedJackpotter")
    await add_balance(db_session, settings.guild_id, 30022, 500)
    await grant_effect(db_session, settings.guild_id, 30022, "casino_jackpot_chance_boost", magnitude=10.0)
    await db_session.commit()

    # 0.05 would lose at the base 1% chance but wins once boosted x10 to 10%.
    monkeypatch.setattr(random, "random", lambda: 0.05)

    from services.casino import add_to_jackpot

    await add_to_jackpot(db_session, settings.guild_id, 1000)
    await db_session.commit()

    cog = _cog(db_session)
    ctx = FakeContext(FakeUser(id=30022, display_name="BoostedJackpotter"))

    await cog.jackpot.callback(cog, ctx, 100)

    assert "JACKPOT" in ctx.last_text()
