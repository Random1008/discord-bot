# Colombina — Fondations (Tranche A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Colombina Discord bot skeleton — configuration, async Postgres/SQLAlchemy models for all 10 tables, Alembic migrations with seed data, Redis connectivity, logging, cog loading, and Docker packaging — with no feature logic yet.

**Architecture:** A `commands.Bot` (prefix + slash commands) backed by an async SQLAlchemy engine (`asyncpg`) and a Redis client. Models are split by domain into small files under `models/`, all registered on one `Base` so Alembic can autogenerate migrations. Everything runs via `docker compose` (bot + postgres + redis); the entrypoint runs `alembic upgrade head` before starting the bot.

**Tech Stack:** Python 3.12+, discord.py 2.x, SQLAlchemy 2.0 (async, asyncpg), Alembic, pydantic-settings, redis.asyncio, pytest + pytest-asyncio (+ aiosqlite for fast model tests, fakeredis for Redis tests), Docker/docker-compose.

## Global Constraints

- Project root is `colombina/` at the repo root (sibling to other bot projects), independent codebase.
- Single-guild only — no `guild_id` column anywhere in this tranche.
- Bot must support both slash commands (`app_commands`) and prefix text commands later — use `commands.Bot`, never `discord.Client`, with a configurable prefix.
- Database access is async end-to-end (SQLAlchemy 2.0 async + `asyncpg`) — no blocking DB calls.
- No dashboard/FastAPI code in this tranche.
- Directory layout is fixed per the design doc (`colombina/docs/superpowers/specs/2026-07-20-fondations-design.md`): `main.py`, `config/`, `database/`, `models/`, `services/`, `cogs/`, `utils/`, `assets/`, `alembic/`, `tests/`. No separate `commands/` folder.
- No placeholders/TODOs in code — every table, model, and seed row listed in the design doc must exist for real by the end of this plan.

---

### Task 1: Project scaffolding & configuration settings

**Files:**
- Create: `colombina/requirements.txt`
- Create: `colombina/requirements-dev.txt`
- Create: `colombina/.gitignore`
- Create: `colombina/.env.example`
- Create: `colombina/pytest.ini`
- Create: `colombina/config/__init__.py`
- Create: `colombina/config/settings.py`
- Create: `colombina/database/__init__.py`
- Create: `colombina/models/__init__.py`
- Create: `colombina/services/__init__.py`
- Create: `colombina/cogs/__init__.py`
- Create: `colombina/utils/__init__.py`
- Create: `colombina/tests/__init__.py`
- Create: `colombina/tests/conftest.py`
- Test: `colombina/tests/test_settings.py`

**Interfaces:**
- Produces: `config.settings.Settings` (pydantic-settings class) and a module-level `config.settings.settings` instance with fields `discord_token: str`, `database_url: str`, `redis_url: str`, `command_prefix: str = "!"`, `sql_echo: bool = False`, `log_level: str = "INFO"`. Every later task imports `from config.settings import settings`.

- [ ] **Step 1: Create the directory skeleton and empty `__init__.py` files**

Run:
```bash
mkdir -p colombina/{config,database,models,services,cogs,utils,assets,alembic,tests}
touch colombina/config/__init__.py colombina/database/__init__.py \
      colombina/models/__init__.py colombina/services/__init__.py \
      colombina/cogs/__init__.py colombina/utils/__init__.py \
      colombina/tests/__init__.py
```
Expected: the directories and empty `__init__.py` files exist.

- [ ] **Step 2: Write `requirements.txt` and `requirements-dev.txt`**

`colombina/requirements.txt`:
```
discord.py>=2.4,<3.0
SQLAlchemy>=2.0,<2.1
asyncpg>=0.29,<0.30
alembic>=1.13,<1.14
pydantic-settings>=2.2,<3.0
redis>=5.0,<6.0
```

`colombina/requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
aiosqlite>=0.20
fakeredis>=2.21
```

- [ ] **Step 3: Write `.gitignore` and `.env.example`**

`colombina/.gitignore`:
```
__pycache__/
*.pyc
.venv/
.env
*.log
```

`colombina/.env.example`:
```
DISCORD_TOKEN=your-bot-token-here
DATABASE_URL=postgresql+asyncpg://colombina:colombina@localhost:5432/colombina
REDIS_URL=redis://localhost:6379/0
COMMAND_PREFIX=!
SQL_ECHO=false
LOG_LEVEL=INFO

# Reward role IDs (filled in once the roles exist on the Discord server, used from tranche B onward)
ROLE_ACTIF_ID=
ROLE_HABITUE_ID=
ROLE_VETERAN_ID=
ROLE_LEGENDAIRE_ID=
```

