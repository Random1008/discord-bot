# Colombina — XP & Progression (Tranche B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the core progression loop for Colombina — XP gain from messages, voice, reactions, admin-granted events, and validated invitations; the level formula and level-up reward/badge/key granting; prestige detection; and the Discord-side wiring (cogs) that dispatches it all, with announcements and role grants.

**Architecture:** All game-rule logic (XP amounts, level formula, prestige tiers, key-rarity rolls, reward dispatch, voice-session accounting, invite-use diffing) lives in `services/`, framework-free and unit-tested against an in-memory sqlite `db_session` fixture — no discord.py objects required. `cogs/` are thin discord.py event adapters that call into `services/`, plus one shared adapter (`cogs/xp_common.py`) that all XP-granting cogs use to persist XP, send announcements to the configured channel, and assign reward/prestige roles. Two additive Alembic migrations extend the tranche A schema (`invited_by_id`, `last_key_drop_level`, `user_keys`) and fix a data gap found in tranche A's seed migration (see Global Constraints).

**Tech Stack:** Same as tranche A — Python 3.12+, discord.py 2.x, SQLAlchemy 2.0 async (asyncpg), Alembic, pydantic-settings, pytest + pytest-asyncio (+ aiosqlite for fast tests, real Postgres via `DATABASE_URL` for seed/migration integration tests).

## Global Constraints

- Spec of record: `colombina/docs/superpowers/specs/2026-07-20-xp-progression-design.md` (amended this session — read the "Réaction reçue" row and the `item` reward-type bullet, both updated).
- Single-guild — no `guild_id` column or parameter anywhere in this tranche (unchanged from tranche A).
- Level never decreases. Prestige (I–IV) is a marker reached at levels 100/200/300/500, never a reset. Each `rewards` row for a given level is granted at most once per account, ever — this is guaranteed structurally by "level never decreases" + "grant only on the exact level(s) crossed by this XP gain," no separate ledger table.
- No cooldown on message XP — every non-bot message gives 5–15 XP.
- Voice XP is tracked by `on_voice_state_update` events, not a polling loop.
- Reaction XP (session decision, amends the original spec): `on_reaction_add` gives +2 XP to the message author (self-reactions ignored); `on_reaction_remove` subtracts 2 XP from the message author (self-reactions ignored too). This is the anti-farm mechanism — an add/remove cycle is net-zero. Subtraction is clamped so a user's XP never drops below the XP threshold of their currently stored level (`xp_for_level(level_row.level)`) — the stored `level` field itself is never recomputed downward.
- Invitation validated = when the invited member reaches **level 5** (checked once, at that exact level-up). Inviter receives +200 XP. Invite tracking uses the simple in-memory cache described in the spec (`guild.invites()` diff + `on_invite_create`) — explicitly accepted limitation for this tranche, no added persistence for invite-use counts (session decision).
- Level-90 "Coffre Mystère" reward (`reward_type=item`, session decision, amends the original spec): grants one chest key of random rarity (same distribution as the passive per-level key drop: Commun 60% / Rare 25% / Épique 10% / Légendaire 3.5% / Mythique 1% / Divin 0.5%), not coins.
- **Data gap found in tranche A's seed migration (this session):** the badges `actif` (niveau 5), `habitue` (niveau 20), `veteran` (niveau 40), `legendaire` (niveau 100) are seeded in the `badges` table but have **no matching `reward_type="badge"` row** in `rewards` — only a same-level `role` reward exists for each. Since tranche B's spec explicitly lists these four badges as in-scope ("Débutant, Actif, Habitué, Vétéran, Légendaire, Argent, Or, Platine, Diamant"), and reward-granting in this plan is driven entirely by the `rewards` table, Task 3 adds an additive migration inserting the four missing badge reward rows so all 9 level badges are actually grantable through the same code path.
- Badges "classement" (Roi du Chat, Maître Vocal, Top 10, Ancien) are out of scope — no reward row exists for them and this tranche must not add one.
- All new game logic goes in `services/`, pure and testable without mocking discord.py (per the spec's "Tests & architecture" section). `cogs/` stay thin.
- No placeholders/TODOs — every mechanic described in the spec must be implemented for real by the end of this plan, with the three amendments and the seed-data fix noted above.

---

### Task 1: Config additions (settings + `.env.example`)

**Files:**
- Modify: `colombina/config/settings.py`
- Modify: `colombina/.env.example`
- Test: `colombina/tests/test_settings.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: new optional string fields on `config.settings.Settings` / `config.settings.settings`: `level_up_channel_id`, `role_actif_id`, `role_habitue_id`, `role_veteran_id`, `role_legendaire_id`, `role_vip_bronze_id`, `role_vip_argent_id`, `role_premium_id`, `prestige_1_role_id`, `prestige_2_role_id`, `prestige_3_role_id`, `prestige_4_role_id` — all `str | None = None`. Task 15 (`cogs/xp_common.py`) reads these by attribute name.

- [ ] **Step 1: Write the failing test**

Append to `colombina/tests/test_settings.py`:
```python
def test_progression_role_and_channel_settings_default_to_none():
    settings = Settings()

    assert settings.level_up_channel_id is None
    assert settings.role_actif_id is None
    assert settings.role_habitue_id is None
    assert settings.role_veteran_id is None
    assert settings.role_legendaire_id is None
    assert settings.role_vip_bronze_id is None
    assert settings.role_vip_argent_id is None
    assert settings.role_premium_id is None
    assert settings.prestige_1_role_id is None
    assert settings.prestige_2_role_id is None
    assert settings.prestige_3_role_id is None
    assert settings.prestige_4_role_id is None


def test_progression_role_setting_reads_from_env(monkeypatch):
    monkeypatch.setenv("LEVEL_UP_CHANNEL_ID", "123456789")
    monkeypatch.setenv("PRESTIGE_1_ROLE_ID", "987654321")

    settings = Settings()

    assert settings.level_up_channel_id == "123456789"
    assert settings.prestige_1_role_id == "987654321"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_settings.py -v`
Expected: FAIL with `AttributeError` on `settings.level_up_channel_id` (field doesn't exist yet).

- [ ] **Step 3: Update `config/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str
    database_url: str
    redis_url: str
    command_prefix: str = "!"
    sql_echo: bool = False
    log_level: str = "INFO"

    level_up_channel_id: str | None = None
    role_actif_id: str | None = None
    role_habitue_id: str | None = None
    role_veteran_id: str | None = None
    role_legendaire_id: str | None = None
    role_vip_bronze_id: str | None = None
    role_vip_argent_id: str | None = None
    role_premium_id: str | None = None
    prestige_1_role_id: str | None = None
    prestige_2_role_id: str | None = None
    prestige_3_role_id: str | None = None
    prestige_4_role_id: str | None = None


settings = Settings()
```

- [ ] **Step 4: Update `.env.example`**

```
DISCORD_TOKEN=your-bot-token-here
DATABASE_URL=postgresql+asyncpg://colombina:colombina@localhost:5432/colombina
REDIS_URL=redis://localhost:6379/0
COMMAND_PREFIX=!
SQL_ECHO=false
LOG_LEVEL=INFO

# Reward role IDs and level-up announcement channel (tranche B)
LEVEL_UP_CHANNEL_ID=
ROLE_ACTIF_ID=
ROLE_HABITUE_ID=
ROLE_VETERAN_ID=
ROLE_LEGENDAIRE_ID=
ROLE_VIP_BRONZE_ID=
ROLE_VIP_ARGENT_ID=
ROLE_PREMIUM_ID=
PRESTIGE_1_ROLE_ID=
PRESTIGE_2_ROLE_ID=
PRESTIGE_3_ROLE_ID=
PRESTIGE_4_ROLE_ID=
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): add tranche B role/channel config settings"
```

---

### Task 2: Schema migration — invited_by_id, last_key_drop_level, user_keys

**Files:**
- Modify: `colombina/models/users.py`
- Modify: `colombina/models/levels.py`
- Create: `colombina/models/keys.py`
- Modify: `colombina/models/__init__.py`
- Create: `colombina/alembic/versions/` (new revision file, exact name generated by `alembic revision`)
- Test: `colombina/tests/test_models_progression.py`

**Interfaces:**
- Consumes: `database.base.Base` (tranche A), `models.users.User`, `models.levels.Level` (tranche A).
- Produces: `models.users.User.invited_by_id: int | None`, `models.levels.Level.last_key_drop_level: int` (default 0), `models.keys.UserKey` (PK `id`, `user_id` FK, `rarity: str`, `count: int` default 0, unique on `(user_id, rarity)`). Task 8 (`services/keys.py`) and Task 14 (invite cog) both import from here.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_models_progression.py`:
```python
from models.keys import UserKey
from models.levels import Level
from models.users import User


async def test_invited_by_and_last_key_drop_level_default(db_session):
    inviter = User(discord_id=5001, username="Inviter")
    invitee = User(discord_id=5002, username="Invitee", invited_by_id=5001)
    db_session.add_all([inviter, invitee])
    await db_session.flush()

    level = Level(user_id=invitee.discord_id, xp=0, level=0, prestige=0)
    db_session.add(level)
    await db_session.commit()

    fetched_invitee = await db_session.get(User, 5002)
    fetched_level = await db_session.get(Level, 5002)
    assert fetched_invitee.invited_by_id == 5001
    assert fetched_level.last_key_drop_level == 0


async def test_user_key_roundtrip(db_session):
    user = User(discord_id=5003, username="KeyHolder")
    db_session.add(user)
    await db_session.flush()

    key = UserKey(user_id=user.discord_id, rarity="rare", count=1)
    db_session.add(key)
    await db_session.commit()

    fetched = await db_session.get(UserKey, key.id)
    assert fetched.rarity == "rare"
    assert fetched.count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_models_progression.py -v`
