# Colombina — Profil, Stats & Classements (Tranche D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `/profile` (Pillow image card + text stats), `/leaderboard` (3 rankings), the daily `message_stats`/`voice_stats` tracking that feeds them, and a weekly periodic sweep that grants the 4 classement badges and rotates 3 Discord roles to the current #1 of each ranking.

**Architecture:** Same layering as tranches A-C — ranking queries, badge-sweep logic, role-config parsing, profile-stat aggregation, and Pillow card rendering all live in `services/`, framework-free and unit-tested against the sqlite `db_session` fixture; `cogs/` are thin adapters. The weekly role rotation's actual Discord I/O (`role.members`, `add_roles`/`remove_roles`) lives in a cog, but the "who should hold this role now" decision is a pure, tested function. No schema changes — every table this tranche reads/writes already exists.

**Tech Stack:** Same as tranches A-C, plus Pillow (image generation) — Python 3.12+, discord.py 2.x, SQLAlchemy 2.0 async, pytest + pytest-asyncio.

## Global Constraints

- Spec of record: `colombina/docs/superpowers/specs/2026-07-21-profil-stats-classements-design.md`.
- No `/stats` command — its content is folded into `/profile`'s text embed.
- `/profile` card (Pillow image): avatar, username, level, XP progress bar, prestige, coin balance, badge names as text (no color-emoji rendering — Pillow's default font doesn't handle it). Default Pillow font (`ImageFont.load_default()`), no bundled `.ttf`.
- `/profile`'s text embed (same message, alongside the image): total messages sent (all-time), total voice seconds (all-time), today's progress on the 3 daily quests, chest keys owned by rarity.
- `/leaderboard type:xp|messages|vocal`: top 10, no pagination.
- 4 classement badges, granted via the existing `services/rewards.py::grant_badge_by_key` (never reimplemented), **never revoked**, matching the rest of the badge system:
  - `roi_du_chat` → current #1 of the messages leaderboard
  - `maitre_vocal` → current #1 of the voice leaderboard
  - `top_10` → anyone currently in the top 10 of the XP leaderboard (cumulative — different people can earn this across different weekly sweeps)
  - `ancien` → `users.created_at` at least **365 days** ago
- 3 Discord roles (distinct from the badges above), rotated weekly to the current #1 of each ranking (messages/vocal/XP), configured via `colombina/config/leaderboard_roles.txt` (already created, format `key: role_id`, one of `roi_du_chat`/`maitre_vocal`/`top_10` per line, empty value = no role configured for that ranking yet). No new DB state to track who holds a role — read live from Discord (`role.members`) at each sweep.
- Weekly sweep: `discord.py` `tasks.loop(hours=168)`, started from `cog_load`, no calendar-day alignment.
- `server_stats` is untouched — nothing in this tranche reads or writes it.
- All new game logic goes in `services/`, framework-free; `cogs/` stay thin, except the weekly sweep's actual Discord role I/O which cannot be meaningfully pulled out of the cog (the *decision* of who to add/remove is still a pure, tested function).
- No placeholders/TODOs.

---

### Task 1: Leaderboard queries

**Files:**
- Create: `colombina/services/leaderboard.py`
- Test: `colombina/tests/test_service_leaderboard.py`

**Interfaces:**
- Consumes: `models.users.User`, `models.levels.Level`, `models.stats.MessageStat`/`VoiceStat` (tranche A).
- Produces: `services.leaderboard.LeaderboardEntry` (dataclass: `user_id: int`, `username: str`, `score: int`), `services.leaderboard.get_xp_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]`, `services.leaderboard.get_message_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]`, `services.leaderboard.get_voice_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]` — all ordered by `score` descending. Tasks 2, 9, 10 all consume these.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_leaderboard.py`:
```python
from datetime import date

from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.leaderboard import get_message_leaderboard, get_voice_leaderboard, get_xp_leaderboard


async def test_get_xp_leaderboard_orders_by_xp_desc(db_session):
    db_session.add_all(
        [
            User(discord_id=30001, username="Low"),
            User(discord_id=30002, username="High"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Level(user_id=30001, xp=100, level=1, prestige=0),
            Level(user_id=30002, xp=500, level=2, prestige=0),
        ]
    )
    await db_session.commit()

    entries = await get_xp_leaderboard(db_session, limit=10)

    assert [e.username for e in entries] == ["High", "Low"]
    assert entries[0].score == 500


async def test_get_xp_leaderboard_respects_limit(db_session):
    users = [User(discord_id=30100 + i, username=f"U{i}") for i in range(15)]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all([Level(user_id=30100 + i, xp=i * 10, level=0, prestige=0) for i in range(15)])
    await db_session.commit()

    entries = await get_xp_leaderboard(db_session, limit=10)

    assert len(entries) == 10
    assert entries[0].score == 140


async def test_get_message_leaderboard_sums_across_dates(db_session):
    db_session.add(User(discord_id=30002, username="Chatty"))
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(user_id=30002, date=date(2026, 7, 20), count=10),
            MessageStat(user_id=30002, date=date(2026, 7, 21), count=15),
        ]
    )
    await db_session.commit()

    entries = await get_message_leaderboard(db_session, limit=10)

    assert entries[0].username == "Chatty"
    assert entries[0].score == 25


async def test_get_voice_leaderboard_sums_across_dates(db_session):
    db_session.add(User(discord_id=30003, username="Talker"))
    await db_session.flush()
    db_session.add_all(
        [
            VoiceStat(user_id=30003, date=date(2026, 7, 20), seconds=600),
            VoiceStat(user_id=30003, date=date(2026, 7, 21), seconds=1200),
        ]
    )
    await db_session.commit()

    entries = await get_voice_leaderboard(db_session, limit=10)

    assert entries[0].username == "Talker"
    assert entries[0].score == 1800


async def test_leaderboards_return_empty_list_when_no_data(db_session):
    assert await get_xp_leaderboard(db_session) == []
    assert await get_message_leaderboard(db_session) == []
    assert await get_voice_leaderboard(db_session) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_leaderboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.leaderboard'`