- [ ] **Step 4: Write `pytest.ini`**

`colombina/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Write `config/settings.py`**

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


settings = Settings()
```

- [ ] **Step 6: Write `tests/conftest.py` with the env-var bootstrap**

This must run before any test module imports `config.settings` (directly or transitively), so later tasks that import settings-dependent modules don't crash during collection.

```python
import os

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
```

- [ ] **Step 7: Write the failing test**

`colombina/tests/test_settings.py`:
```python
from config.settings import Settings


def test_settings_loads_required_fields_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc123")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/colombina")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings()

    assert settings.discord_token == "abc123"
    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/colombina"
    assert settings.redis_url == "redis://localhost:6379/0"


def test_settings_defaults():
    settings = Settings()

    assert settings.command_prefix == "!"
    assert settings.log_level == "INFO"
    assert settings.sql_echo is False
```

- [ ] **Step 8: Install dependencies and run the test**

Run:
```bash
cd colombina && pip install -r requirements-dev.txt && pytest tests/test_settings.py -v
```
Expected: both tests PASS.

- [ ] **Step 9: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): project scaffolding and config settings"
```

---

### Task 2: Database engine & declarative base

**Files:**
- Create: `colombina/database/base.py`
- Create: `colombina/database/engine.py`
- Test: `colombina/tests/test_engine.py`

**Interfaces:**
- Consumes: `config.settings.settings` (Task 1).
- Produces: `database.base.Base` (SQLAlchemy `DeclarativeBase`), `database.engine.create_engine_and_session(database_url: str, echo: bool = False) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]`, and module-level `database.engine.engine` / `database.engine.AsyncSessionLocal` built from `settings`. All model files (Tasks 3-6) import `Base` from here; `main.py` (Task 11) imports `AsyncSessionLocal`.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_engine.py`:
```python
from sqlalchemy import text

from database.engine import create_engine_and_session


async def test_create_engine_and_session_executes_query():
    engine, session_factory = create_engine_and_session("sqlite+aiosqlite:///:memory:")

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    await engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'database.engine'`

- [ ] **Step 3: Write `database/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Write `database/engine.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings


def create_engine_and_session(
    database_url: str, echo: bool = False
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, echo=echo)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, session_factory


engine, AsyncSessionLocal = create_engine_and_session(settings.database_url, echo=settings.sql_echo)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): async SQLAlchemy engine and declarative base"
```

---

### Task 3: Core identity & progression models (users, levels, prestiges)

**Files:**
- Create: `colombina/models/users.py`
- Create: `colombina/models/levels.py`
- Create: `colombina/models/prestiges.py`
- Modify: `colombina/models/__init__.py`
- Modify: `colombina/tests/conftest.py`
- Test: `colombina/tests/test_models_core.py`

**Interfaces:**
- Consumes: `database.base.Base` (Task 2).
- Produces: `models.users.User` (PK `discord_id: int`), `models.levels.Level` (PK `user_id: int`, FK to `User.discord_id`), `models.prestiges.Prestige` (PK `id: int`, FK `user_id` to `User.discord_id`). Later tasks' foreign keys reference `"users.discord_id"`.

- [ ] **Step 1: Add the shared `db_session` fixture to `tests/conftest.py`**

Append to `colombina/tests/conftest.py`:
```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.base import Base
from database.engine import create_engine_and_session


