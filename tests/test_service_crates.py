import random

import pytest

from config.settings import settings
from models.badges import Badge
from models.economy import Economy
from models.keys import UserKey
from models.users import User
from services.crate_loot_table import LOOT_TABLE, LootEntry
from services.crates import CRATE_RARITIES, NoKeyOwnedError, _resolve_entry, get_key_counts, open_crate
from services.keys import add_key

KNOWN_KINDS = (
    "coins",
    "xp",
    "badge",
    "key",
    "key_bundle",
    "cosmetic",
    "gacha_pull",
    "gacha_pull_guaranteed",
    "gacha_fragments",
    "gacha_boost",
    "key_upgrade",
    "bonus_open",
    "reroll",
    "mystery",
    "effect",
)


def _find(rarity: str, label: str) -> LootEntry:
    for entry in LOOT_TABLE[rarity]:
        if entry.label == label:
            return entry
    raise AssertionError(f"No entry labelled {label!r} in the {rarity!r} loot table")


async def _make_user(db_session, user_id: int) -> None:
    db_session.add(User(guild_id=settings.guild_id, user_id=user_id, username=f"user{user_id}"))
    await db_session.flush()


class FixedChoiceRng(random.Random):
    def __init__(self, index=0):
        super().__init__()
        self.index = index

    def choice(self, seq):
        return seq[self.index]


class LootEntryChoiceRng(random.Random):
    """Picks a specific loot-table entry, but leaves any other rng.choice() call
    (e.g. gacha character picks nested inside a resolved reward) to real randomness."""

    def __init__(self, index):
        super().__init__()
        self.index = index

    def choice(self, seq):
        if seq and isinstance(seq[0], LootEntry):
            return seq[self.index]
        return super().choice(seq)


# --- Structural checks over the real content -------------------------------------


def test_loot_table_has_an_entry_for_every_rarity():
    for rarity in CRATE_RARITIES:
        assert len(LOOT_TABLE[rarity]) > 0


def test_loot_table_kinds_are_all_known():
    for rarity in CRATE_RARITIES:
        for entry in LOOT_TABLE[rarity]:
            assert entry.kind in KNOWN_KINDS


def test_loot_table_mystery_entries_always_have_a_resolvable_candidate():
    from services.crates import MYSTERY_ELIGIBLE_KINDS

    for rarity in CRATE_RARITIES:
        has_mystery = any(e.kind == "mystery" for e in LOOT_TABLE[rarity])
        if not has_mystery:
            continue
        candidates = [e for e in LOOT_TABLE[rarity] if e.kind in MYSTERY_ELIGIBLE_KINDS]
        assert candidates, f"{rarity!r} has a mystery entry but nothing eligible to resolve it"


def test_loot_table_reroll_entries_always_have_a_non_reroll_candidate():
    for rarity in CRATE_RARITIES:
        has_reroll = any(e.kind == "reroll" for e in LOOT_TABLE[rarity])
        if not has_reroll:
            continue
        candidates = [e for e in LOOT_TABLE[rarity] if e.kind != "reroll"]
        assert candidates, f"{rarity!r} has a reroll entry but nothing else to reroll into"


@pytest.mark.parametrize("rarity", ["commun", "rare", "epique", "legendaire", "mythique", "divin"])
async def test_open_crate_never_crashes_on_real_content(db_session, rarity):
    user = User(guild_id=settings.guild_id, user_id=90000 + hash(rarity) % 1000, username=f"smoke_{rarity}")
    db_session.add(user)
    await db_session.flush()
    for _ in range(5):
        await add_key(db_session, settings.guild_id, user.user_id, rarity)
    await db_session.commit()

    rng = random.Random(1234)
    for _ in range(5):
        await open_crate(db_session, settings.guild_id, user.user_id, rarity, rng=rng, bypass=True)
        await db_session.commit()


# --- Kind-resolution behavior, tested directly against _resolve_entry ------------
# (independent of real loot-table content/positions, so a future content refresh
# can't silently desync these from what they claim to test)


