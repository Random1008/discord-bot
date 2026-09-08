from shared.db import services as shared_services

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