@pytest_asyncio.fixture
async def db_session():
    engine, _ = create_engine_and_session("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
```

- [ ] **Step 2: Write the failing test**

`colombina/tests/test_models_core.py`:
```python
from models.levels import Level
from models.prestiges import Prestige
from models.users import User


async def test_user_level_and_prestige_roundtrip(db_session):
    user = User(discord_id=1001, username="Ashen")
    db_session.add(user)
    await db_session.flush()

    level = Level(user_id=user.discord_id, xp=250, level=3, prestige=0, message_count=10, voice_seconds=120)
    db_session.add(level)

    prestige = Prestige(user_id=user.discord_id, prestige_level=1)
    db_session.add(prestige)
    await db_session.commit()

    fetched_level = await db_session.get(Level, user.discord_id)
    assert fetched_level.xp == 250
    assert fetched_level.level == 3
    assert fetched_level.message_count == 10

    assert prestige.id is not None
    assert prestige.user_id == user.discord_id
    assert prestige.prestige_level == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_models_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.users'`

- [ ] **Step 4: Write `models/users.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class User(Base):
    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 5: Write `models/levels.py`**

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
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_voice_reward_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 6: Write `models/prestiges.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Prestige(Base):
    __tablename__ = "prestiges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), nullable=False)
    prestige_level: Mapped[int] = mapped_column(Integer, nullable=False)
    achieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 7: Write `models/__init__.py`**

```python
from models.levels import Level
from models.prestiges import Prestige
from models.users import User

__all__ = ["User", "Level", "Prestige"]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_models_core.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): users, levels and prestiges models"
```

---

### Task 4: Badges models (badges, user_badges)

**Files:**
- Create: `colombina/models/badges.py`
- Modify: `colombina/models/__init__.py`
- Test: `colombina/tests/test_models_badges.py`

**Interfaces:**
- Consumes: `database.base.Base`, `models.users.User` (Task 3).
- Produces: `models.badges.Badge` (PK `id`, unique `key`), `models.badges.UserBadge` (composite PK `user_id`+`badge_id`).

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_models_badges.py`:
```python
from models.badges import Badge, UserBadge
from models.users import User


async def test_badge_and_user_badge_roundtrip(db_session):
    user = User(discord_id=2002, username="Wren")
    badge = Badge(key="debutant", name="Débutant", description="Niveau 1 atteint", icon="🔰", rarity="commun")
    db_session.add_all([user, badge])
    await db_session.flush()

    user_badge = UserBadge(user_id=user.discord_id, badge_id=badge.id)
    db_session.add(user_badge)
    await db_session.commit()

    fetched = await db_session.get(UserBadge, {"user_id": user.discord_id, "badge_id": badge.id})
    assert fetched is not None
    assert fetched.earned_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_models_badges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.badges'`

- [ ] **Step 3: Write `models/badges.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(255), nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (UniqueConstraint("key", name="uq_badges_key"),)


class UserBadge(Base):
    __tablename__ = "user_badges"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), primary_key=True)
    badge_id: Mapped[int] = mapped_column(Integer, ForeignKey("badges.id"), primary_key=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Update `models/__init__.py`**

```python
from models.badges import Badge, UserBadge
from models.levels import Level
from models.prestiges import Prestige
from models.users import User

__all__ = ["User", "Level", "Prestige", "Badge", "UserBadge"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_models_badges.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): badges and user_badges models"
```

---

### Task 5: Economy & activity-stats models (economy, voice_stats, message_stats)

**Files:**
- Create: `colombina/models/economy.py`
- Create: `colombina/models/stats.py`
- Modify: `colombina/models/__init__.py`
- Test: `colombina/tests/test_models_economy_stats.py`

**Interfaces:**
- Consumes: `database.base.Base`, `models.users.User` (Task 3).
- Produces: `models.economy.Economy` (PK `user_id`), `models.stats.VoiceStat` and `models.stats.MessageStat` (PK `id`, unique on `user_id`+`date`). `models.stats.ServerStat` is also defined here (PK `date`) since it lives in the same `stats.py` file per the design doc's `voice_stats`/`message_stats`/`server_stats` grouping.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_models_economy_stats.py`:
```python
from datetime import date

from models.economy import Economy
from models.stats import MessageStat, ServerStat, VoiceStat
from models.users import User


async def test_economy_and_daily_stats_roundtrip(db_session):
    user = User(discord_id=3003, username="Talys")
    db_session.add(user)
    await db_session.flush()

    economy = Economy(user_id=user.discord_id, balance=500)
    voice = VoiceStat(user_id=user.discord_id, date=date(2026, 7, 20), seconds=600)
    messages = MessageStat(user_id=user.discord_id, date=date(2026, 7, 20), count=12)
    server = ServerStat(date=date(2026, 7, 20), total_members=100, active_members=40, messages_count=300, voice_minutes=50, new_members=2)
    db_session.add_all([economy, voice, messages, server])
    await db_session.commit()

    fetched_economy = await db_session.get(Economy, user.discord_id)
    assert fetched_economy.balance == 500

    fetched_server = await db_session.get(ServerStat, date(2026, 7, 20))
    assert fetched_server.total_members == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_models_economy_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.economy'`

- [ ] **Step 3: Write `models/economy.py`**

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Economy(Base):
    __tablename__ = "economy"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_daily_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Write `models/stats.py`**

```python
from datetime import date as PyDate

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class VoiceStat(Base):
    __tablename__ = "voice_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), nullable=False)
    date: Mapped[PyDate] = mapped_column(Date, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_voice_stats_user_date"),)


class MessageStat(Base):
    __tablename__ = "message_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), nullable=False)
    date: Mapped[PyDate] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_message_stats_user_date"),)


class ServerStat(Base):
    __tablename__ = "server_stats"

    date: Mapped[PyDate] = mapped_column(Date, primary_key=True)
    total_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    messages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    voice_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_members: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 5: Update `models/__init__.py`**

```python
from models.badges import Badge, UserBadge
from models.economy import Economy
from models.levels import Level
from models.prestiges import Prestige
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
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_models_economy_stats.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): economy, voice/message/server stats models"
```

---

### Task 6: Quests, rewards & remaining models

**Files:**
- Create: `colombina/models/quests.py`
- Create: `colombina/models/rewards.py`
- Modify: `colombina/models/__init__.py`
- Test: `colombina/tests/test_models_quests_rewards.py`

**Interfaces:**
- Consumes: `database.base.Base`, `models.users.User` (Task 3).
- Produces: `models.quests.Quest` (PK `id`, unique `key`), `models.quests.UserQuest` (PK `id`, unique on `user_id`+`quest_id`+`date`), `models.rewards.Reward` (PK `id`, columns `level`, `reward_type`, `reward_value`).

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_models_quests_rewards.py`:
```python
from datetime import date

from models.quests import Quest, UserQuest
from models.rewards import Reward
from models.users import User


async def test_quest_progress_and_reward_roundtrip(db_session):
    user = User(discord_id=4004, username="Odile")
    quest = Quest(key="messages_25", description="Envoyer 25 messages", target_count=25, xp_reward=100, coins_reward=50)
    db_session.add_all([user, quest])
    await db_session.flush()

    user_quest = UserQuest(user_id=user.discord_id, quest_id=quest.id, date=date(2026, 7, 20), progress=10, completed=False)
    reward = Reward(level=10, reward_type="coins", reward_value="1000")
    db_session.add_all([user_quest, reward])
    await db_session.commit()

    fetched_quest_progress = await db_session.get(UserQuest, user_quest.id)
    assert fetched_quest_progress.progress == 10
    assert fetched_quest_progress.completed is False

    assert reward.id is not None
    assert reward.reward_value == "1000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_models_quests_rewards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.quests'`

