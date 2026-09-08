from datetime import datetime, timezone

from models.invest import MarketIndex

# --- Règles d'investissement ---
INVEST_MAX_AMOUNT = 100_000          # plafond de mise
INVEST_DAILY_LIMIT = 5               # max d'investissements par jour
INVEST_LOSS_CHANCE = 0.75            # 75% de chance de perdre la mise
INVEST_WIN_MIN_MULTIPLIER = 2.0      # gain min en cas de succès
INVEST_WIN_MAX_MULTIPLIER = 2.5      # gain max en cas de succès

MARKET_INDEX_MIN = 0.5
MARKET_INDEX_MAX = 1.5
MARKET_INDEX_STEP = 0.05


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def calculate_return(amount: int, rng, market_index: float = 1.0) -> int:
    """75% de chance de tout perdre, sinon gros gain entre x2 et x2.5.

    `market_index` est conservé pour compatibilité de signature mais n'influe
    plus sur le rendement : la nouvelle règle remplace l'ancien multiplicateur
    continu (0.8–1.3)."""
    if rng.random() < INVEST_LOSS_CHANCE:
        return 0
    multiplier = rng.uniform(INVEST_WIN_MIN_MULTIPLIER, INVEST_WIN_MAX_MULTIPLIER)
    return int(amount * multiplier)


def update_market_index(current_index: float, rng) -> float:
    delta = (rng.random() * 2 - 1) * MARKET_INDEX_STEP
    return max(MARKET_INDEX_MIN, min(MARKET_INDEX_MAX, current_index + delta))


async def get_market_index(session, guild_id: int) -> float:
    row = await session.get(MarketIndex, guild_id)
    if row is None:
        row = MarketIndex(guild_id=guild_id, index_value=1.0)
        session.add(row)
        await session.flush()
        return 1.0
    return row.index_value


async def set_market_index(session, guild_id: int, index_value: float) -> None:
    row = await session.get(MarketIndex, guild_id)
    if row is None:
        row = MarketIndex(guild_id=guild_id, index_value=index_value)
        session.add(row)
    else:
        row.index_value = index_value
    await session.flush()


async def record_market_history(session, guild_id: int, index_value: float, is_accurate: bool) -> None:
    """Enregistre une consultation de l'indice dans l'historique (pour le graphique)."""
    from models.invest import MarketHistory
    session.add(MarketHistory(guild_id=guild_id, index_value=index_value, is_accurate=is_accurate))
    await session.flush()


async def get_market_history(session, guild_id: int, limit: int = 30) -> list[dict]:
    """Récupère les dernières entrées de l'historique (plus récentes en dernier pour le graphique)."""
    from sqlalchemy import select, desc
    from models.invest import MarketHistory
    result = await session.execute(
        select(MarketHistory)
        .where(MarketHistory.guild_id == guild_id)
        .order_by(desc(MarketHistory.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [{"index_value": r.index_value, "is_accurate": r.is_accurate} for r in reversed(rows)]


async def purge_old_market_history(session, guild_id: int, keep: int = 100) -> None:
    """Garde uniquement les `keep` dernières entrées par guilde."""
    from sqlalchemy import delete, desc, select
    from models.invest import MarketHistory
    result = await session.execute(
        select(MarketHistory.id)
        .where(MarketHistory.guild_id == guild_id)
        .order_by(desc(MarketHistory.created_at))
        .offset(keep)
    )
    ids_to_delete = list(result.scalars().all())
    if ids_to_delete:
        await session.execute(
            delete(MarketHistory).where(MarketHistory.id.in_(ids_to_delete))
        )
    await session.flush()


# --- Compteur journalier d'investissements ---

async def get_invest_usage(session, guild_id: int, user_id: int) -> int:
    """Nombre d'investissements déjà effectués aujourd'hui."""
    from models.invest import InvestDaily
    row = await session.get(InvestDaily, (guild_id, user_id))
    if row is None or row.invest_date != _today():
        return 0
    return row.invest_count


async def register_invest(session, guild_id: int, user_id: int) -> int:
    """Enregistre un investissement aujourd'hui. Retourne le nouveau total."""
    from models.invest import InvestDaily
    today = _today()
    row = await session.get(InvestDaily, (guild_id, user_id))
    if row is None:
        row = InvestDaily(guild_id=guild_id, user_id=user_id, invest_date=today, invest_count=1)
        session.add(row)
    elif row.invest_date != today:
        row.invest_date = today
        row.invest_count = 1
    else:
        row.invest_count += 1
    await session.flush()
    return row.invest_count