- [ ] **Step 3: Write `services/leaderboard.py`**

```python
from dataclasses import dataclass

from sqlalchemy import func, select

from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User


@dataclass
class LeaderboardEntry:
    user_id: int
    username: str
    score: int


async def get_xp_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.discord_id, User.username, Level.xp)
        .join(Level, Level.user_id == User.discord_id)
        .order_by(Level.xp.desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=row[2]) for row in result.all()]


async def get_message_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.discord_id, User.username, func.sum(MessageStat.count).label("total"))
        .join(MessageStat, MessageStat.user_id == User.discord_id)
        .group_by(User.discord_id, User.username)
        .order_by(func.sum(MessageStat.count).desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=int(row[2])) for row in result.all()]


async def get_voice_leaderboard(session, limit: int = 10) -> list[LeaderboardEntry]:
    result = await session.execute(
        select(User.discord_id, User.username, func.sum(VoiceStat.seconds).label("total"))
        .join(VoiceStat, VoiceStat.user_id == User.discord_id)
        .group_by(User.discord_id, User.username)
        .order_by(func.sum(VoiceStat.seconds).desc())
        .limit(limit)
    )
    return [LeaderboardEntry(user_id=row[0], username=row[1], score=int(row[2])) for row in result.all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_leaderboard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): XP/message/voice leaderboard queries (services/leaderboard.py)"
```

---

### Task 2: Classement badge sweep

**Files:**
- Create: `colombina/services/classement_badges.py`
- Test: `colombina/tests/test_service_classement_badges.py`

**Interfaces:**
- Consumes: `services.leaderboard.get_xp_leaderboard`/`get_message_leaderboard`/`get_voice_leaderboard` (Task 1), `services.rewards.grant_badge_by_key`/`RewardOutcome` (tranche B), `models.users.User.created_at`, `models.badges.Badge`/`UserBadge` (tranche A).
- Produces: `services.classement_badges.ANCIEN_THRESHOLD_DAYS = 365`, `services.classement_badges.sweep_classement_badges(session, now: datetime) -> list[tuple[int, RewardOutcome]]` — grants (idempotently) `roi_du_chat` to the #1 of messages, `maitre_vocal` to the #1 of voice, `top_10` to everyone in the XP top 10, `ancien` to everyone with `created_at <= now - 365 days`; returns only the badges that were **newly** granted this call (not re-announcing badges a user already had), as `(user_id, RewardOutcome)` pairs. Task 10 (`cogs/classement_roles.py`) calls this.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_classement_badges.py`:
```python
from datetime import datetime, timedelta, timezone

from models.badges import Badge, UserBadge
from models.levels import Level
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.classement_badges import sweep_classement_badges


async def _seed_badges(db_session):
    db_session.add_all(
        [
            Badge(key="roi_du_chat", name="Roi du Chat", description="d", icon="💬", rarity="epique"),
            Badge(key="maitre_vocal", name="Maître Vocal", description="d", icon="🎙️", rarity="epique"),
            Badge(key="top_10", name="Top 10", description="d", icon="🔟", rarity="rare"),
            Badge(key="ancien", name="Ancien", description="d", icon="⏳", rarity="epique"),
        ]
    )
    await db_session.commit()


async def test_sweep_grants_roi_du_chat_to_message_leader(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(discord_id=31001, username="Chatty", created_at=now))
    await db_session.flush()
    db_session.add(MessageStat(user_id=31001, date=now.date(), count=100))
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()

    assert any(user_id == 31001 and outcome.reward_value == "roi_du_chat" for user_id, outcome in outcomes)

    from sqlalchemy import select

    result = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 31001))
    badge_ids = {row.badge_id for row in result.scalars().all()}
    badge_result = await db_session.execute(select(Badge).where(Badge.key == "roi_du_chat"))
    assert badge_result.scalar_one().id in badge_ids


async def test_sweep_grants_maitre_vocal_to_voice_leader(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(discord_id=31002, username="Talker", created_at=now))
    await db_session.flush()
    db_session.add(VoiceStat(user_id=31002, date=now.date(), seconds=3600))
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()

    assert any(user_id == 31002 and outcome.reward_value == "maitre_vocal" for user_id, outcome in outcomes)


async def test_sweep_grants_top_10_to_everyone_in_xp_top_ten(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    users = [User(discord_id=31100 + i, username=f"U{i}", created_at=now) for i in range(12)]
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all([Level(user_id=31100 + i, xp=i * 100, level=0, prestige=0) for i in range(12)])
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()

    top_10_grantees = {user_id for user_id, outcome in outcomes if outcome.reward_value == "top_10"}
    assert len(top_10_grantees) == 10
    assert 31100 not in top_10_grantees  # lowest XP, rank 12, not in top 10
    assert 31101 not in top_10_grantees  # rank 11, not in top 10


async def test_sweep_grants_ancien_to_tenured_users_only(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add_all(
        [
            User(discord_id=31003, username="OldTimer", created_at=now - timedelta(days=400)),
            User(discord_id=31004, username="Newbie", created_at=now - timedelta(days=10)),
        ]
    )
    await db_session.commit()

    outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()

    ancien_grantees = {user_id for user_id, outcome in outcomes if outcome.reward_value == "ancien"}
    assert ancien_grantees == {31003}


async def test_sweep_does_not_re_announce_already_held_badges(db_session):
    await _seed_badges(db_session)
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    db_session.add(User(discord_id=31005, username="Chatty2", created_at=now))
    await db_session.flush()
    db_session.add(MessageStat(user_id=31005, date=now.date(), count=100))
    await db_session.commit()

    first_outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()
    assert any(user_id == 31005 for user_id, _ in first_outcomes)

    second_outcomes = await sweep_classement_badges(db_session, now)
    await db_session.commit()
    assert not any(user_id == 31005 for user_id, _ in second_outcomes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_classement_badges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.classement_badges'`

- [ ] **Step 3: Write `services/classement_badges.py`**