- [ ] **Step 3: Write `models/quests.py`**

```python
from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Quest(Base):
    __tablename__ = "quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coins_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("key", name="uq_quests_key"),)


class UserQuest(Base):
    __tablename__ = "user_quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.discord_id"), nullable=False)
    quest_id: Mapped[int] = mapped_column(Integer, ForeignKey("quests.id"), nullable=False)
    date: Mapped["Date"] = mapped_column(Date, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("user_id", "quest_id", "date", name="uq_user_quests_user_quest_date"),)
```

- [ ] **Step 4: Write `models/rewards.py`**

```python
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reward_value: Mapped[str] = mapped_column(String(100), nullable=False)
```

- [ ] **Step 5: Update `models/__init__.py`**

```python
from models.badges import Badge, UserBadge
from models.economy import Economy
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
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_models_quests_rewards.py -v`
Expected: PASS

- [ ] **Step 7: Run the full test suite so far**

Run: `cd colombina && pytest -v`
Expected: all tests from Tasks 1-6 PASS.

- [ ] **Step 8: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): quests and rewards models"
```

---

### Task 7: Alembic setup and initial migration

**Files:**
- Create: `colombina/alembic.ini`
- Create: `colombina/alembic/env.py`
- Create: `colombina/alembic/script.py.mako`
- Create: `colombina/alembic/versions/` (first revision file, exact name generated by `alembic revision`)

**Interfaces:**
- Consumes: `database.base.Base` (Task 2), `models/__init__.py` (Tasks 3-6, all 10 tables registered on `Base.metadata`), `config.settings.settings` (Task 1).
- Produces: a runnable `alembic upgrade head` that creates all 10 tables in a real Postgres database. Task 8 adds a second revision on top of this one.

- [ ] **Step 1: Start a throwaway Postgres for this task**

Run:
```bash
docker run -d --name colombina-dev-postgres -e POSTGRES_USER=colombina \
  -e POSTGRES_PASSWORD=colombina -e POSTGRES_DB=colombina -p 5432:5432 postgres:16-alpine
```
Expected: container starts; `docker ps` shows `colombina-dev-postgres` as `Up`.

- [ ] **Step 2: Create `.env` from the example**

Run: `cd colombina && cp .env.example .env`
Then edit `.env` so `DATABASE_URL=postgresql+asyncpg://colombina:colombina@localhost:5432/colombina` and `DISCORD_TOKEN=dev-placeholder-token` (any non-empty value — no real Discord connection happens in this task).