Expected: FAIL — `TypeError: 'invited_by_id' is an invalid keyword argument for User` (column doesn't exist yet).

- [ ] **Step 3: Update `models/users.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class User(Base):
    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    invited_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.discord_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Update `models/levels.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Level(Base):
    __tablename__ = "levels"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), primary_key=True)
    xp: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prestige: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voice_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_key_drop_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_voice_reward_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Write `models/keys.py`**

```python
from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class UserKey(Base):
    __tablename__ = "user_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "rarity", name="uq_user_keys_user_rarity"),)
```

- [ ] **Step 6: Update `models/__init__.py`**

```python
from models.badges import Badge, UserBadge
from models.economy import Economy
from models.keys import UserKey
from models.levels import Level
from models.prestiges import Prestige
from models.quests import Quest, UserQuest
from models.rewards import Reward
from models.stats import MessageStat, ServerStat, VoiceStat
from models.users import User

__all__ = [
    "User",
    "Level",
    "Prestige",
    "Badge",
    "UserBadge",
    "Economy",
    "VoiceStat",
    "MessageStat",
    "ServerStat",
    "Quest",
    "UserQuest",
    "Reward",
    "UserKey",
]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_models_progression.py -v`
Expected: PASS

- [ ] **Step 8: Start Postgres and create the migration**