```python
from datetime import datetime, timedelta

from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.users import User
from services.leaderboard import get_message_leaderboard, get_voice_leaderboard, get_xp_leaderboard
from services.rewards import RewardOutcome, grant_badge_by_key

ANCIEN_THRESHOLD_DAYS = 365


async def sweep_classement_badges(session, now: datetime) -> list[tuple[int, RewardOutcome]]:
    outcomes: list[tuple[int, RewardOutcome]] = []

    message_leaderboard = await get_message_leaderboard(session, limit=1)
    if message_leaderboard:
        outcome = await _grant_if_new(session, message_leaderboard[0].user_id, "roi_du_chat")
        if outcome is not None:
            outcomes.append((message_leaderboard[0].user_id, outcome))

    voice_leaderboard = await get_voice_leaderboard(session, limit=1)
    if voice_leaderboard:
        outcome = await _grant_if_new(session, voice_leaderboard[0].user_id, "maitre_vocal")
        if outcome is not None:
            outcomes.append((voice_leaderboard[0].user_id, outcome))

    xp_leaderboard = await get_xp_leaderboard(session, limit=10)
    for entry in xp_leaderboard:
        outcome = await _grant_if_new(session, entry.user_id, "top_10")
        if outcome is not None:
            outcomes.append((entry.user_id, outcome))

    cutoff = now - timedelta(days=ANCIEN_THRESHOLD_DAYS)
    tenured_result = await session.execute(select(User.discord_id).where(User.created_at <= cutoff))
    for (user_id,) in tenured_result.all():
        outcome = await _grant_if_new(session, user_id, "ancien")
        if outcome is not None:
            outcomes.append((user_id, outcome))

    return outcomes


async def _grant_if_new(session, user_id: int, badge_key: str) -> RewardOutcome | None:
    badge_result = await session.execute(select(Badge).where(Badge.key == badge_key))
    badge = badge_result.scalar_one()

    existing = await session.execute(
        select(UserBadge).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
    )
    already_had = existing.scalar_one_or_none() is not None

    outcome = await grant_badge_by_key(session, user_id, badge_key)

    return None if already_had else outcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_classement_badges.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): classement badge sweep (services/classement_badges.py)"
```

---

### Task 3: Leaderboard role config parsing + role-change decision

**Files:**
- Create: `colombina/services/leaderboard_roles.py`
- Test: `colombina/tests/test_service_leaderboard_roles.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `services.leaderboard_roles.parse_role_config(text: str) -> dict[str, int | None]` (parses `key: value` lines, `#`-prefixed lines and blank lines ignored, empty value → `None`), `services.leaderboard_roles.compute_role_changes(current_holder_ids: set[int], new_holder_id: int | None) -> tuple[set[int], int | None]` (returns `(ids_to_remove, id_to_add)`; `id_to_add` is `None` if the current #1 already holds the role or there's no #1). Task 10 (`cogs/classement_roles.py`) uses both.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_leaderboard_roles.py`:
```python
from services.leaderboard_roles import compute_role_changes, parse_role_config


def test_parse_role_config_reads_filled_and_empty_values():
    text = """# comment line
roi_du_chat: 123456789
maitre_vocal:
top_10: 987654321
"""
    config = parse_role_config(text)

    assert config == {"roi_du_chat": 123456789, "maitre_vocal": None, "top_10": 987654321}


def test_parse_role_config_ignores_blank_lines():
    text = "roi_du_chat: 111\n\nmaitre_vocal: 222\n"

    config = parse_role_config(text)

    assert config == {"roi_du_chat": 111, "maitre_vocal": 222}


def test_compute_role_changes_removes_old_holders_adds_new():
    to_remove, to_add = compute_role_changes({1, 2}, 3)

    assert to_remove == {1, 2}
    assert to_add == 3


def test_compute_role_changes_no_change_when_holder_unchanged():
    to_remove, to_add = compute_role_changes({1}, 1)

    assert to_remove == set()
    assert to_add is None


def test_compute_role_changes_no_leaderboard_data_removes_all_keeps_none_to_add():
    to_remove, to_add = compute_role_changes({1, 2}, None)

    assert to_remove == {1, 2}
    assert to_add is None


def test_compute_role_changes_empty_holders_adds_new_leader():
    to_remove, to_add = compute_role_changes(set(), 5)

    assert to_remove == set()
    assert to_add == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_leaderboard_roles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.leaderboard_roles'`

- [ ] **Step 3: Write `services/leaderboard_roles.py`**

```python
def parse_role_config(text: str) -> dict[str, int | None]:
    config: dict[str, int | None] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        config[key] = int(value) if value else None
    return config


def compute_role_changes(current_holder_ids: set[int], new_holder_id: int | None) -> tuple[set[int], int | None]:
    if new_holder_id is None:
        return current_holder_ids, None
    to_remove = current_holder_ids - {new_holder_id}
    to_add = None if new_holder_id in current_holder_ids else new_holder_id
    return to_remove, to_add
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_leaderboard_roles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): leaderboard role config parsing and role-change logic"
```

---

### Task 4: Profile stats aggregation

**Files:**
- Create: `colombina/services/profile_stats.py`
- Test: `colombina/tests/test_service_profile_stats.py`

**Interfaces:**
- Consumes: `models.stats.MessageStat`/`VoiceStat`, `models.quests.Quest`/`UserQuest`, `models.keys.UserKey` (tranches A/B).
- Produces: `services.profile_stats.QuestProgressView` (dataclass: `description: str`, `progress: int`, `target_count: int`, `completed: bool`), `services.profile_stats.ProfileStats` (dataclass: `total_messages: int`, `total_voice_seconds: int`, `quests_today: list[QuestProgressView]`, `keys_by_rarity: dict[str, int]`), `services.profile_stats.gather_profile_stats(session, user_id: int, today: date) -> ProfileStats`. Task 8 (`cogs/profile.py`) uses this.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_profile_stats.py`:
```python
from datetime import date

from models.keys import UserKey
from models.quests import Quest, UserQuest
from models.stats import MessageStat, VoiceStat
from models.users import User
from services.profile_stats import gather_profile_stats