- [ ] **Step 3: Initialize Alembic**

Run: `cd colombina && alembic init alembic`
Expected: creates `alembic.ini` and `alembic/` with `env.py`, `script.py.mako`, `versions/`.

- [ ] **Step 4: Rewrite `alembic/env.py` for async SQLAlchemy**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import models  # noqa: F401  registers all model classes on Base.metadata
from config.settings import settings
from database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Autogenerate the initial revision**

Run: `cd colombina && alembic revision --autogenerate -m "initial schema"`
Expected: a new file appears under `alembic/versions/` containing `op.create_table(...)` calls for all 10 tables (`users`, `levels`, `prestiges`, `badges`, `user_badges`, `economy`, `voice_stats`, `message_stats`, `quests`, `user_quests`, `rewards`, `server_stats`). Open the generated file and confirm every table is present — if any is missing, check that `models/__init__.py` imports it (Tasks 3-6).

- [ ] **Step 6: Apply the migration**

Run: `cd colombina && alembic upgrade head`
Expected: command exits 0 with no errors.

- [ ] **Step 7: Verify the tables exist**

Run:
```bash
docker exec colombina-dev-postgres psql -U colombina -d colombina -c "\dt"
```
Expected: output lists all 12 tables (10 from the design doc, `user_badges` and `user_quests` being the junction tables) plus `alembic_version`.

- [ ] **Step 8: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): alembic setup and initial schema migration"
```

(Leave `colombina-dev-postgres` running — Task 8 reuses it. `.env` stays local/untracked per `.gitignore`.)

---

### Task 8: Seed data migration (badges, rewards, quests)

**Files:**
- Create: `colombina/alembic/versions/` (second revision file, exact name generated by `alembic revision`)
- Test: `colombina/tests/test_seed_data.py`

**Interfaces:**
- Consumes: the Task 7 migration chain, `models.badges.Badge`, `models.rewards.Reward`, `models.quests.Quest`.
- Produces: 14 seeded badges, 16 seeded reward rows (one per level in the brief, level 100 has 3 rows), 3 seeded quest definitions — present in the database after `alembic upgrade head`.

- [ ] **Step 1: Create the empty revision**

Run: `cd colombina && alembic revision -m "seed badges rewards quests"`
Expected: a new empty revision file appears under `alembic/versions/`, chained after the Task 7 revision (its `down_revision` points to Task 7's revision id).

- [ ] **Step 2: Fill in the revision's `upgrade`/`downgrade`**

Open the generated file and replace its body with:

```python
from alembic import op
import sqlalchemy as sa

badges_table = sa.table(
    "badges",
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("icon", sa.String),
    sa.column("rarity", sa.String),
)

rewards_table = sa.table(
    "rewards",
    sa.column("level", sa.Integer),
    sa.column("reward_type", sa.String),
    sa.column("reward_value", sa.String),
)

quests_table = sa.table(
    "quests",
    sa.column("key", sa.String),
    sa.column("description", sa.String),
    sa.column("target_count", sa.Integer),
    sa.column("xp_reward", sa.Integer),
    sa.column("coins_reward", sa.Integer),
)

BADGES = [
    {"key": "debutant", "name": "Débutant", "description": "Obtenu en atteignant le niveau 1", "icon": "🔰", "rarity": "commun"},
    {"key": "actif", "name": "Actif", "description": "Obtenu en atteignant le niveau 5", "icon": "⭐", "rarity": "commun"},
    {"key": "habitue", "name": "Habitué", "description": "Obtenu en atteignant le niveau 20", "icon": "🏅", "rarity": "rare"},
    {"key": "veteran", "name": "Vétéran", "description": "Obtenu en atteignant le niveau 40", "icon": "🎖️", "rarity": "rare"},
    {"key": "legendaire", "name": "Légendaire", "description": "Obtenu en atteignant le niveau 100", "icon": "👑", "rarity": "legendaire"},
    {"key": "roi_du_chat", "name": "Roi du Chat", "description": "Décerné au membre le plus actif en messages", "icon": "💬", "rarity": "epique"},
    {"key": "maitre_vocal", "name": "Maître Vocal", "description": "Décerné au membre le plus actif en vocal", "icon": "🎙️", "rarity": "epique"},
    {"key": "top_10", "name": "Top 10", "description": "Obtenu en atteignant le top 10 du classement XP", "icon": "🔟", "rarity": "rare"},
    {"key": "inviteur", "name": "Inviteur", "description": "Obtenu en validant des invitations", "icon": "📨", "rarity": "rare"},
    {"key": "ancien", "name": "Ancien", "description": "Décerné aux membres présents depuis longtemps sur le serveur", "icon": "⏳", "rarity": "epique"},
    {"key": "argent", "name": "Badge Argent", "description": "Obtenu en atteignant le niveau 30", "icon": "🥈", "rarity": "rare"},
    {"key": "or", "name": "Badge Or", "description": "Obtenu en atteignant le niveau 50", "icon": "🥇", "rarity": "epique"},
    {"key": "platine", "name": "Badge Platine", "description": "Obtenu en atteignant le niveau 80", "icon": "💠", "rarity": "legendaire"},
    {"key": "diamant", "name": "Badge Diamant", "description": "Obtenu en atteignant le niveau 100", "icon": "💎", "rarity": "legendaire"},
]