Run (reuse the tranche A dev container if it isn't already up):
```bash
docker start colombina-dev-postgres 2>/dev/null || docker run -d --name colombina-dev-postgres \
  -e POSTGRES_USER=colombina -e POSTGRES_PASSWORD=colombina -e POSTGRES_DB=colombina \
  -p 5432:5432 postgres:16-alpine
cd colombina && alembic revision -m "add invited_by_id, last_key_drop_level, user_keys"
```
Expected: a new revision file appears under `alembic/versions/`, `down_revision` auto-set to `'1cd155f760d3'` (the tranche A seed migration, the current head).

- [ ] **Step 9: Fill in the revision's `upgrade`/`downgrade`**

Open the generated file and replace its body with:
```python
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_by_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_users_invited_by_id_users", "users", "users", ["invited_by_id"], ["discord_id"]
    )
    op.add_column(
        "levels",
        sa.Column("last_key_drop_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "user_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.discord_id"), nullable=False),
        sa.Column("rarity", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "rarity", name="uq_user_keys_user_rarity"),
    )


def downgrade() -> None:
    op.drop_table("user_keys")
    op.drop_column("levels", "last_key_drop_level")
    op.drop_constraint("fk_users_invited_by_id_users", "users", type_="foreignkey")
    op.drop_column("users", "invited_by_id")
```

- [ ] **Step 10: Apply the migration**

Run: `cd colombina && cp -n .env.example .env` (if `.env` doesn't already exist, then edit it so `DATABASE_URL` and `DISCORD_TOKEN` are set as in tranche A Task 7) `&& alembic upgrade head`
Expected: command exits 0.

- [ ] **Step 11: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): schema migration for invited_by_id, last_key_drop_level, user_keys"
```

---

### Task 3: Seed-data fix — missing badge reward rows

**Files:**
- Create: `colombina/alembic/versions/` (new revision file, exact name generated by `alembic revision`)
- Modify: `colombina/tests/test_seed_data.py`

**Interfaces:**
- Consumes: the Task 2 migration chain, `models.rewards.Reward`.
- Produces: 4 additional `rewards` rows (`reward_type="badge"`) at levels 5, 20, 40, 100, so all 9 in-scope level badges (see Global Constraints) have a grantable reward row. Total reward row count becomes 20.

- [ ] **Step 1: Create the empty revision**

Run: `cd colombina && alembic revision -m "add missing level badge reward rows"`
Expected: a new revision file appears, chained after Task 2's revision.

- [ ] **Step 2: Fill in the revision's `upgrade`/`downgrade`**

```python
from alembic import op
import sqlalchemy as sa

rewards_table = sa.table(
    "rewards",
    sa.column("level", sa.Integer),
    sa.column("reward_type", sa.String),
    sa.column("reward_value", sa.String),
)

MISSING_BADGE_REWARDS = [
    {"level": 5, "reward_type": "badge", "reward_value": "actif"},
    {"level": 20, "reward_type": "badge", "reward_value": "habitue"},
    {"level": 40, "reward_type": "badge", "reward_value": "veteran"},
    {"level": 100, "reward_type": "badge", "reward_value": "legendaire"},
]


def upgrade() -> None:
    op.bulk_insert(rewards_table, MISSING_BADGE_REWARDS)


def downgrade() -> None:
    conn = op.get_bind()
    for row in MISSING_BADGE_REWARDS:
        conn.execute(
            sa.text(
                "DELETE FROM rewards WHERE level = :level AND reward_type = :reward_type "
                "AND reward_value = :reward_value"
            ),
            row,
        )
```

- [ ] **Step 3: Apply the migration**

Run: `cd colombina && alembic upgrade head`
Expected: command exits 0.

- [ ] **Step 4: Update the failing test**

In `colombina/tests/test_seed_data.py`, change the reward count assertion and add a coverage check:
```python
    assert len(badges) == 14
    assert len(rewards) == 20
    assert len(quests) == 3
    assert any(r.level == 100 and r.reward_type == "badge" and r.reward_value == "diamant" for r in rewards)
    level_badges = {"debutant", "actif", "habitue", "veteran", "legendaire", "argent", "or", "platine", "diamant"}
    granted_badge_values = {r.reward_value for r in rewards if r.reward_type == "badge"}
    assert level_badges <= granted_badge_values
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && DATABASE_URL=postgresql+asyncpg://colombina:colombina@localhost:5432/colombina pytest tests/test_seed_data.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "fix(colombina): seed the 4 level badge reward rows missing from tranche A"
```

---

### Task 4: Leveling formula

**Files:**
- Create: `colombina/services/leveling.py`
- Test: `colombina/tests/test_service_leveling.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `services.leveling.xp_for_level(level: int) -> int`, `services.leveling.level_for_xp(xp: int) -> int`. Task 11 (`add_xp`) and the reaction-removal clamp (Task 16) both call these.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_leveling.py`:
```python
from services.leveling import level_for_xp, xp_for_level


def test_xp_for_level_matches_formula():
    assert xp_for_level(0) == 0
    assert xp_for_level(1) == 100
    assert xp_for_level(5) == 2500
    assert xp_for_level(10) == 10000


def test_level_for_xp_matches_formula():
    assert level_for_xp(0) == 0
    assert level_for_xp(99) == 0
    assert level_for_xp(100) == 1
    assert level_for_xp(2499) == 4
    assert level_for_xp(2500) == 5
    assert level_for_xp(9999) == 9
    assert level_for_xp(10000) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_leveling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.leveling'`

- [ ] **Step 3: Write `services/leveling.py`**

```python
import math


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level` (formula: 100 * level^2)."""
    return 100 * level * level


def level_for_xp(xp: int) -> int:
    """Current level for a total XP amount (formula: floor(sqrt(xp / 100)))."""
    return math.isqrt(xp // 100)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_leveling.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): leveling formula (services/leveling.py)"
```

---

### Task 5: XP gain calculators

**Files:**
- Create: `colombina/services/xp.py`
- Test: `colombina/tests/test_service_xp.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `services.xp.MESSAGE_XP_RANGE: tuple[int, int]`, `services.xp.VOICE_XP_PER_INTERVAL: int`, `services.xp.VOICE_XP_INTERVAL_SECONDS: int`, `services.xp.REACTION_XP: int`, `services.xp.EVENT_PARTICIPATION_XP: int`, `services.xp.INVITE_VALIDATION_XP: int`, `services.xp.roll_message_xp(rng=random) -> int`, `services.xp.voice_xp_for_seconds(seconds: int) -> int`. Task 12 (voice tracker), Task 16/17/18 (cogs) all import these constants and functions.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_xp.py`:
```python
from services.xp import (
    EVENT_PARTICIPATION_XP,
    INVITE_VALIDATION_XP,
    REACTION_XP,
    roll_message_xp,
    voice_xp_for_seconds,
)


class FixedRng:
    def __init__(self, value):
        self.value = value

    def randint(self, low, high):
        return self.value


def test_roll_message_xp_within_range():
    for _ in range(50):
        assert 5 <= roll_message_xp() <= 15


def test_roll_message_xp_uses_injected_rng():
    assert roll_message_xp(rng=FixedRng(9)) == 9


def test_voice_xp_for_seconds_pays_per_ten_minutes():
    assert voice_xp_for_seconds(0) == 0
    assert voice_xp_for_seconds(599) == 0
    assert voice_xp_for_seconds(600) == 10
    assert voice_xp_for_seconds(1199) == 10
    assert voice_xp_for_seconds(1200) == 20


def test_flat_xp_constants():
    assert REACTION_XP == 2
    assert EVENT_PARTICIPATION_XP == 50
    assert INVITE_VALIDATION_XP == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_xp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.xp'`

- [ ] **Step 3: Write `services/xp.py`**

```python
import random

MESSAGE_XP_RANGE = (5, 15)
VOICE_XP_PER_INTERVAL = 10
VOICE_XP_INTERVAL_SECONDS = 600
REACTION_XP = 2
EVENT_PARTICIPATION_XP = 50
INVITE_VALIDATION_XP = 200


def roll_message_xp(rng=random) -> int:
    low, high = MESSAGE_XP_RANGE
    return rng.randint(low, high)


def voice_xp_for_seconds(seconds: int) -> int:
    intervals = seconds // VOICE_XP_INTERVAL_SECONDS
    return intervals * VOICE_XP_PER_INTERVAL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_xp.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): XP gain calculators (services/xp.py)"
```

---

### Task 6: Prestige service

**Files:**
- Create: `colombina/services/prestige.py`
- Test: `colombina/tests/test_service_prestige.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `services.prestige.PRESTIGE_LEVEL_THRESHOLDS: dict[int, int]`, `services.prestige.prestige_for_level(level: int) -> int`, `services.prestige.multiplier_for_prestige(prestige: int) -> float`. Task 11 (`add_xp`) uses both functions.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_prestige.py`:
```python
from services.prestige import multiplier_for_prestige, prestige_for_level


def test_prestige_for_level_thresholds():
    assert prestige_for_level(0) == 0
    assert prestige_for_level(99) == 0
    assert prestige_for_level(100) == 1
    assert prestige_for_level(199) == 1
    assert prestige_for_level(200) == 2
    assert prestige_for_level(300) == 3
    assert prestige_for_level(499) == 3
    assert prestige_for_level(500) == 4
    assert prestige_for_level(600) == 4


def test_multiplier_for_prestige():
    assert multiplier_for_prestige(0) == 1.0
    assert multiplier_for_prestige(1) == 1.1
    assert multiplier_for_prestige(2) == 1.2
    assert multiplier_for_prestige(3) == 1.3
    assert multiplier_for_prestige(4) == 1.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_prestige.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.prestige'`

- [ ] **Step 3: Write `services/prestige.py`**

```python
PRESTIGE_LEVEL_THRESHOLDS = {100: 1, 200: 2, 300: 3, 500: 4}
PRESTIGE_MULTIPLIERS = {0: 1.0, 1: 1.1, 2: 1.2, 3: 1.3, 4: 1.5}


def prestige_for_level(level: int) -> int:
    reached = 0
    for threshold, tier in PRESTIGE_LEVEL_THRESHOLDS.items():
        if level >= threshold:
            reached = max(reached, tier)
    return reached


def multiplier_for_prestige(prestige: int) -> float:
    return PRESTIGE_MULTIPLIERS.get(prestige, 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_prestige.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): prestige tiers and XP multiplier (services/prestige.py)"
```

---

### Task 7: Key drop mechanic

**Files:**
- Create: `colombina/services/keys.py`
- Test: `colombina/tests/test_service_keys.py`

**Interfaces:**
- Consumes: `database` session (only for `add_key`), `models.keys.UserKey` (Task 2).
- Produces: `services.keys.KEY_RARITY_WEIGHTS: dict[str, float]`, `services.keys.KEY_DROP_CHANCES: dict[int, float]`, `services.keys.roll_key_rarity(rng=random) -> str`, `services.keys.should_drop_key(levels_elapsed: int, rng=random) -> bool`, `services.keys.add_key(session, user_id: int, rarity: str) -> None`. Task 9 (reward granting, for the level-90 item) and Task 11 (`add_xp`, for the passive per-level drop) both use all four.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_keys.py`:
```python
from models.users import User
from services.keys import add_key, roll_key_rarity, should_drop_key


class FixedRng:
    def __init__(self, uniform_value=None, random_value=None):
        self.uniform_value = uniform_value
        self.random_value = random_value

    def uniform(self, low, high):
        return self.uniform_value

    def random(self):
        return self.random_value


def test_roll_key_rarity_boundaries():
    assert roll_key_rarity(rng=FixedRng(uniform_value=10.0)) == "commun"
    assert roll_key_rarity(rng=FixedRng(uniform_value=70.0)) == "rare"
    assert roll_key_rarity(rng=FixedRng(uniform_value=90.0)) == "epique"
    assert roll_key_rarity(rng=FixedRng(uniform_value=96.0)) == "legendaire"
    assert roll_key_rarity(rng=FixedRng(uniform_value=98.6)) == "mythique"
    assert roll_key_rarity(rng=FixedRng(uniform_value=99.9)) == "divin"


def test_should_drop_key_only_fires_on_known_thresholds():
    assert should_drop_key(1, rng=FixedRng(random_value=0.0)) is False
    assert should_drop_key(7, rng=FixedRng(random_value=0.0)) is False


def test_should_drop_key_respects_chance_table():
    assert should_drop_key(5, rng=FixedRng(random_value=0.10)) is True
    assert should_drop_key(5, rng=FixedRng(random_value=0.20)) is False
    assert should_drop_key(25, rng=FixedRng(random_value=0.999)) is True


async def test_add_key_creates_then_increments(db_session):
    user = User(discord_id=6001, username="Keyed")
    db_session.add(user)
    await db_session.flush()

    await add_key(db_session, user.discord_id, "rare")
    await add_key(db_session, user.discord_id, "rare")
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.discord_id, UserKey.rarity == "rare")
    )
    fetched = result.scalar_one()
    assert fetched.count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_keys.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.keys'`

- [ ] **Step 3: Write `services/keys.py`**

```python
import random

from sqlalchemy import select

from models.keys import UserKey

KEY_RARITY_WEIGHTS = {
    "commun": 60.0,
    "rare": 25.0,
    "epique": 10.0,
    "legendaire": 3.5,
    "mythique": 1.0,
    "divin": 0.5,
}

KEY_DROP_CHANCES = {5: 0.15, 10: 0.25, 15: 0.5, 20: 0.75, 25: 1.0}


def roll_key_rarity(rng=random) -> str:
    roll = rng.uniform(0.0, 100.0)
    cumulative = 0.0
    for rarity, weight in KEY_RARITY_WEIGHTS.items():
        cumulative += weight
        if roll < cumulative:
            return rarity
    return "divin"


def should_drop_key(levels_elapsed: int, rng=random) -> bool:
    chance = KEY_DROP_CHANCES.get(levels_elapsed)
    if chance is None:
        return False
    return rng.random() < chance


async def add_key(session, user_id: int, rarity: str) -> None:
    result = await session.execute(
        select(UserKey).where(UserKey.user_id == user_id, UserKey.rarity == rarity)
    )
    key = result.scalar_one_or_none()
    if key is None:
        key = UserKey(user_id=user_id, rarity=rarity, count=0)
        session.add(key)
    key.count += 1
    await session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_keys.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): chest key rarity roll and drop chance (services/keys.py)"
```

---

### Task 8: Economy mutation

**Files:**
- Create: `colombina/services/economy.py`
- Test: `colombina/tests/test_service_economy.py`

**Interfaces:**
- Consumes: `models.economy.Economy` (tranche A).
- Produces: `services.economy.add_balance(session, user_id: int, amount: int) -> int` (returns new balance). Task 9 (reward granting) uses this for `coins`-type rewards.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_economy.py`:
```python
from models.users import User
from services.economy import add_balance


async def test_add_balance_creates_economy_row_if_missing(db_session):
    user = User(discord_id=7001, username="Broke")
    db_session.add(user)
    await db_session.flush()

    new_balance = await add_balance(db_session, user.discord_id, 1000)
    await db_session.commit()

    assert new_balance == 1000


async def test_add_balance_increments_existing_balance(db_session):
    user = User(discord_id=7002, username="Rich")
    db_session.add(user)
    await db_session.flush()

    await add_balance(db_session, user.discord_id, 500)
    new_balance = await add_balance(db_session, user.discord_id, 250)
    await db_session.commit()

    assert new_balance == 750
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_economy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.economy'`

- [ ] **Step 3: Write `services/economy.py`**

```python
from models.economy import Economy


async def add_balance(session, user_id: int, amount: int) -> int:
    economy = await session.get(Economy, user_id)
    if economy is None:
        economy = Economy(user_id=user_id, balance=0)
        session.add(economy)
    economy.balance += amount
    await session.flush()
    return economy.balance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_economy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): economy balance mutation (services/economy.py)"
```

---

### Task 9: Ensure-user helper

**Files:**
- Create: `colombina/services/users.py`
- Test: `colombina/tests/test_service_users.py`

**Interfaces:**
- Consumes: `models.users.User` (tranche A).
- Produces: `services.users.get_or_create_user(session, discord_id: int, username: str) -> models.users.User`. Task 15 (`cogs/xp_common.py`) calls this before every `add_xp`, since `Level.user_id` has a foreign key to `users.discord_id`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_users.py`:
```python
from services.users import get_or_create_user


async def test_get_or_create_user_creates_new_row(db_session):
    user = await get_or_create_user(db_session, 8001, "Newcomer")
    await db_session.commit()

    assert user.discord_id == 8001
    assert user.username == "Newcomer"


async def test_get_or_create_user_returns_existing_row_unchanged(db_session):
    first = await get_or_create_user(db_session, 8002, "Original")
    await db_session.commit()

    second = await get_or_create_user(db_session, 8002, "RenamedElsewhere")
    await db_session.commit()

    assert second.discord_id == first.discord_id
    assert second.username == "Original"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_users.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.users'`

- [ ] **Step 3: Write `services/users.py`**

```python
from models.users import User


async def get_or_create_user(session, discord_id: int, username: str) -> User:
    user = await session.get(User, discord_id)
    if user is None:
        user = User(discord_id=discord_id, username=username)
        session.add(user)
        await session.flush()
    return user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_users.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): get-or-create user helper (services/users.py)"
```

---

### Task 10: Reward granting

**Files:**
- Create: `colombina/services/rewards.py`
- Test: `colombina/tests/test_service_rewards.py`

**Interfaces:**
- Consumes: `models.rewards.Reward`, `models.badges.Badge`, `models.badges.UserBadge` (tranche A), `services.economy.add_balance` (Task 8), `services.keys.roll_key_rarity`/`add_key` (Task 7).
- Produces: `services.rewards.RewardOutcome` (dataclass: `reward_type: str`, `reward_value: str`, `detail: str`), `services.rewards.grant_reward(session, user_id: int, reward: models.rewards.Reward, rng=random) -> RewardOutcome`. Task 11 (`add_xp`) calls this once per `Reward` row matched to a crossed level.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_rewards.py`:
```python
import random

from models.badges import Badge
from models.rewards import Reward
from models.users import User
from services.rewards import grant_reward


class FixedRng(random.Random):
    def uniform(self, low, high):
        return 10.0  # always rolls "commun"


async def test_grant_badge_reward_inserts_user_badge(db_session):
    user = User(discord_id=9001, username="Badged")
    badge = Badge(key="debutant", name="Débutant", description="d", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    reward = Reward(level=1, reward_type="badge", reward_value="debutant")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, user.discord_id, reward)
    await db_session.commit()

    assert outcome.reward_type == "badge"
    assert outcome.reward_value == "debutant"

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == user.discord_id, UserBadge.badge_id == badge.id)
    )
    assert result.scalar_one_or_none() is not None


async def test_grant_badge_reward_is_idempotent(db_session):
    user = User(discord_id=9002, username="BadgedTwice")
    badge = Badge(key="actif", name="Actif", description="d", icon="⭐", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    reward = Reward(level=5, reward_type="badge", reward_value="actif")
    db_session.add(reward)
    await db_session.flush()

    await grant_reward(db_session, user.discord_id, reward)
    await grant_reward(db_session, user.discord_id, reward)
    await db_session.commit()

    from sqlalchemy import select
    from models.badges import UserBadge

    result = await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == user.discord_id, UserBadge.badge_id == badge.id)
    )
    assert len(result.scalars().all()) == 1


async def test_grant_coins_reward_credits_economy(db_session):
    user = User(discord_id=9003, username="Coined")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=10, reward_type="coins", reward_value="1000")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, user.discord_id, reward)
    await db_session.commit()

    from models.economy import Economy

    economy = await db_session.get(Economy, user.discord_id)
    assert economy.balance == 1000
    assert outcome.detail == "1000 coins"


async def test_grant_item_reward_grants_a_key(db_session):
    user = User(discord_id=9004, username="Chested")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=90, reward_type="item", reward_value="coffre_mystere")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, user.discord_id, reward, rng=FixedRng())
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.discord_id, UserKey.rarity == "commun")
    )
    assert result.scalar_one().count == 1
    assert outcome.reward_type == "item"


async def test_grant_role_reward_has_no_db_side_effect(db_session):
    user = User(discord_id=9005, username="RoleWaiting")
    db_session.add(user)
    await db_session.flush()

    reward = Reward(level=5, reward_type="role", reward_value="role_actif")
    db_session.add(reward)
    await db_session.flush()

    outcome = await grant_reward(db_session, user.discord_id, reward)

    assert outcome.reward_type == "role"
    assert outcome.reward_value == "role_actif"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_rewards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.rewards'`

- [ ] **Step 3: Write `services/rewards.py`**

```python
import random
from dataclasses import dataclass

from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.rewards import Reward
from services.economy import add_balance
from services.keys import add_key, roll_key_rarity


@dataclass
class RewardOutcome:
    reward_type: str
    reward_value: str
    detail: str


async def grant_reward(session, user_id: int, reward: Reward, rng=random) -> RewardOutcome:
    if reward.reward_type == "badge":
        await _grant_badge(session, user_id, reward.reward_value)
        detail = reward.reward_value
    elif reward.reward_type == "coins":
        amount = int(reward.reward_value)
        await add_balance(session, user_id, amount)
        detail = f"{amount} coins"
    elif reward.reward_type == "item":
        rarity = roll_key_rarity(rng=rng)
        await add_key(session, user_id, rarity)
        detail = f"clé {rarity}"
    else:
        # role, access, title: no DB-side effect here — the caller (cogs/xp_common.py)
        # resolves reward_value to a Discord role via config, or is announce-only (title).
        detail = reward.reward_value

    return RewardOutcome(reward_type=reward.reward_type, reward_value=reward.reward_value, detail=detail)


async def _grant_badge(session, user_id: int, badge_key: str) -> None:
    badge_result = await session.execute(select(Badge).where(Badge.key == badge_key))
    badge = badge_result.scalar_one()

    existing = await session.execute(
        select(UserBadge).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
    )
    if existing.scalar_one_or_none() is not None:
        return

    session.add(UserBadge(user_id=user_id, badge_id=badge.id))
    await session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_rewards.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): reward granting dispatch (services/rewards.py)"
```

---

### Task 11: `add_xp` orchestration (level-up loop)

**Files:**
- Modify: `colombina/services/leveling.py`
- Test: `colombina/tests/test_service_add_xp.py`

**Interfaces:**
- Consumes: `services.leveling.xp_for_level`/`level_for_xp` (Task 4), `services.prestige.prestige_for_level`/`multiplier_for_prestige` (Task 6), `services.keys.should_drop_key`/`roll_key_rarity`/`add_key` (Task 7), `services.rewards.grant_reward`/`RewardOutcome` (Task 10), `models.levels.Level`, `models.rewards.Reward`, `models.users.User` (Task 2/tranche A).
- Produces: `services.leveling.KeyDrop` (dataclass: `level: int`, `rarity: str`), `services.leveling.LevelUpResult` (dataclass: `user_id: int`, `xp: int`, `level: int`, `levels_gained: list[int]`, `reward_outcomes: list[RewardOutcome]`, `key_drops: list[KeyDrop]`, `prestige_reached: int | None`, `inviter_bonus: "LevelUpResult | None" = None`), `services.leveling.add_xp(session, user_id: int, base_amount: int, rng=random) -> LevelUpResult`, `services.leveling.subtract_xp(session, user_id: int, amount: int) -> int` (returns new xp; clamps at the floor of the user's current stored level, never lowers `level`). Task 15 (`cogs/xp_common.py`) calls `add_xp`; the reaction-remove path in Task 16 calls `subtract_xp` directly.
- **Precondition:** both `add_xp` and `subtract_xp` assume the `User` row for `user_id` already exists (caller must have called `services.users.get_or_create_user` first) — they only get-or-create the `Level` row.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_add_xp.py`:
```python
from models.rewards import Reward
from models.users import User
from services.leveling import add_xp, subtract_xp


async def test_add_xp_creates_level_row_and_awards_xp(db_session):
    user = User(discord_id=10001, username="Fresh")
    db_session.add(user)
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, 50)
    await db_session.commit()

    assert result.xp == 50
    assert result.level == 0
    assert result.levels_gained == []


async def test_add_xp_crosses_multiple_levels_and_grants_each_rewards(db_session):
    user = User(discord_id=10002, username="Jumper")
    db_session.add(user)
    await db_session.flush()

    db_session.add_all(
        [
            Reward(level=1, reward_type="coins", reward_value="10"),
            Reward(level=2, reward_type="coins", reward_value="20"),
        ]
    )
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, 400)  # crosses level 1 and 2
    await db_session.commit()

    assert result.level == 2
    assert result.levels_gained == [1, 2]
    assert [o.detail for o in result.reward_outcomes] == ["10 coins", "20 coins"]


async def test_add_xp_never_lowers_stored_level(db_session):
    from models.levels import Level

    user = User(discord_id=10003, username="Veteran")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(user_id=user.discord_id, xp=10000, level=10, prestige=0))
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, 1)
    await db_session.commit()

    assert result.level == 10
    assert result.levels_gained == []


async def test_add_xp_applies_prestige_multiplier(db_session):
    from models.levels import Level

    user = User(discord_id=10004, username="Prestiged")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(user_id=user.discord_id, xp=0, level=0, prestige=1))
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, 100)
    await db_session.commit()
    assert result.xp == 110  # +10% prestige I multiplier


async def test_add_xp_detects_prestige_reached(db_session):
    from models.levels import Level

    user = User(discord_id=10005, username="AlmostHundred")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(user_id=user.discord_id, xp=999900, level=99, prestige=0))
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, 200)
    await db_session.commit()

    assert result.level == 100
    assert result.prestige_reached == 1


async def test_add_xp_triggers_key_drop_at_five_levels_elapsed(db_session):
    import services.leveling as leveling_module

    class AlwaysDrop:
        def random(self):
            return 0.0

        def uniform(self, low, high):
            return 0.0  # always "commun"

    user = User(discord_id=10006, username="Lucky")
    db_session.add(user)
    await db_session.flush()

    result = await add_xp(db_session, user.discord_id, leveling_module.xp_for_level(5), rng=AlwaysDrop())
    await db_session.commit()

    assert result.key_drops == [leveling_module.KeyDrop(level=5, rarity="commun")]


async def test_subtract_xp_clamps_at_current_level_floor(db_session):
    from models.levels import Level

    user = User(discord_id=10007, username="Clamped")
    db_session.add(user)
    await db_session.flush()
    db_session.add(Level(user_id=user.discord_id, xp=100, level=1, prestige=0))
    await db_session.flush()

    new_xp = await subtract_xp(db_session, user.discord_id, 50)
    await db_session.commit()

    assert new_xp == 100  # can't drop below xp_for_level(1) == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_add_xp.py -v`
Expected: FAIL with `ImportError: cannot import name 'add_xp' from 'services.leveling'`

- [ ] **Step 3: Rewrite `services/leveling.py`**

```python
import math
import random
from dataclasses import dataclass, field

from sqlalchemy import select

from models.levels import Level
from models.rewards import Reward
from services.keys import add_key, roll_key_rarity, should_drop_key
from services.prestige import multiplier_for_prestige, prestige_for_level
from services.rewards import RewardOutcome, grant_reward


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level` (formula: 100 * level^2)."""
    return 100 * level * level


def level_for_xp(xp: int) -> int:
    """Current level for a total XP amount (formula: floor(sqrt(xp / 100)))."""
    return math.isqrt(xp // 100)


@dataclass
class KeyDrop:
    level: int
    rarity: str


@dataclass
class LevelUpResult:
    user_id: int
    xp: int
    level: int
    levels_gained: list[int] = field(default_factory=list)
    reward_outcomes: list[RewardOutcome] = field(default_factory=list)
    key_drops: list[KeyDrop] = field(default_factory=list)
    prestige_reached: int | None = None
    inviter_bonus: "LevelUpResult | None" = None


async def _get_or_create_level(session, user_id: int) -> Level:
    level_row = await session.get(Level, user_id)
    if level_row is None:
        level_row = Level(user_id=user_id, xp=0, level=0, prestige=0, last_key_drop_level=0)
        session.add(level_row)
        await session.flush()
    return level_row


async def add_xp(session, user_id: int, base_amount: int, rng=random) -> LevelUpResult:
    level_row = await _get_or_create_level(session, user_id)

    multiplier = multiplier_for_prestige(level_row.prestige)
    actual_amount = round(base_amount * multiplier)

    old_level = level_row.level
    level_row.xp += actual_amount
    computed_level = level_for_xp(level_row.xp)
    new_level = max(old_level, computed_level)
    levels_gained = list(range(old_level + 1, new_level + 1))

    reward_outcomes: list[RewardOutcome] = []
    key_drops: list[KeyDrop] = []
    inviter_bonus: LevelUpResult | None = None

    for crossed_level in levels_gained:
        reward_result = await session.execute(select(Reward).where(Reward.level == crossed_level))
        for reward in reward_result.scalars().all():
            reward_outcomes.append(await grant_reward(session, user_id, reward, rng=rng))

        levels_elapsed = crossed_level - level_row.last_key_drop_level
        if should_drop_key(levels_elapsed, rng=rng):
            rarity = roll_key_rarity(rng=rng)
            await add_key(session, user_id, rarity)
            level_row.last_key_drop_level = crossed_level
            key_drops.append(KeyDrop(level=crossed_level, rarity=rarity))

        if crossed_level == 5:
            inviter_bonus = await _maybe_reward_inviter(session, user_id, rng=rng)

    new_prestige = prestige_for_level(new_level)
    prestige_reached = new_prestige if new_prestige > level_row.prestige else None
    level_row.prestige = max(level_row.prestige, new_prestige)
    level_row.level = new_level

    await session.flush()

    return LevelUpResult(
        user_id=user_id,
        xp=level_row.xp,
        level=level_row.level,
        levels_gained=levels_gained,
        reward_outcomes=reward_outcomes,
        key_drops=key_drops,
        prestige_reached=prestige_reached,
        inviter_bonus=inviter_bonus,
    )


async def _maybe_reward_inviter(session, invitee_user_id: int, rng=random) -> "LevelUpResult | None":
    from models.users import User
    from services.xp import INVITE_VALIDATION_XP

    invitee = await session.get(User, invitee_user_id)
    if invitee is None or invitee.invited_by_id is None:
        return None
    return await add_xp(session, invitee.invited_by_id, INVITE_VALIDATION_XP, rng=rng)


async def subtract_xp(session, user_id: int, amount: int) -> int:
    level_row = await _get_or_create_level(session, user_id)
    floor_xp = xp_for_level(level_row.level)
    level_row.xp = max(floor_xp, level_row.xp - amount)
    await session.flush()
    return level_row.xp
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_add_xp.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite so far**

Run: `cd colombina && pytest -v -m "not integration" tests/ --ignore=tests/test_seed_data.py --ignore=tests/test_postgres_integration.py`
Expected: all service/model tests from Tasks 1-11 PASS.

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): add_xp level-up orchestration loop"
```

---

### Task 12: Announcement formatting

**Files:**
- Create: `colombina/services/announcements.py`
- Test: `colombina/tests/test_service_announcements.py`

**Interfaces:**
- Consumes: `services.rewards.RewardOutcome` (Task 10).
- Produces: `services.announcements.format_level_up_message(display_name: str, level: int) -> str`, `services.announcements.format_reward_message(display_name: str, outcome: RewardOutcome) -> str`, `services.announcements.format_prestige_message(display_name: str, prestige: int) -> str`. Task 15 (`cogs/xp_common.py`) calls all three.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_announcements.py`:
```python
from services.announcements import (
    format_level_up_message,
    format_prestige_message,
    format_reward_message,
)
from services.rewards import RewardOutcome


def test_format_level_up_message():
    assert format_level_up_message("Ashen", 5) == "🎉 **Ashen** a atteint le niveau **5** !"


def test_format_reward_message_badge():
    outcome = RewardOutcome(reward_type="badge", reward_value="debutant", detail="debutant")
    assert format_reward_message("Ashen", outcome) == "✨ **Ashen** a débloqué le badge : debutant"


def test_format_reward_message_coins():
    outcome = RewardOutcome(reward_type="coins", reward_value="1000", detail="1000 coins")
    assert format_reward_message("Ashen", outcome) == "✨ **Ashen** a reçu : 1000 coins"


def test_format_prestige_message():
    assert format_prestige_message("Ashen", 2) == "🌟 **Ashen** atteint le **Prestige II** !"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_announcements.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.announcements'`

- [ ] **Step 3: Write `services/announcements.py`**

```python
from services.rewards import RewardOutcome

_REWARD_LABELS = {
    "badge": "a débloqué le badge",
    "coins": "a reçu",
    "role": "a débloqué le rôle",
    "access": "a débloqué l'accès",
    "item": "a reçu",
    "title": "a débloqué le titre",
}

_PRESTIGE_NUMERALS = {1: "I", 2: "II", 3: "III", 4: "IV"}


def format_level_up_message(display_name: str, level: int) -> str:
    return f"🎉 **{display_name}** a atteint le niveau **{level}** !"


def format_reward_message(display_name: str, outcome: RewardOutcome) -> str:
    label = _REWARD_LABELS.get(outcome.reward_type, "a reçu")
    return f"✨ **{display_name}** {label} : {outcome.detail}"


def format_prestige_message(display_name: str, prestige: int) -> str:
    numeral = _PRESTIGE_NUMERALS.get(prestige, str(prestige))
    return f"🌟 **{display_name}** atteint le **Prestige {numeral}** !"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_announcements.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): level-up/reward/prestige announcement formatting"
```

---

### Task 13: Voice session tracker

**Files:**
- Create: `colombina/services/voice_tracker.py`
- Test: `colombina/tests/test_service_voice_tracker.py`

**Interfaces:**
- Consumes: `services.xp.VOICE_XP_INTERVAL_SECONDS` (Task 5).
- Produces: `services.voice_tracker.VoiceTracker` with `__init__(self, clock=time.monotonic)` and `update_channel(self, user_id: int, channel_id: int | None, human_count: int) -> int` (returns whole seconds — always a multiple of `VOICE_XP_INTERVAL_SECONDS` — newly payable since the last call for this user; 0 if none). Task 17 (`cogs/voice.py`) holds one `VoiceTracker` instance per bot process and calls `update_channel` on every `on_voice_state_update`, converting the returned seconds via `services.xp.voice_xp_for_seconds`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_voice_tracker.py`:
```python
from services.voice_tracker import VoiceTracker


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def advance(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


def test_no_payout_below_two_humans():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=1)
    clock.advance(700)
    payout = tracker.update_channel(1, channel_id=100, human_count=1)

    assert payout == 0


def test_payout_after_ten_minutes_with_two_humans():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(650)
    payout = tracker.update_channel(1, channel_id=100, human_count=2)

    assert payout == 600


def test_remainder_carries_over_across_channel_move():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(650)
    first_payout = tracker.update_channel(1, channel_id=200, human_count=2)  # moved channel
    clock.advance(550)
    second_payout = tracker.update_channel(1, channel_id=200, human_count=2)

    assert first_payout == 600
    assert second_payout == 600  # 50s leftover + 550s new = 600s


def test_disconnect_drops_unpaid_remainder():
    clock = FakeClock()
    tracker = VoiceTracker(clock=clock)

    tracker.update_channel(1, channel_id=100, human_count=2)
    clock.advance(300)
    payout = tracker.update_channel(1, channel_id=None, human_count=0)
    clock.advance(300)
    tracker.update_channel(1, channel_id=100, human_count=2)
    second_payout = tracker.update_channel(1, channel_id=100, human_count=2)

    assert payout == 0
    assert second_payout == 0  # the 300s before disconnect was dropped, not carried
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_voice_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.voice_tracker'`

- [ ] **Step 3: Write `services/voice_tracker.py`**

```python
import time

from services.xp import VOICE_XP_INTERVAL_SECONDS


class VoiceTracker:
    """Tracks per-user voice presence eligible for XP (channel has >=2 non-bot members)."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._eligible_since: dict[int, float] = {}
        self._accumulated: dict[int, float] = {}

    def update_channel(self, user_id: int, channel_id: int | None, human_count: int) -> int:
        now = self._clock()
        self._flush_eligibility(user_id, now)

        if channel_id is not None and human_count >= 2:
            self._eligible_since[user_id] = now
        else:
            self._eligible_since.pop(user_id, None)

        accumulated = self._accumulated.get(user_id, 0.0)
        payable_seconds = int(accumulated // VOICE_XP_INTERVAL_SECONDS) * VOICE_XP_INTERVAL_SECONDS
        if payable_seconds:
            self._accumulated[user_id] = accumulated - payable_seconds

        if channel_id is None:
            self._accumulated.pop(user_id, None)
            self._eligible_since.pop(user_id, None)

        return payable_seconds

    def _flush_eligibility(self, user_id: int, now: float) -> None:
        since = self._eligible_since.get(user_id)
        if since is None:
            return
        elapsed = now - since
        self._accumulated[user_id] = self._accumulated.get(user_id, 0.0) + elapsed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_voice_tracker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): voice session eligibility tracker (services/voice_tracker.py)"
```

---

### Task 14: Invite diff logic

**Files:**
- Create: `colombina/services/invites.py`
- Test: `colombina/tests/test_service_invites.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `services.invites.diff_invite_uses(before: dict[str, int], after: dict[str, int]) -> str | None`. Task 18 (`cogs/invites.py`) calls this on every `on_member_join`, comparing its cached snapshot against a fresh `guild.invites()` read.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_service_invites.py`:
```python
from services.invites import diff_invite_uses


def test_diff_invite_uses_finds_incremented_code():
    before = {"abc123": 5, "xyz789": 0}
    after = {"abc123": 6, "xyz789": 0}

    assert diff_invite_uses(before, after) == "abc123"


def test_diff_invite_uses_handles_new_code_not_in_before():
    before = {"abc123": 5}
    after = {"abc123": 5, "newcode": 1}

    assert diff_invite_uses(before, after) == "newcode"


def test_diff_invite_uses_returns_none_when_nothing_changed():
    before = {"abc123": 5}
    after = {"abc123": 5}

    assert diff_invite_uses(before, after) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_service_invites.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.invites'`

- [ ] **Step 3: Write `services/invites.py`**

```python
def diff_invite_uses(before: dict[str, int], after: dict[str, int]) -> str | None:
    """Return the invite code whose use count increased between two snapshots,
    or None if it can't be determined (e.g. vanity URL join, or no change found)."""
    for code, uses_after in after.items():
        if uses_after > before.get(code, 0):
            return code
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_service_invites.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): invite-use diff logic (services/invites.py)"
```

---

### Task 15: Shared Discord XP dispatch adapter

**Files:**
- Create: `colombina/cogs/xp_common.py`
- Test: `colombina/tests/test_cogs_xp_common.py`

**Interfaces:**
- Consumes: `services.users.get_or_create_user` (Task 9), `services.leveling.add_xp`/`LevelUpResult` (Task 11), `services.announcements.*` (Task 12), `config.settings.settings` (Task 1).
- Produces: `cogs.xp_common.award_xp(session, guild, channel_resolver, member, base_amount, rng=random) -> LevelUpResult`. Tasks 16/17/18 (`cogs/leveling.py`, `cogs/voice.py`, `cogs/invites.py`) all call this instead of `add_xp` directly, so announcements and role grants happen consistently regardless of XP source. `channel_resolver` is a zero-arg callable returning the announcement channel object (or `None`); it exists so tests can supply a fake without needing a real `discord.Guild`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_xp_common.py`:
```python
from models.rewards import Reward
from models.users import User
from cogs.xp_common import award_xp


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeRole:
    def __init__(self, id):
        self.id = id


class FakeMember:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name
        self.added_roles = []

    async def add_roles(self, role):
        self.added_roles.append(role)


class FakeGuild:
    def __init__(self, roles_by_id):
        self._roles_by_id = roles_by_id

    def get_role(self, role_id):
        return self._roles_by_id.get(role_id)


async def test_award_xp_persists_user_and_sends_no_announcement_below_level_up(db_session):
    channel = FakeChannel()
    guild = FakeGuild(roles_by_id={})
    member = FakeMember(id=11001, display_name="Newcomer")

    result = await award_xp(db_session, guild, lambda: channel, member, 50)

    assert result.xp == 50
    fetched = await db_session.get(User, 11001)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_xp_common.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.xp_common'`

- [ ] **Step 3: Write `cogs/xp_common.py`**

```python
import random

from config.settings import settings
from services.announcements import (
    format_level_up_message,
    format_prestige_message,
    format_reward_message,
)
from services.leveling import LevelUpResult, add_xp
from services.users import get_or_create_user

REWARD_ROLE_SETTINGS = {
    "role_actif": "role_actif_id",
    "role_habitue": "role_habitue_id",
    "role_veteran": "role_veteran_id",
    "role_legendaire": "role_legendaire_id",
    "vip_bronze": "role_vip_bronze_id",
    "vip_argent": "role_vip_argent_id",
    "premium": "role_premium_id",
}

PRESTIGE_ROLE_SETTINGS = {
    1: "prestige_1_role_id",
    2: "prestige_2_role_id",
    3: "prestige_3_role_id",
    4: "prestige_4_role_id",
}


async def award_xp(session, guild, channel_resolver, member, base_amount: int, rng=random) -> LevelUpResult:
    await get_or_create_user(session, member.id, member.display_name)
    result = await add_xp(session, member.id, base_amount, rng=rng)
    await session.commit()

    channel = channel_resolver()

    for level in result.levels_gained:
        if channel is not None:
            await channel.send(format_level_up_message(member.display_name, level))

    for outcome in result.reward_outcomes:
        if channel is not None:
            await channel.send(format_reward_message(member.display_name, outcome))
        await _maybe_assign_role(guild, member, REWARD_ROLE_SETTINGS.get(outcome.reward_value))

    if result.prestige_reached is not None:
        await _maybe_assign_role(guild, member, PRESTIGE_ROLE_SETTINGS.get(result.prestige_reached))
        if channel is not None:
            await channel.send(format_prestige_message(member.display_name, result.prestige_reached))

    return result


async def _maybe_assign_role(guild, member, role_id_setting_name: str | None) -> None:
    if role_id_setting_name is None:
        return
    role_id = getattr(settings, role_id_setting_name, None)
    if not role_id:
        return
    role = guild.get_role(int(role_id))
    if role is not None:
        await member.add_roles(role)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_xp_common.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): shared XP dispatch adapter (cogs/xp_common.py)"
```

---

### Task 16: `cogs/leveling.py` — message XP, reaction XP, event-participation command

**Files:**
- Create: `colombina/cogs/leveling.py`
- Test: `colombina/tests/test_cogs_leveling.py`

**Interfaces:**
- Consumes: `cogs.xp_common.award_xp` (Task 15), `services.leveling.subtract_xp` (Task 11), `services.xp.roll_message_xp`/`REACTION_XP`/`EVENT_PARTICIPATION_XP` (Task 5), `database.engine.AsyncSessionLocal` (tranche A).
- Produces: `cogs.leveling.LevelingCog(commands.Cog)` with listeners `on_message`, `on_reaction_add`, `on_reaction_remove`, and a slash command `event-participation` (admin-only); module-level `async def setup(bot)`. Loaded automatically by `utils.cog_loader.load_all_extensions` (tranche A) once this file exists under `cogs/`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_leveling.py`:
```python
from cogs.leveling import LevelingCog


class FakeAuthor:
    def __init__(self, id, display_name, bot=False):
        self.id = id
        self.display_name = display_name
        self.bot = bot


class FakeMessage:
    def __init__(self, author, guild):
        self.author = author
        self.guild = guild


class FakeGuild:
    def get_role(self, role_id):
        return None


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content):
        self.sent.append(content)