async def test_gather_profile_stats_sums_messages_and_voice_across_dates(db_session):
    user = User(discord_id=32001, username="Statful")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            MessageStat(user_id=32001, date=date(2026, 7, 20), count=10),
            MessageStat(user_id=32001, date=date(2026, 7, 21), count=5),
            VoiceStat(user_id=32001, date=date(2026, 7, 20), seconds=600),
            VoiceStat(user_id=32001, date=date(2026, 7, 21), seconds=1200),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, 32001, date(2026, 7, 21))

    assert stats.total_messages == 15
    assert stats.total_voice_seconds == 1800


async def test_gather_profile_stats_returns_zero_for_new_user(db_session):
    user = User(discord_id=32002, username="Fresh")
    db_session.add(user)
    await db_session.commit()

    stats = await gather_profile_stats(db_session, 32002, date(2026, 7, 21))

    assert stats.total_messages == 0
    assert stats.total_voice_seconds == 0
    assert stats.quests_today == []
    assert stats.keys_by_rarity == {}


async def test_gather_profile_stats_includes_only_todays_quests(db_session):
    user = User(discord_id=32003, username="Grinder")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()
    db_session.add_all(
        [
            UserQuest(user_id=32003, quest_id=quest.id, date=date(2026, 7, 21), progress=10, completed=False),
            UserQuest(user_id=32003, quest_id=quest.id, date=date(2026, 7, 20), progress=25, completed=True),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, 32003, date(2026, 7, 21))

    assert len(stats.quests_today) == 1
    assert stats.quests_today[0].description == "Envoyer 25 messages"
    assert stats.quests_today[0].progress == 10
    assert stats.quests_today[0].target_count == 25
    assert stats.quests_today[0].completed is False


async def test_gather_profile_stats_includes_keys_by_rarity(db_session):
    user = User(discord_id=32004, username="KeyHolder")
    db_session.add(user)
    await db_session.flush()
    db_session.add_all(
        [
            UserKey(user_id=32004, rarity="commun", count=3),
            UserKey(user_id=32004, rarity="rare", count=1),
        ]
    )
    await db_session.commit()

    stats = await gather_profile_stats(db_session, 32004, date(2026, 7, 21))

    assert stats.keys_by_rarity == {"commun": 3, "rare": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_profile_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.profile_stats'`

- [ ] **Step 3: Write `services/profile_stats.py`**

```python
from dataclasses import dataclass, field
from datetime import date as Date

from sqlalchemy import func, select

from models.keys import UserKey
from models.quests import Quest, UserQuest
from models.stats import MessageStat, VoiceStat


@dataclass
class QuestProgressView:
    description: str
    progress: int
    target_count: int
    completed: bool


@dataclass
class ProfileStats:
    total_messages: int
    total_voice_seconds: int
    quests_today: list[QuestProgressView] = field(default_factory=list)
    keys_by_rarity: dict[str, int] = field(default_factory=dict)


async def gather_profile_stats(session, user_id: int, today: Date) -> ProfileStats:
    total_messages_result = await session.execute(
        select(func.sum(MessageStat.count)).where(MessageStat.user_id == user_id)
    )
    total_messages = total_messages_result.scalar_one_or_none() or 0

    total_voice_result = await session.execute(
        select(func.sum(VoiceStat.seconds)).where(VoiceStat.user_id == user_id)
    )
    total_voice_seconds = total_voice_result.scalar_one_or_none() or 0

    quests_result = await session.execute(
        select(UserQuest, Quest)
        .join(Quest, Quest.id == UserQuest.quest_id)
        .where(UserQuest.user_id == user_id, UserQuest.date == today)
    )
    quests_today = [
        QuestProgressView(
            description=quest.description,
            progress=user_quest.progress,
            target_count=quest.target_count,
            completed=user_quest.completed,
        )
        for user_quest, quest in quests_result.all()
    ]

    keys_result = await session.execute(select(UserKey.rarity, UserKey.count).where(UserKey.user_id == user_id))
    keys_by_rarity = {rarity: count for rarity, count in keys_result.all()}

    return ProfileStats(
        total_messages=total_messages,
        total_voice_seconds=total_voice_seconds,
        quests_today=quests_today,
        keys_by_rarity=keys_by_rarity,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_profile_stats.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): profile stats aggregation (services/profile_stats.py)"
```

---

### Task 5: Profile card image rendering

**Files:**
- Modify: `colombina/requirements.txt`
- Create: `colombina/services/profile_card.py`
- Test: `colombina/tests/test_service_profile_card.py`

**Interfaces:**
- Consumes: nothing beyond Pillow.
- Produces: `services.profile_card.ProfileCardData` (dataclass: `username: str`, `level: int`, `prestige: int`, `current_level_xp: int`, `xp_needed_for_next_level: int`, `balance: int`, `badge_names: list[str] = field(default_factory=list)`), `services.profile_card.render_profile_card(data: ProfileCardData, avatar_bytes: bytes) -> bytes` (returns PNG bytes, 800×300). Task 8 (`cogs/profile.py`) uses this.

- [ ] **Step 1: Add the Pillow dependency**

In `colombina/requirements.txt`, add this line (matching the existing pinning style):
```
Pillow>=10.0,<11.0
```

Run: `cd colombina && pip install -r requirements.txt`
Expected: Pillow installs successfully.

- [ ] **Step 2: Write the failing test**

`colombina/tests/test_service_profile_card.py`:
```python
import io

from PIL import Image

from services.profile_card import ProfileCardData, render_profile_card


def _fake_avatar_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), (200, 100, 50))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_render_profile_card_produces_correctly_sized_png():
    data = ProfileCardData(
        username="Ashen",
        level=5,
        prestige=0,
        current_level_xp=150,
        xp_needed_for_next_level=400,
        balance=1200,
        badge_names=["Débutant", "Actif"],
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.format == "PNG"
    assert image.size == (800, 300)


def test_render_profile_card_handles_no_badges():
    data = ProfileCardData(
        username="Newcomer", level=0, prestige=0, current_level_xp=0, xp_needed_for_next_level=100, balance=0
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.size == (800, 300)


def test_render_profile_card_handles_max_level_zero_xp_needed():
    data = ProfileCardData(
        username="MaxLevel", level=999, prestige=4, current_level_xp=0, xp_needed_for_next_level=0, balance=999999
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.size == (800, 300)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_profile_card.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.profile_card'`

- [ ] **Step 4: Write `services/profile_card.py`**

```python
import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 800
CARD_HEIGHT = 300
BACKGROUND_COLOR = (30, 30, 40)
TEXT_COLOR = (255, 255, 255)
BAR_BACKGROUND_COLOR = (60, 60, 70)
BAR_FILL_COLOR = (88, 166, 255)
AVATAR_SIZE = 128


@dataclass
class ProfileCardData:
    username: str
    level: int
    prestige: int
    current_level_xp: int
    xp_needed_for_next_level: int
    balance: int
    badge_names: list[str] = field(default_factory=list)


def render_profile_card(data: ProfileCardData, avatar_bytes: bytes) -> bytes:
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card)
    font = ImageFont.load_default()

    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB").resize((AVATAR_SIZE, AVATAR_SIZE))
    card.paste(avatar, (20, 20))

    text_x = 20 + AVATAR_SIZE + 20
    draw.text((text_x, 20), data.username, fill=TEXT_COLOR, font=font)
    draw.text((text_x, 45), f"Niveau {data.level}  •  Prestige {data.prestige}", fill=TEXT_COLOR, font=font)
    draw.text((text_x, 70), f"{data.balance} coins", fill=TEXT_COLOR, font=font)

    bar_x, bar_y, bar_width, bar_height = text_x, 100, 400, 20
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=BAR_BACKGROUND_COLOR)
    fill_ratio = 1.0
    if data.xp_needed_for_next_level > 0:
        fill_ratio = min(1.0, data.current_level_xp / data.xp_needed_for_next_level)
    draw.rectangle(
        [bar_x, bar_y, bar_x + int(bar_width * fill_ratio), bar_y + bar_height], fill=BAR_FILL_COLOR
    )
    draw.text(
        (bar_x, bar_y + bar_height + 5),
        f"{data.current_level_xp} / {data.xp_needed_for_next_level} XP",
        fill=TEXT_COLOR,
        font=font,
    )

    badges_text = ", ".join(data.badge_names) if data.badge_names else "Aucun badge"
    draw.text((text_x, 150), f"Badges : {badges_text}", fill=TEXT_COLOR, font=font)

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    return buffer.getvalue()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_profile_card.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): profile card image rendering (services/profile_card.py)"
```

---

### Task 6: Wire `message_stats` tracking into `cogs/leveling.py`

**Files:**
- Modify: `colombina/cogs/leveling.py`
- Test: `colombina/tests/test_cogs_leveling.py`

**Interfaces:**
- Consumes: `models.stats.MessageStat` (tranche A).
- Produces: `LevelingCog._record_message_stat(session, message) -> None` (get-or-creates today's `MessageStat` row for the author, `count += 1`, commits). Called from the existing `on_message` listener, after the tranche-C quest-tracking calls.

- [ ] **Step 1: Write the failing test**

Append to `colombina/tests/test_cogs_leveling.py`:
```python
from datetime import date as _date


async def test_on_message_increments_message_stat_for_the_day(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: _date(2026, 7, 21))

    author = FakeAuthor(id=24001, display_name="Statful")
    channel = _FakeChannel(id=800)

    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))
    await cog.on_message(FakeMessage(author=author, guild=FakeGuild(), channel=channel))

    from sqlalchemy import select
    from models.stats import MessageStat

    result = await db_session.execute(
        select(MessageStat).where(MessageStat.user_id == 24001, MessageStat.date == _date(2026, 7, 21))
    )
    stat = result.scalar_one()
    assert stat.count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_leveling.py -v`
Expected: FAIL — the new test's assertion fails with `NoResultFound` (no `MessageStat` row created yet).

- [ ] **Step 3: Update `cogs/leveling.py`**

Add the import at the top of the file, alongside the existing imports:
```python
from models.stats import MessageStat
from sqlalchemy import select
```

Add this method to `LevelingCog` (near `_apply_quest_progress`):
```python
    async def _record_message_stat(self, session, message) -> None:
        today = self._today()
        result = await session.execute(
            select(MessageStat).where(MessageStat.user_id == message.author.id, MessageStat.date == today)
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = MessageStat(user_id=message.author.id, date=today, count=0)
            session.add(stat)
        stat.count += 1
        await session.commit()
```

In `on_message`, after the existing `channels_3` quest-tracking block, add:
```python
            await self._record_message_stat(session, message)
```

The full `on_message` method should now end with (showing the tail for context — only the last line is new):
```python
            is_new_channel = self._channel_tracker.record_channel(
                message.author.id, message.channel.id, self._today()
            )
            if is_new_channel:
                await self._apply_quest_progress(session, message, "channels_3", 1)

            await self._record_message_stat(session, message)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_leveling.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): track daily message_stats in leveling cog"
```

---

### Task 7: Wire `voice_stats` tracking into `cogs/voice.py`

**Files:**
- Modify: `colombina/cogs/voice.py`
- Test: `colombina/tests/test_cogs_voice.py`

**Interfaces:**
- Consumes: `models.stats.VoiceStat` (tranche A).
- Produces: `VoiceCog._record_voice_stat(session, member_id: int, seconds: int) -> None` (get-or-creates today's `VoiceStat` row, `seconds += ...`, commits). Called from `on_voice_state_update` at the same point `payable_seconds` already feeds XP and the `voice_60min` quest.

- [ ] **Step 1: Write the failing test**

Append to `colombina/tests/test_cogs_voice.py`:
```python
from datetime import date as _date


async def test_on_voice_state_update_increments_voice_stat_for_the_day(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    monkeypatch.setattr(cog, "_today", lambda: _date(2026, 7, 21))
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=25001, display_name="Statful")
    other = FakeMember(id=25002, display_name="Other")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from sqlalchemy import select
    from models.stats import VoiceStat

    result = await db_session.execute(
        select(VoiceStat).where(VoiceStat.user_id == 25001, VoiceStat.date == _date(2026, 7, 21))
    )
    stat = result.scalar_one()
    assert stat.seconds == 600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_voice.py -v`
Expected: FAIL — no `VoiceStat` row exists yet.

- [ ] **Step 3: Update `cogs/voice.py`**

Add the import at the top of the file, alongside the existing imports:
```python
from models.stats import VoiceStat
from sqlalchemy import select
```

Add this method to `VoiceCog`:
```python
    async def _record_voice_stat(self, session, member_id: int, seconds: int) -> None:
        today = self._today()
        result = await session.execute(
            select(VoiceStat).where(VoiceStat.user_id == member_id, VoiceStat.date == today)
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = VoiceStat(user_id=member_id, date=today, seconds=0)
            session.add(stat)
        stat.seconds += seconds
        await session.commit()
```

In `on_voice_state_update`, after the existing `voice_60min` quest-tracking block (inside the `async with self._session() as session:` block), add:
```python
            await self._record_voice_stat(session, member.id, payable_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_voice.py -v`
Expected: PASS (all tests in the file, old and new)

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): track daily voice_stats in voice cog"
```

---

### Task 8: `cogs/profile.py` — `/profile`

**Files:**
- Create: `colombina/cogs/profile.py`
- Test: `colombina/tests/test_cogs_profile.py`

**Interfaces:**
- Consumes: `services.profile_card.ProfileCardData`/`render_profile_card` (Task 5), `services.profile_stats.gather_profile_stats` (Task 4), `services.leveling.xp_for_level` (tranche B), `services.users.get_or_create_user` (tranche B), `models.levels.Level`, `models.economy.Economy`, `models.badges.Badge`/`UserBadge` (tranche A).
- Produces: `cogs.profile.ProfileCog(commands.Cog)` with slash command `profile` (optional `membre` param, defaults to the caller); module-level `async def setup(bot)`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_profile.py`:
```python
import io

from PIL import Image

from cogs.profile import ProfileCog
from models.badges import Badge, UserBadge
from models.economy import Economy
from models.levels import Level
from models.users import User


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


class FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()


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

    user = User(discord_id=26001, username="Ashen")
    badge = Badge(key="debutant", name="Débutant", description="d", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()
    db_session.add_all(
        [
            Level(user_id=26001, xp=250, level=1, prestige=0),
            Economy(user_id=26001, balance=500),
            UserBadge(user_id=26001, badge_id=badge.id),
        ]
    )
    await db_session.commit()

    interaction = FakeInteraction(FakeUser(id=26001, display_name="Ashen"))

    await cog.profile.callback(cog, interaction, None)

    assert len(interaction.response.calls) == 1
    call = interaction.response.calls[0]
    assert "file" in call
    assert "embed" in call
    embed = call["embed"]
    field_names = [f.name for f in embed.fields]
    assert "Messages envoyés" in field_names

    cog._today = original_today


async def test_profile_defaults_to_caller_when_no_target_given(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ProfileCog(bot=FakeBot(session_factory))

    user = User(discord_id=26002, username="Solo")
    db_session.add(user)
    await db_session.commit()

    interaction = FakeInteraction(FakeUser(id=26002, display_name="Solo"))

    await cog.profile.callback(cog, interaction, None)

    assert len(interaction.response.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.profile'`

- [ ] **Step 3: Write `cogs/profile.py`**

```python
import io
from datetime import date, datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.economy import Economy
from models.levels import Level
from services.leveling import xp_for_level
from services.profile_card import ProfileCardData, render_profile_card
from services.profile_stats import gather_profile_stats
from services.users import get_or_create_user


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _today(self) -> date:
        return datetime.now(timezone.utc).date()

    @app_commands.command(name="profile", description="Affiche ta carte de profil")
    async def profile(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        target = membre or interaction.user
        avatar_bytes = await target.display_avatar.read()

        async with self._session() as session:
            await get_or_create_user(session, target.id, target.display_name)
            level_row = await session.get(Level, target.id)
            xp = level_row.xp if level_row is not None else 0
            level = level_row.level if level_row is not None else 0
            prestige = level_row.prestige if level_row is not None else 0

            economy = await session.get(Economy, target.id)
            balance = economy.balance if economy is not None else 0

            badge_result = await session.execute(
                select(Badge.name)
                .join(UserBadge, UserBadge.badge_id == Badge.id)
                .where(UserBadge.user_id == target.id)
            )
            badge_names = [row[0] for row in badge_result.all()]

            stats = await gather_profile_stats(session, target.id, self._today())
            await session.commit()

        current_level_xp = xp - xp_for_level(level)
        xp_needed = xp_for_level(level + 1) - xp_for_level(level)

        card_data = ProfileCardData(
            username=target.display_name,
            level=level,
            prestige=prestige,
            current_level_xp=current_level_xp,
            xp_needed_for_next_level=xp_needed,
            balance=balance,
            badge_names=badge_names,
        )
        card_bytes = render_profile_card(card_data, avatar_bytes)

        quest_lines = [
            f"{'✅' if q.completed else '▫️'} {q.description} ({min(q.progress, q.target_count)}/{q.target_count})"
            for q in stats.quests_today
        ]
        keys_lines = [f"{rarity}: {count}" for rarity, count in stats.keys_by_rarity.items()]

        embed = discord.Embed(title=f"Stats de {target.display_name}")
        embed.add_field(name="Messages envoyés", value=str(stats.total_messages), inline=True)
        embed.add_field(name="Temps vocal (secondes)", value=str(stats.total_voice_seconds), inline=True)
        embed.add_field(name="Quêtes du jour", value="\n".join(quest_lines) or "Aucune", inline=False)
        embed.add_field(name="Clés", value="\n".join(keys_lines) or "Aucune", inline=False)

        file = discord.File(io.BytesIO(card_bytes), filename="profile.png")
        embed.set_image(url="attachment://profile.png")

        await interaction.response.send_message(file=file, embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(ProfileCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_profile.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): profile cog (/profile image card + stats embed)"
```

---

### Task 9: `cogs/leaderboard.py` — `/leaderboard`

**Files:**
- Create: `colombina/cogs/leaderboard.py`
- Test: `colombina/tests/test_cogs_leaderboard.py`

**Interfaces:**
- Consumes: `services.leaderboard.get_xp_leaderboard`/`get_message_leaderboard`/`get_voice_leaderboard` (Task 1).
- Produces: `cogs.leaderboard.LeaderboardCog(commands.Cog)` with slash command `leaderboard` (choice param `type`: `xp`/`messages`/`vocal`); module-level `async def setup(bot)`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_leaderboard.py`:
```python
from datetime import date

from cogs.leaderboard import LeaderboardCog
from models.levels import Level
from models.users import User


class FakeChoice:
    def __init__(self, value):
        self.value = value


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()


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


async def test_leaderboard_xp_lists_top_users(db_session):
    db_session.add_all([User(discord_id=27001, username="Low"), User(discord_id=27002, username="High")])
    await db_session.flush()
    db_session.add_all(
        [Level(user_id=27001, xp=100, level=1, prestige=0), Level(user_id=27002, xp=500, level=2, prestige=0)]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))
    interaction = FakeInteraction()

    await cog.leaderboard.callback(cog, interaction, FakeChoice("xp"))

    content, ephemeral = interaction.response.messages[0]
    assert "High" in content
    assert content.index("High") < content.index("Low")
    assert ephemeral is False


async def test_leaderboard_reports_no_data_for_empty_ranking(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LeaderboardCog(bot=FakeBot(session_factory))
    interaction = FakeInteraction()

    await cog.leaderboard.callback(cog, interaction, FakeChoice("messages"))

    content, ephemeral = interaction.response.messages[0]
    assert "Aucune donnée" in content
    assert ephemeral is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_leaderboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.leaderboard'`

- [ ] **Step 3: Write `cogs/leaderboard.py`**

```python
import discord
from discord import app_commands
from discord.ext import commands

from services.leaderboard import get_message_leaderboard, get_voice_leaderboard, get_xp_leaderboard

LEADERBOARD_FETCHERS = {
    "xp": get_xp_leaderboard,
    "messages": get_message_leaderboard,
    "vocal": get_voice_leaderboard,
}

LEADERBOARD_LABELS = {
    "xp": "XP",
    "messages": "Messages",
    "vocal": "Temps vocal (secondes)",
}


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    @app_commands.command(name="leaderboard", description="Affiche le classement du serveur")
    @app_commands.choices(
        type=[
            app_commands.Choice(name="XP", value="xp"),
            app_commands.Choice(name="Messages", value="messages"),
            app_commands.Choice(name="Vocal", value="vocal"),
        ]
    )
    async def leaderboard(self, interaction: discord.Interaction, type: app_commands.Choice[str]) -> None:
        fetcher = LEADERBOARD_FETCHERS[type.value]
        async with self._session() as session:
            entries = await fetcher(session, limit=10)

        if not entries:
            await interaction.response.send_message("Aucune donnée pour ce classement.", ephemeral=True)
            return

        label = LEADERBOARD_LABELS[type.value]
        lines = [f"{i + 1}. **{entry.username}** — {entry.score} {label}" for i, entry in enumerate(entries)]
        await interaction.response.send_message(f"🏆 **Classement {label}**\n" + "\n".join(lines))


async def setup(bot) -> None:
    await bot.add_cog(LeaderboardCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_leaderboard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): leaderboard cog (/leaderboard xp|messages|vocal)"
```

---

### Task 10: `cogs/classement_roles.py` — weekly badge sweep + role rotation

**Files:**
- Create: `colombina/cogs/classement_roles.py`
- Test: `colombina/tests/test_cogs_classement_roles.py`

**Interfaces:**
- Consumes: `services.classement_badges.sweep_classement_badges` (Task 2), `services.leaderboard_roles.parse_role_config`/`compute_role_changes` (Task 3), `services.leaderboard.get_xp_leaderboard`/`get_message_leaderboard`/`get_voice_leaderboard` (Task 1), `services.announcements.format_reward_message` (tranche B).
- Produces: `cogs.classement_roles.ClassementRolesCog(commands.Cog)` with a `tasks.loop(hours=168)` weekly sweep (`cog_load` starts it, `cog_unload` cancels it), public methods `run_sweep(guild)` and `_rotate_roles(guild)` for testing; instance attribute `self._role_config_path` (defaults to `colombina/config/leaderboard_roles.txt`, overridable per-instance for tests); module-level `async def setup(bot)`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_classement_roles.py`:
```python
from datetime import date

from cogs.classement_roles import ClassementRolesCog
from models.badges import Badge
from models.levels import Level
from models.users import User


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
    def __init__(self, members_by_id, roles_by_id):
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
    user = User(discord_id=28001, username="Chatty")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MessageStat(user_id=28001, date=date(2026, 7, 21), count=50))
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: FakeChannel())
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10:\n", encoding="utf-8")
    cog._role_config_path = config_path

    member = FakeMember(id=28001, display_name="Chatty")
    guild = FakeGuild(members_by_id={28001: member}, roles_by_id={})

    await cog.run_sweep(guild)

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(select(UserBadge).where(UserBadge.user_id == 28001))
    assert result.scalar_one_or_none() is not None


async def test_rotate_roles_moves_role_from_old_holder_to_new_leader(db_session, tmp_path):
    db_session.add_all([User(discord_id=28101, username="OldLeader"), User(discord_id=28102, username="NewLeader")])
    await db_session.flush()
    db_session.add_all(
        [
            Level(user_id=28101, xp=100, level=1, prestige=0),
            Level(user_id=28102, xp=999, level=5, prestige=0),
        ]
    )
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10: 555\n", encoding="utf-8")
    cog._role_config_path = config_path

    old_leader = FakeMember(id=28101, display_name="OldLeader")
    new_leader = FakeMember(id=28102, display_name="NewLeader")
    role = FakeRole(id=555, members=[old_leader])
    guild = FakeGuild(members_by_id={28101: old_leader, 28102: new_leader}, roles_by_id={555: role})

    await cog._rotate_roles(guild)

    assert role in old_leader.removed_roles
    assert role in new_leader.added_roles


async def test_rotate_roles_skips_unconfigured_rankings(db_session, tmp_path):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = ClassementRolesCog(bot=FakeBot(session_factory))
    config_path = tmp_path / "leaderboard_roles.txt"
    config_path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10:\n", encoding="utf-8")
    cog._role_config_path = config_path

    guild = FakeGuild(members_by_id={}, roles_by_id={})

    await cog._rotate_roles(guild)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_classement_roles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.classement_roles'`

- [ ] **Step 3: Write `cogs/classement_roles.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

from discord.ext import commands, tasks

from config.settings import settings
from services.announcements import format_reward_message
from services.classement_badges import sweep_classement_badges
from services.leaderboard import get_message_leaderboard, get_voice_leaderboard, get_xp_leaderboard
from services.leaderboard_roles import compute_role_changes, parse_role_config

DEFAULT_ROLE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "leaderboard_roles.txt"

ROLE_CONFIG_LEADERBOARD = {
    "roi_du_chat": get_message_leaderboard,
    "maitre_vocal": get_voice_leaderboard,
    "top_10": get_xp_leaderboard,
}


class ClassementRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._role_config_path = DEFAULT_ROLE_CONFIG_PATH

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    async def cog_load(self) -> None:
        self.weekly_sweep.start()

    def cog_unload(self) -> None:
        self.weekly_sweep.cancel()

    @tasks.loop(hours=168)
    async def weekly_sweep(self) -> None:
        for guild in self.bot.guilds:
            await self.run_sweep(guild)

    @weekly_sweep.before_loop
    async def before_weekly_sweep(self) -> None:
        await self.bot.wait_until_ready()

    async def run_sweep(self, guild) -> None:
        async with self._session() as session:
            outcomes = await sweep_classement_badges(session, datetime.now(timezone.utc))
            await session.commit()

        channel = self._announcement_channel(guild)
        if channel is not None:
            for user_id, outcome in outcomes:
                member = guild.get_member(user_id)
                display_name = member.display_name if member is not None else str(user_id)
                await channel.send(format_reward_message(display_name, outcome))

        await self._rotate_roles(guild)

    async def _rotate_roles(self, guild) -> None:
        role_config = parse_role_config(self._role_config_path.read_text(encoding="utf-8"))

        for key, role_id in role_config.items():
            if role_id is None:
                continue
            role = guild.get_role(role_id)
            if role is None:
                continue

            fetcher = ROLE_CONFIG_LEADERBOARD.get(key)
            if fetcher is None:
                continue

            async with self._session() as session:
                leaderboard = await fetcher(session, limit=1)

            new_holder_id = leaderboard[0].user_id if leaderboard else None
            current_holder_ids = {member.id for member in role.members}
            to_remove, to_add = compute_role_changes(current_holder_ids, new_holder_id)

            for member_id in to_remove:
                member = guild.get_member(member_id)
                if member is not None:
                    await member.remove_roles(role)

            if to_add is not None:
                member = guild.get_member(to_add)
                if member is not None:
                    await member.add_roles(role)


async def setup(bot) -> None:
    await bot.add_cog(ClassementRolesCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_classement_roles.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd colombina && pytest tests/ -v -m "not integration" --ignore=tests/test_seed_data.py --ignore=tests/test_postgres_integration.py`
Expected: all tests from Tasks 1-10 (plus every tranche A/B/C test, untouched) PASS.

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): weekly classement badge sweep and role rotation cog"
```

---

## Plan Self-Review Notes

- **Spec coverage:** `/profile` (image + fused stats) → Tasks 4, 5, 8; `/leaderboard` (3 rankings) → Tasks 1, 9; daily `message_stats`/`voice_stats` tracking → Tasks 6, 7; 4 permanent classement badges → Task 2; 3 weekly-rotating Discord roles + `config/leaderboard_roles.txt` parsing → Tasks 3, 10; periodic sweep cadence (`tasks.loop(hours=168)`) → Task 10. Out-of-scope items (shop cosmetics on the card, bundled font/emoji rendering, `server_stats`, leaderboard pagination, persisted role-holder state) are correctly not implemented.
- **Placeholder scan:** no TBD/TODO; every step has complete code.
- **Type/interface consistency check:** `LeaderboardEntry`/`get_xp_leaderboard`/`get_message_leaderboard`/`get_voice_leaderboard` signatures match between Task 1 and their consumers (Tasks 2, 9, 10); `ProfileStats`/`QuestProgressView`/`gather_profile_stats` match between Task 4 and Task 8; `ProfileCardData`/`render_profile_card` match between Task 5 and Task 8; `parse_role_config`/`compute_role_changes` match between Task 3 and Task 10; `sweep_classement_badges`'s `(user_id, RewardOutcome)` return shape matches how Task 10's `run_sweep` unpacks it.
- **Testability decision honored:** the weekly role rotation's Discord I/O (`role.members`, `add_roles`/`remove_roles`) stays in `cogs/classement_roles.py`, but the "who to add/remove" decision is the pure, fully-tested `compute_role_changes` (Task 3) — the cog test in Task 10 only exercises the thin wiring around it, consistent with the plan's stated split.
- **Session/commit pattern:** both Task 6 and Task 7 append their stat-tracking commit to the same `async with self._session()` block already opened by the pre-existing `on_message`/`on_voice_state_update` (tranches B/C) — no new session-lifecycle risk introduced (unlike the quest-tracking bug caught during tranche C's plan review, these stat writes don't have a "not yet complete" branch that could be silently rolled back — every call unconditionally commits).