REWARDS = [
    {"level": 1, "reward_type": "badge", "reward_value": "debutant"},
    {"level": 5, "reward_type": "role", "reward_value": "role_actif"},
    {"level": 10, "reward_type": "coins", "reward_value": "1000"},
    {"level": 15, "reward_type": "access", "reward_value": "vip_bronze"},
    {"level": 20, "reward_type": "role", "reward_value": "role_habitue"},
    {"level": 25, "reward_type": "coins", "reward_value": "2500"},
    {"level": 30, "reward_type": "badge", "reward_value": "argent"},
    {"level": 40, "reward_type": "role", "reward_value": "role_veteran"},
    {"level": 50, "reward_type": "badge", "reward_value": "or"},
    {"level": 60, "reward_type": "access", "reward_value": "vip_argent"},
    {"level": 70, "reward_type": "title", "reward_value": "titre_exclusif"},
    {"level": 80, "reward_type": "badge", "reward_value": "platine"},
    {"level": 90, "reward_type": "item", "reward_value": "coffre_mystere"},
    {"level": 100, "reward_type": "badge", "reward_value": "diamant"},
    {"level": 100, "reward_type": "role", "reward_value": "role_legendaire"},
    {"level": 100, "reward_type": "access", "reward_value": "premium"},
]

QUESTS = [
    {"key": "messages_25", "description": "Envoyer 25 messages", "target_count": 25, "xp_reward": 100, "coins_reward": 50},
    {"key": "voice_60min", "description": "Rester 1h en vocal", "target_count": 60, "xp_reward": 100, "coins_reward": 50},
    {"key": "channels_3", "description": "Écrire dans 3 salons", "target_count": 3, "xp_reward": 100, "coins_reward": 50},
]


def upgrade() -> None:
    op.bulk_insert(badges_table, BADGES)
    op.bulk_insert(rewards_table, REWARDS)
    op.bulk_insert(quests_table, QUESTS)


def downgrade() -> None:
    op.execute(badges_table.delete())
    op.execute(rewards_table.delete())
    op.execute(quests_table.delete())
```

- [ ] **Step 3: Apply the migration**

Run: `cd colombina && alembic upgrade head`
Expected: command exits 0.

- [ ] **Step 4: Write the failing test**

`colombina/tests/test_seed_data.py` (runs against the real dev Postgres, not the sqlite fixture, since it verifies migration-inserted data):

```python
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.engine import create_engine_and_session
from models.badges import Badge
from models.quests import Quest
from models.rewards import Reward


async def test_seed_data_present():
    engine, session_factory = create_engine_and_session(os.environ["DATABASE_URL"])

    async with session_factory() as session:
        badges = (await session.execute(select(Badge))).scalars().all()
        rewards = (await session.execute(select(Reward))).scalars().all()
        quests = (await session.execute(select(Quest))).scalars().all()

    await engine.dispose()

    assert len(badges) == 14
    assert len(rewards) == 16
    assert len(quests) == 3
    assert any(r.level == 100 and r.reward_type == "badge" and r.reward_value == "diamant" for r in rewards)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd colombina && DATABASE_URL=postgresql+asyncpg://colombina:colombina@localhost:5432/colombina pytest tests/test_seed_data.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): seed badges, level rewards and daily quests"