class FakeBot:
    def __init__(self, session_factory):
        self.session_factory = session_factory


async def test_on_message_awards_xp_to_human_author(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12001, display_name="Chatter")
    message = FakeMessage(author=author, guild=FakeGuild())

    await cog.on_message(message)

    from models.levels import Level

    level_row = await db_session.get(Level, 12001)
    assert level_row is not None
    assert 5 <= level_row.xp <= 15


async def test_on_message_ignores_bots(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = LevelingCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)

    author = FakeAuthor(id=12002, display_name="RobotFriend", bot=True)
    message = FakeMessage(author=author, guild=FakeGuild())

    await cog.on_message(message)

    from models.levels import Level

    level_row = await db_session.get(Level, 12002)
    assert level_row is None


class _FakeSessionContext:
    """Minimal async context manager so cog code can do `async with self._session() as session`."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_leveling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.leveling'`

- [ ] **Step 3: Write `cogs/leveling.py`**

```python
import discord
from discord import app_commands
from discord.ext import commands

from cogs.xp_common import award_xp
from config.settings import settings
from services.leveling import subtract_xp
from services.xp import EVENT_PARTICIPATION_XP, roll_message_xp


class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        if message.author.bot:
            return

        amount = roll_message_xp()
        async with self._session() as session:
            await award_xp(
                session,
                message.guild,
                lambda: self._announcement_channel(message.guild),
                message.author,
                amount,
            )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user) -> None:
        message = reaction.message
        if user.bot or user.id == message.author.id or message.author.bot:
            return

        async with self._session() as session:
            await award_xp(
                session,
                message.guild,
                lambda: self._announcement_channel(message.guild),
                message.author,
                2,
            )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user) -> None:
        message = reaction.message
        if user.bot or user.id == message.author.id or message.author.bot:
            return

        async with self._session() as session:
            await subtract_xp(session, message.author.id, 2)
            await session.commit()

    @app_commands.command(name="event-participation", description="Accorde le bonus XP d'événement à un membre")
    @app_commands.checks.has_permissions(administrator=True)
    async def event_participation(self, interaction: discord.Interaction, member: discord.Member) -> None:
        async with self._session() as session:
            await award_xp(
                session,
                interaction.guild,
                lambda: self._announcement_channel(interaction.guild),
                member,
                EVENT_PARTICIPATION_XP,
            )
        await interaction.response.send_message(
            f"{member.display_name} a reçu le bonus de participation à l'événement (+{EVENT_PARTICIPATION_XP} XP).",
            ephemeral=True,
        )


async def setup(bot) -> None:
    await bot.add_cog(LevelingCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_leveling.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): leveling cog (message/reaction XP, event-participation command)"
```

---

### Task 17: `cogs/voice.py` — voice XP wiring

**Files:**
- Create: `colombina/cogs/voice.py`
- Test: `colombina/tests/test_cogs_voice.py`

**Interfaces:**
- Consumes: `services.voice_tracker.VoiceTracker` (Task 13), `services.xp.voice_xp_for_seconds` (Task 5), `cogs.xp_common.award_xp` (Task 15).
- Produces: `cogs.voice.VoiceCog(commands.Cog)` with listener `on_voice_state_update`; module-level `async def setup(bot)`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_voice.py`:
```python
from cogs.voice import VoiceCog


class FakeMember:
    def __init__(self, id, display_name, bot=False):
        self.id = id
        self.display_name = display_name
        self.bot = bot


class FakeChannelMembers:
    def __init__(self, members):
        self.members = members


class FakeVoiceState:
    def __init__(self, channel):
        self.channel = channel


class FakeGuild:
    def get_role(self, role_id):
        return None


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


async def test_on_voice_state_update_awards_xp_after_ten_minutes(db_session, monkeypatch):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = VoiceCog(bot=FakeBot(session_factory))
    monkeypatch.setattr(cog, "_announcement_channel", lambda guild: None)
    cog.tracker._clock = lambda: cog._fake_now

    cog._fake_now = 0.0
    member = FakeMember(id=13001, display_name="Talker")
    other = FakeMember(id=13002, display_name="Listener")
    channel = FakeChannelMembers(members=[member, other])

    await cog.on_voice_state_update(member, FakeVoiceState(None), FakeVoiceState(channel))

    cog._fake_now = 650.0
    await cog.on_voice_state_update(member, FakeVoiceState(channel), FakeVoiceState(None))

    from models.levels import Level

    level_row = await db_session.get(Level, 13001)
    assert level_row is not None
    assert level_row.xp == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_voice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.voice'`

- [ ] **Step 3: Write `cogs/voice.py`**

```python
from discord.ext import commands

from cogs.xp_common import award_xp
from config.settings import settings
from services.voice_tracker import VoiceTracker
from services.xp import voice_xp_for_seconds


class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker = VoiceTracker()

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if member.bot:
            return

        channel = after.channel
        channel_id = channel.id if channel is not None else None
        human_count = 0
        if channel is not None:
            human_count = sum(1 for m in channel.members if not m.bot)

        payable_seconds = self.tracker.update_channel(member.id, channel_id, human_count)
        if payable_seconds <= 0:
            return

        amount = voice_xp_for_seconds(payable_seconds)
        guild = getattr(member, "guild", None)
        async with self._session() as session:
            await award_xp(session, guild, lambda: self._announcement_channel(guild), member, amount)


async def setup(bot) -> None:
    await bot.add_cog(VoiceCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_voice.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): voice cog wiring voice XP to VoiceTracker"
```

---

### Task 18: `cogs/invites.py` — invite tracking wiring

**Files:**
- Create: `colombina/cogs/invites.py`
- Test: `colombina/tests/test_cogs_invites.py`

**Interfaces:**
- Consumes: `services.invites.diff_invite_uses` (Task 14), `services.users.get_or_create_user` (Task 9).
- Produces: `cogs.invites.InvitesCog(commands.Cog)` with listeners `on_ready` (cache init per guild), `on_invite_create` (adds the new code to the cache with 0 uses), `on_member_join` (diffs cache vs fresh `guild.invites()`, sets `invited_by_id` on the joining member's `User` row, refreshes the cache); module-level `async def setup(bot)`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_cogs_invites.py`:
```python
from cogs.invites import InvitesCog


class FakeInvite:
    def __init__(self, code, uses, inviter_id):
        self.code = code
        self.uses = uses
        self.inviter = FakeInviter(inviter_id)


class FakeInviter:
    def __init__(self, id):
        self.id = id


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

    inviter = User(discord_id=14001, username="Inviter")
    db_session.add(inviter)
    await db_session.flush()
    await db_session.commit()

    guild = FakeGuild(id=1, invites=[FakeInvite("abc123", uses=0, inviter_id=14001)])
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = InvitesCog(bot=FakeBot(session_factory, guilds=[guild]))

    await cog.on_ready()  # snapshots {"abc123": 0}

    guild._invites = [FakeInvite("abc123", uses=1, inviter_id=14001)]  # someone just used it
    joining_member = FakeMember(id=14002, display_name="Invitee", guild=guild)
    await cog.on_member_join(joining_member)

    fetched = await db_session.get(User, 14002)
    assert fetched.invited_by_id == 14001


async def test_on_member_join_does_nothing_when_no_invite_use_increased(db_session):
    from models.users import User

    inviter = User(discord_id=14003, username="Inviter2")
    db_session.add(inviter)
    await db_session.flush()
    await db_session.commit()

    guild = FakeGuild(id=2, invites=[FakeInvite("stable", uses=5, inviter_id=14003)])
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = InvitesCog(bot=FakeBot(session_factory, guilds=[guild]))

    await cog.on_ready()
    joining_member = FakeMember(id=14004, display_name="VanityJoiner", guild=guild)
    await cog.on_member_join(joining_member)  # e.g. vanity URL join, uses count unchanged

    fetched = await db_session.get(User, 14004)
    assert fetched.invited_by_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cogs_invites.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cogs.invites'`

- [ ] **Step 3: Write `cogs/invites.py`**

```python
from discord.ext import commands

from services.invites import diff_invite_uses
from services.users import get_or_create_user


class InvitesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._uses_by_guild: dict[int, dict[str, int]] = {}
        self._inviter_by_code: dict[int, dict[str, int]] = {}

    def _session(self):
        return self.bot.session_factory()

    async def _snapshot_guild(self, guild) -> None:
        invites = await guild.invites()
        self._uses_by_guild[guild.id] = {invite.code: invite.uses for invite in invites}
        self._inviter_by_code[guild.id] = {invite.code: invite.inviter.id for invite in invites}

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._snapshot_guild(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite) -> None:
        self._uses_by_guild.setdefault(invite.guild.id, {})[invite.code] = 0
        self._inviter_by_code.setdefault(invite.guild.id, {})[invite.code] = invite.inviter.id

    @commands.Cog.listener()
    async def on_member_join(self, member) -> None:
        guild = member.guild
        before = self._uses_by_guild.get(guild.id, {})
        invites = await guild.invites()
        after = {invite.code: invite.uses for invite in invites}
        inviter_by_code = {invite.code: invite.inviter.id for invite in invites}

        used_code = diff_invite_uses(before, after)

        async with self._session() as session:
            new_user = await get_or_create_user(session, member.id, member.display_name)
            if used_code is not None:
                new_user.invited_by_id = inviter_by_code.get(used_code)
            await session.commit()

        self._uses_by_guild[guild.id] = after
        self._inviter_by_code[guild.id] = inviter_by_code


async def setup(bot) -> None:
    await bot.add_cog(InvitesCog(bot))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cogs_invites.py -v`
Expected: PASS

- [ ] **Step 5: Run the full non-integration test suite**

Run: `cd colombina && pytest -v --ignore=tests/test_seed_data.py --ignore=tests/test_postgres_integration.py`
Expected: all tests from Tasks 1-18 PASS.

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): invites cog wiring invited_by_id tracking"
```

---

## Plan Self-Review Notes

- **Spec coverage:** message/voice/reaction/event/invite XP → Tasks 5, 13, 16, 17, 18; level formula → Task 4; level-up loop + reward granting per palier → Tasks 10, 11; badges (level-based subset) → Task 10 (`_grant_badge`) fed by Task 3's seed fix; prestige detection + multiplier + role → Tasks 6, 15; key-drop mechanic → Task 7, wired in Task 11; announcements → Task 12, dispatched in Task 15; `/event-participation` admin command → Task 16; config additions → Task 1; schema additions → Task 2. Out-of-scope items (classement badges, coffre opening/loot table, cosmetic prestige, `/balance /pay /daily /shop`, anti-abuse hardening beyond the reaction net-zero mechanic, generic admin commands) are correctly not implemented, per the spec's own "Hors périmètre" section.
- **Session amendments applied:** reaction add/remove symmetric XP (Task 16, `subtract_xp` in Task 11) with the level-floor clamp; level-90 item reward grants a key instead of coins (Task 10's `grant_reward` item branch); invite tracking stays simple in-memory (Task 18, unchanged from spec).
- **Data-gap fix:** Task 3 adds the 4 missing badge reward rows found during this session's spec review (actif/habitue/veteran/legendaire) — without it, Task 10's badge-granting path would never fire for those four despite the spec listing them as in-scope.
- **Type/interface consistency check:** `add_xp`/`subtract_xp` signatures match between Task 11's implementation and Tasks 15/16 call sites; `LevelUpResult`/`RewardOutcome`/`KeyDrop` field names match across Tasks 10-12, 15; `VoiceTracker.update_channel` return type (seconds, not XP) matches how Task 17 converts it via `voice_xp_for_seconds`; `award_xp`'s `channel_resolver` parameter is consistently a zero-arg callable across Tasks 15-18.
- **Known simplifications, called out rather than hidden:** `subtract_xp` reverses the flat `REACTION_XP` amount, not the prestige-multiplied amount actually granted by the matching `add_xp` call — acceptable since the multiplier rarely changes between a reaction's add and remove, and getting this wrong only affects a few XP at the margin, never levels or rewards (add/remove of rewards is not symmetric — removing a reaction never revokes an already-granted reward). `add_xp`'s recursive inviter-bonus call has no cycle guard; this is safe because `invited_by_id` chains cannot cycle back to a level-5 crossing without that account regaining a level it already passed, which "level never decreases" forbids — so recursion depth is bounded by the length of a real invite chain, not by malicious input.