async def test_resolve_entry_coins_credits_the_balance(db_session):
    await _make_user(db_session, 51003)
    entry = LootEntry(kind="coins", value=100, label="100 Coins")

    result = await _resolve_entry(db_session, settings.guild_id, 51003, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "coins"
    assert result.value == 100
    economy = await db_session.get(Economy, (settings.guild_id, 51003))
    assert economy.balance == 100


async def test_resolve_entry_badge_grants_the_badge(db_session):
    await _make_user(db_session, 51004)
    db_session.add(Badge(key="bois", name="Badge Bois", description="d", icon="🪵", rarity="commun"))
    await db_session.flush()
    entry = LootEntry(kind="badge", value="bois", label="Badge Bois")

    result = await _resolve_entry(db_session, settings.guild_id, 51004, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "badge"
    from sqlalchemy import select

    from models.badges import UserBadge

    assert (await db_session.execute(select(UserBadge).where(UserBadge.user_id == 51004))).scalar_one() is not None


async def test_resolve_entry_key_grants_one_key(db_session):
    await _make_user(db_session, 51005)
    entry = LootEntry(kind="key", value="commun", label="Clé commune")

    result = await _resolve_entry(db_session, settings.guild_id, 51005, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "key"
    assert result.value == "commun"
    from sqlalchemy import select

    key_result = await db_session.execute(select(UserKey).where(UserKey.user_id == 51005, UserKey.rarity == "commun"))
    assert key_result.scalar_one().count == 1


async def test_resolve_entry_key_bundle_grants_several_keys(db_session):
    await _make_user(db_session, 51021)
    entry = LootEntry(kind="key_bundle", value=("rare", 3), label="Clé rare x3")

    result = await _resolve_entry(db_session, settings.guild_id, 51021, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "key_bundle"
    from sqlalchemy import select

    key_result = await db_session.execute(select(UserKey).where(UserKey.user_id == 51021, UserKey.rarity == "rare"))
    assert key_result.scalar_one().count == 3


async def test_resolve_entry_cosmetic_is_stored(db_session):
    await _make_user(db_session, 51006)
    entry = LootEntry(kind="cosmetic", value=None, label='Titre "Apprenti"')

    result = await _resolve_entry(db_session, settings.guild_id, 51006, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "cosmetic"
    from sqlalchemy import select

    from models.cosmetic_rewards import UserCosmeticReward

    reward = (
        await db_session.execute(select(UserCosmeticReward).where(UserCosmeticReward.user_id == 51006))
    ).scalar_one()
    assert reward.reward_label == result.label
    assert reward.rarity == "commun"


async def test_resolve_entry_xp_is_returned_without_being_applied(db_session):
    await _make_user(db_session, 51007)
    entry = LootEntry(kind="xp", value=500, label="500 XP")

    result = await _resolve_entry(db_session, settings.guild_id, 51007, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "xp"
    assert result.value == 500
    from models.levels import Level

    assert await db_session.get(Level, (settings.guild_id, 51007)) is None  # not applied by the service


async def test_resolve_entry_gacha_pull_performs_pulls_and_records_history(db_session):
    import services.gacha_db as gacha_db_module

    await _make_user(db_session, 51012)
    entry = LootEntry(kind="gacha_pull", value=2, label="2 invocations gacha")

    result = await _resolve_entry(db_session, settings.guild_id, 51012, "epique", entry, random.Random())
    await db_session.commit()

    assert result.kind == "gacha_pull"
    assert len(result.pull_results) == 2
    history = await gacha_db_module.get_gacha_history(db_session, settings.guild_id, 51012)
    assert len(history) == 2


async def test_resolve_entry_gacha_pull_guaranteed_forces_the_minimum_rarity(db_session):
    await _make_user(db_session, 51013)
    entry = LootEntry(kind="gacha_pull_guaranteed", value=("Épique", 1), label="Invocation épique garantie")

    class AlwaysLowRoll(random.Random):
        def random(self):
            return 0.0  # would normally roll "Commun" — well below the guaranteed floor

    result = await _resolve_entry(db_session, settings.guild_id, 51013, "epique", entry, AlwaysLowRoll())
    await db_session.commit()

    assert result.kind == "gacha_pull_guaranteed"
    assert result.pull_results[0].rarity == "Épique"


async def test_resolve_entry_gacha_pull_guaranteed_with_count_performs_several_forced_pulls(db_session):
    await _make_user(db_session, 51022)
    entry = LootEntry(kind="gacha_pull_guaranteed", value=("Légendaire", 3), label="Invocation légendaire x3")

    class AlwaysLowRoll(random.Random):
        def random(self):
            return 0.0

    result = await _resolve_entry(db_session, settings.guild_id, 51022, "mythique", entry, AlwaysLowRoll())
    await db_session.commit()

    assert len(result.pull_results) == 3
    assert all(p.rarity == "Légendaire" for p in result.pull_results)


async def test_resolve_entry_gacha_fragments_credits_fragments(db_session):
    import services.gacha_db as gacha_db_module

    await _make_user(db_session, 51014)
    entry = LootEntry(kind="gacha_fragments", value=5, label="5 fragments gacha")

    result = await _resolve_entry(db_session, settings.guild_id, 51014, "epique", entry, random.Random())
    await db_session.commit()

    assert result.kind == "gacha_fragments"
    state = await gacha_db_module.get_gacha_state(db_session, settings.guild_id, 51014)
    assert state["fragments"] == 5


async def test_resolve_entry_gacha_boost_grants_an_active_bonus(db_session):
    from services.effects import get_active_bonus

    await _make_user(db_session, 51015)
    entry = LootEntry(kind="gacha_boost", value=(0.05, 3600), label="Boost gacha 1h")

    result = await _resolve_entry(db_session, settings.guild_id, 51015, "epique", entry, random.Random())
    await db_session.commit()

    assert result.kind == "gacha_boost"
    bonus = await get_active_bonus(db_session, settings.guild_id, 51015, "gacha_rate_boost")
    assert bonus == 0.05


async def test_resolve_entry_effect_grants_an_active_effect(db_session):
    from services.effects import has_active

    await _make_user(db_session, 51020)
    entry = LootEntry(
        kind="effect",
        value={"effect_type": "streak_protection", "magnitude": None, "uses": 1, "duration_seconds": None},
        label="Protection de série",
    )

    result = await _resolve_entry(db_session, settings.guild_id, 51020, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "effect"
    assert await has_active(db_session, settings.guild_id, 51020, "streak_protection") is True


async def test_resolve_entry_key_upgrade_consumes_and_grants_next_tier(db_session):
    await _make_user(db_session, 51016)
    await add_key(db_session, settings.guild_id, 51016, "rare")
    await db_session.commit()
    entry = LootEntry(kind="key_upgrade", value=None, label="Upgrade automatique d'une clé")

    class FirstOwnedRarity:
        def choice(self, seq):
            return seq[0]

    result = await _resolve_entry(db_session, settings.guild_id, 51016, "legendaire", entry, FirstOwnedRarity())
    await db_session.commit()

    assert result.kind == "key_upgrade"
    assert result.value == "epique"
    from sqlalchemy import select

    key_result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == 51016, UserKey.rarity == "epique")
    )
    assert key_result.scalar_one().count == 1


async def test_resolve_entry_key_upgrade_with_explicit_from_rarity(db_session):
    await _make_user(db_session, 51023)
    await add_key(db_session, settings.guild_id, 51023, "mythique")
    await db_session.commit()
    entry = LootEntry(kind="key_upgrade", value="mythique", label="Upgrade garanti en Divin")

    result = await _resolve_entry(db_session, settings.guild_id, 51023, "divin", entry, random.Random())
    await db_session.commit()

    assert result.value == "divin"
    from sqlalchemy import select

    key_result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == 51023, UserKey.rarity == "divin")
    )
    assert key_result.scalar_one().count == 1


async def test_resolve_entry_bonus_open_opens_extra_crates_without_consuming_a_key(db_session):
    await _make_user(db_session, 51017)
    entry = LootEntry(kind="bonus_open", value=("commun", 2), label="Triple ouverture")

    result = await _resolve_entry(db_session, settings.guild_id, 51017, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind == "bonus_open"
    assert len(result.extra_results) == 2  # both extra crates opened without ever needing an owned key


async def test_resolve_entry_reroll_replaces_the_result_with_a_non_reroll_entry(db_session):
    await _make_user(db_session, 51018)
    rarity_table = [
        LootEntry(kind="reroll", value=None, label="Reroll de box"),
        LootEntry(kind="coins", value=100, label="100 Coins"),
    ]

    class PicksSecond:
        def choice(self, seq):
            return seq[-1]

    result = await _resolve_entry(
        db_session, settings.guild_id, 51018, "commun", rarity_table[0], PicksSecond()
    )
    await db_session.commit()

    # the reroll branch reads from the real LOOT_TABLE[rarity], not our synthetic list,
    # so just assert the outcome is never itself a reroll.
    assert result.kind != "reroll"


async def test_resolve_entry_mystery_resolves_to_a_coins_xp_or_key_entry(db_session):
    await _make_user(db_session, 51019)
    entry = LootEntry(kind="mystery", value=None, label="Cadeau mystère")

    result = await _resolve_entry(db_session, settings.guild_id, 51019, "commun", entry, random.Random())
    await db_session.commit()

    assert result.kind in ("coins", "xp", "key")


# --- Real-content integration checks for a few specific, meaningful entries ------


async def test_open_crate_mythique_upgrade_entry_can_reach_divin(db_session):
    await _make_user(db_session, 51010)
    await add_key(db_session, settings.guild_id, 51010, "mythique")
    await add_key(db_session, settings.guild_id, 51010, "mythique")  # one to open the box, one to upgrade
    await db_session.commit()

    target = _find("mythique", "Upgrade aléatoire vers Divin")
    index = LOOT_TABLE["mythique"].index(target)

    result = await open_crate(
        db_session, settings.guild_id, 51010, "mythique", rng=LootEntryChoiceRng(index=index)
    )
    await db_session.commit()

    assert result.kind == "key_upgrade"
    assert result.value == "divin"


async def test_open_crate_divin_entry_resolves_through_real_content(db_session):
    await _make_user(db_session, 51011)
    await add_key(db_session, settings.guild_id, 51011, "divin")
    await db_session.commit()

    target = _find("divin", "Jackpot divin")
    index = LOOT_TABLE["divin"].index(target)

    result = await open_crate(db_session, settings.guild_id, 51011, "divin", rng=FixedChoiceRng(index=index))
    await db_session.commit()

    assert result.kind == "coins"
    assert result.value == 500000


async def test_get_key_counts_reflects_inventory(db_session):
    user = User(guild_id=settings.guild_id, user_id=51008, username="Counter")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await add_key(db_session, settings.guild_id, user.user_id, "epique")
    await db_session.commit()

    counts = await get_key_counts(db_session, settings.guild_id, user.user_id)

    assert counts == {"commun": 2, "rare": 0, "epique": 1, "legendaire": 0, "mythique": 0, "divin": 0}


async def test_open_crate_raises_without_a_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=51001, username="Empty")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(NoKeyOwnedError):
        await open_crate(db_session, settings.guild_id, user.user_id, "commun")


async def test_open_crate_consumes_a_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=51002, username="Opener")
    db_session.add(user)
    await db_session.flush()
    await add_key(db_session, settings.guild_id, user.user_id, "commun")
    await db_session.commit()

    await open_crate(db_session, settings.guild_id, user.user_id, "commun", rng=FixedChoiceRng(index=0))
    await db_session.commit()

    from sqlalchemy import select

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "commun")
    )
    assert result.scalar_one().count == 0


async def test_open_crate_bypass_works_without_owning_a_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=51009, username="BypassOpener")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    # No key at all — would normally raise NoKeyOwnedError.
    result = await open_crate(
        db_session, settings.guild_id, user.user_id, "commun", rng=FixedChoiceRng(index=0), bypass=True
    )
    await db_session.commit()

    assert result.kind is not None

    counts = await get_key_counts(db_session, settings.guild_id, user.user_id)
    assert counts["commun"] == 0  # never consumed, since none were owned