```

---

### Task 9: Redis client helper and health check

**Files:**
- Create: `colombina/utils/redis_client.py`
- Test: `colombina/tests/test_redis_client.py`

**Interfaces:**
- Consumes: `config.settings.settings` (Task 1).
- Produces: `utils.redis_client.create_redis_client() -> redis.asyncio.Redis` and `utils.redis_client.ping(client) -> bool`. `main.py` (Task 11) calls both at startup.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_redis_client.py`:
```python
import fakeredis.aioredis

from utils.redis_client import ping


async def test_ping_returns_true_for_healthy_client():
    client = fakeredis.aioredis.FakeRedis()

    assert await ping(client) is True

    await client.aclose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_redis_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.redis_client'`

- [ ] **Step 3: Write `utils/redis_client.py`**

```python
import redis.asyncio as redis

from config.settings import settings


def create_redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def ping(client: redis.Redis) -> bool:
    return bool(await client.ping())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_redis_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): redis client helper and health check"
```

---

### Task 10: Logging utility

**Files:**
- Create: `colombina/utils/logging.py`
- Test: `colombina/tests/test_logging.py`

**Interfaces:**
- Consumes: `config.settings.settings` (Task 1, for `log_level`).
- Produces: `utils.logging.configure_logging(level: str = "INFO", log_file: str = "colombina.log") -> None`. `main.py` (Task 11) calls this once at startup.

- [ ] **Step 1: Write the failing test**

`colombina/tests/test_logging.py`:
```python
import logging

from utils.logging import configure_logging


def test_configure_logging_sets_level_and_handlers(tmp_path):
    log_file = tmp_path / "test.log"

    configure_logging(level="DEBUG", log_file=str(log_file))

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.logging'`

- [ ] **Step 3: Write `utils/logging.py`**

```python
import logging
import logging.handlers


def configure_logging(level: str = "INFO", log_file: str = "colombina.log") -> None:
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_logging.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): logging configuration utility"
```

---

### Task 11: Cog loader and bot factory (main.py)

**Files:**
- Create: `colombina/utils/cog_loader.py`
- Create: `colombina/main.py`
- Test: `colombina/tests/test_cog_loader.py`
- Test: `colombina/tests/test_bot_factory.py`

**Interfaces:**
- Consumes: `config.settings.settings` (Task 1), `utils.logging.configure_logging` (Task 10), `utils.redis_client.create_redis_client`/`ping` (Task 9), `database.engine.AsyncSessionLocal` (Task 2).
- Produces: `utils.cog_loader.load_all_extensions(bot: commands.Bot, package: str = "cogs") -> list[str]` (returns the names of extensions that failed to load, tolerant of individual failures) and `main.create_bot() -> commands.Bot` (no network I/O — just constructs and configures the bot object, so it's unit-testable).

- [ ] **Step 1: Write the failing test for the cog loader**

`colombina/tests/test_cog_loader.py`:
```python
import discord
from discord.ext import commands

from utils.cog_loader import load_all_extensions


async def test_load_all_extensions_is_tolerant_of_failures(tmp_path, monkeypatch):
    package_dir = tmp_path / "fixture_cogs"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    (package_dir / "good_cog.py").write_text(
        "from discord.ext import commands\n\n"
        "class GoodCog(commands.Cog):\n"
        "    pass\n\n"
        "async def setup(bot):\n"
        "    await bot.add_cog(GoodCog())\n"
    )
    (package_dir / "bad_cog.py").write_text(
        "async def setup(bot):\n"
        "    raise RuntimeError('boom')\n"
    )

    monkeypatch.syspath_prepend(str(tmp_path))

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    failed = await load_all_extensions(bot, package="fixture_cogs")

    assert failed == ["fixture_cogs.bad_cog"]
    assert bot.get_cog("GoodCog") is not None

    await bot.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_cog_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.cog_loader'`

- [ ] **Step 3: Write `utils/cog_loader.py`**

```python
import importlib
import logging
import pkgutil

from discord.ext import commands

logger = logging.getLogger(__name__)


async def load_all_extensions(bot: commands.Bot, package: str = "cogs") -> list[str]:
    module = importlib.import_module(package)
    failed: list[str] = []

    for _finder, name, is_pkg in pkgutil.iter_modules(module.__path__, prefix=f"{package}."):
        if is_pkg:
            continue
        try:
            await bot.load_extension(name)
        except commands.ExtensionError:
            logger.exception("Failed to load extension %s", name)
            failed.append(name)

    return failed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_cog_loader.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for the bot factory**

`colombina/tests/test_bot_factory.py`:
```python
from discord.ext import commands

from main import create_bot


async def test_create_bot_has_expected_prefix_and_intents():
    bot = create_bot()

    assert isinstance(bot, commands.Bot)
    assert bot.command_prefix == "!"
    assert bot.intents.members is True
    assert bot.intents.message_content is True
    assert bot.intents.voice_states is True

    await bot.close()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd colombina && pytest tests/test_bot_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 7: Write `main.py`**

```python
import asyncio
import logging

import discord
from discord.ext import commands

from config.settings import settings
from utils.cog_loader import load_all_extensions
from utils.logging import configure_logging
from utils.redis_client import create_redis_client, ping

logger = logging.getLogger(__name__)


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.voice_states = True

    return commands.Bot(command_prefix=settings.command_prefix, intents=intents)


async def main() -> None:
    configure_logging(level=settings.log_level)

    redis_client = create_redis_client()
    if not await ping(redis_client):
        logger.error("Redis is not reachable at %s", settings.redis_url)

    bot = create_bot()

    @bot.event
    async def on_ready() -> None:
        logger.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else None)

    failed = await load_all_extensions(bot)
    if failed:
        logger.warning("Extensions failed to load: %s", failed)

    await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd colombina && pytest tests/test_bot_factory.py -v`
Expected: PASS

- [ ] **Step 9: Run the full test suite**

Run: `cd colombina && pytest -v`
Expected: all tests from Tasks 1-11 that don't require the dev Postgres/Redis pass (Task 8's `test_seed_data.py` needs `DATABASE_URL` pointed at the running dev Postgres, as in Task 8 Step 5).

