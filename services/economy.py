import math

from shared.db import services as shared_services

from models.economy import Economy

# Plancher par défaut (dette max -5 000). Les débits forcés de confiance
# (sentence du procès, .removecoins / .money remove) passent `floor=None`
# pour autoriser un solde négatif sans limite.
DEFAULT_BALANCE_FLOOR = shared_services.DEFAULT_BALANCE_FLOOR


class InsufficientBalanceError(Exception):
    def __init__(self, user_id: int, requested: int, available: int):
        self.user_id = user_id
        self.requested = requested
        self.available = available
        super().__init__(f"user {user_id} has {available} coins, requested {requested}")


async def get_balance(session, guild_id: int, user_id: int) -> int:
    return await shared_services.get_balance(session, guild_id, user_id)


async def get_total_capital(session, guild_id: int, user_id: int) -> int:
    """Capital total d'un joueur = portefeuille + banque."""
    economy = await session.get(Economy, (guild_id, user_id))
    if economy is None:
        return 0
    return economy.balance + economy.bank_balance


def theft_success_chance(base_chance: float, thief_capital: int, target_capital: int) -> float:
    """Chance de vol ajustée par l'écart de patrimoine.

    Plus la victime est riche par rapport au voleur, plus le vol est difficile :
    chance = base / (1 + log10(capital_cible / capital_voleur)).

    L'échelle est logarithmique (et non linéaire) : un écart de 100 000x
    (100 k contre 10 Md) donnerait sinon une chance de 0,0005 %, c'est-à-dire un
    vol impossible. Ici : cible 10x plus riche -> moitié de la chance de base,
    1 000x -> un quart, 100 000x -> ~1/6. Voleur au moins aussi riche que sa
    cible (ou cible ruinée) : chance de base, inchangée.
    """
    if target_capital <= 0 or thief_capital >= target_capital:
        return base_chance
    ratio = target_capital / max(thief_capital, 1)
    return base_chance / (1.0 + math.log10(ratio))


async def add_balance(
    session, guild_id: int, user_id: int, amount: int, *, floor: int | None = DEFAULT_BALANCE_FLOOR
) -> int:
    """Ajoute `amount` (négatif = débit). `floor=None` lève le plancher : le solde
    peut devenir négatif sans limite (dette illimitée)."""
    return await shared_services.add_balance(session, guild_id, user_id, amount, floor=floor)


async def set_balance(
    session, guild_id: int, user_id: int, amount: int, *, floor: int | None = DEFAULT_BALANCE_FLOOR
) -> None:
    await shared_services.set_balance(session, guild_id, user_id, amount, floor=floor)


async def subtract_balance(
    session, guild_id: int, user_id: int, amount: int, *, floor: int | None = DEFAULT_BALANCE_FLOOR
) -> int:
    ok, new_balance = await shared_services.spend_balance(session, guild_id, user_id, amount, floor=floor)
    if not ok:
        raise InsufficientBalanceError(user_id, amount, new_balance)
    return new_balance


async def transfer_balance(session, guild_id: int, from_user_id: int, to_user_id: int, amount: int) -> tuple[int, int]:
    if amount <= 0:
        raise ValueError("transfer amount must be positive")
    if from_user_id == to_user_id:
        raise ValueError("cannot transfer to yourself")

    new_from_balance = await subtract_balance(session, guild_id, from_user_id, amount)
    new_to_balance = await add_balance(session, guild_id, to_user_id, amount)
    return new_from_balance, new_to_balance