- [ ] **Step 10: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): cog loader and bot factory (main.py)"
```

---

### Task 12: Docker packaging

**Files:**
- Create: `colombina/Dockerfile`
- Create: `colombina/entrypoint.sh`
- Create: `colombina/docker-compose.yml`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), `alembic.ini`/`alembic/` (Tasks 7-8), `main.py` (Task 11).
- Produces: `docker compose up` provisions Postgres, Redis, and the bot in one command, running migrations automatically before the bot starts.

- [ ] **Step 1: Write `entrypoint.sh`**

```bash
#!/bin/sh
set -e

alembic upgrade head
exec python main.py
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: colombina
      POSTGRES_PASSWORD: colombina
      POSTGRES_DB: colombina
    volumes:
      - colombina_postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    volumes:
      - colombina_redis_data:/data
    ports:
      - "6379:6379"

  bot:
    build: .
    depends_on:
      - postgres
      - redis
    env_file:
      - .env

volumes:
  colombina_postgres_data:
  colombina_redis_data:
```

- [ ] **Step 4: Make the entrypoint executable and validate the compose file**

Run:
```bash
cd colombina && chmod +x entrypoint.sh && cp -n .env.example .env
docker compose config --quiet
```
Expected: `docker compose config --quiet` exits 0 with no output (valid YAML, all referenced files present).

- [ ] **Step 5: Stop the throwaway Postgres from Task 7 (compose now owns Postgres/Redis)**

Run: `docker rm -f colombina-dev-postgres`
Expected: container removed; from now on, `docker compose up -d postgres redis` is the way to get local Postgres/Redis for running the test suite against real infra (Task 8's `test_seed_data.py`).

- [ ] **Step 6: Full end-to-end smoke test**

Run:
```bash
cd colombina && docker compose up -d postgres redis
sleep 3
docker compose build bot
docker compose run --rm bot alembic upgrade head
docker compose run --rm bot python -c "from models import User; print('models import OK')"
```
Expected: the last command prints `models import OK` with no traceback, confirming the image builds and the app package imports cleanly inside the container. (Starting the bot itself needs a real `DISCORD_TOKEN` in `.env` — out of scope for an automated check here; do that manually once a token exists.)

- [ ] **Step 7: Commit**

```bash
cd colombina && git add -A && git commit -m "feat(colombina): docker packaging (Dockerfile, compose, entrypoint)"
```

---

## Plan Self-Review Notes

- **Spec coverage:** stack (discord.py/Postgres/SQLAlchemy/Alembic/Redis/Docker) → Tasks 1-2, 7, 9, 12; all 10 design-doc tables (+2 junction tables) → Tasks 3-6; seed data → Task 8; prefix+slash command support → Task 11; logging → Task 10; project structure → Task 1. Pillow/Matplotlib and dashboard are out of scope for this tranche per the design doc (tranches D and G).
- **Type/name consistency check:** `Level.user_id`/`Economy.user_id`/etc. all reference `"users.discord_id"` consistently; `load_all_extensions` name and signature match between Task 11's test and implementation; `create_bot`/`main` names match between test and `main.py`.
- Task 5's `models/stats.py` step includes a corrected import block after an initial typo (duplicate `date` alias) — use the corrected block, not the first one shown.
