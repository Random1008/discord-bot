import pytest

from models.users import User
from services.economy import add_balance, InsufficientBalanceError, set_balance, subtract_balance, transfer_balance
from config.settings import settings


async def test_add_balance_creates_economy_row_if_missing(db_session):
    user = User(guild_id=settings.guild_id, user_id=7001, username="Broke")
    db_session.add(user)
    await db_session.flush()

    new_balance = await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    await db_session.commit()

    assert new_balance == 1000


async def test_add_balance_increments_existing_balance(db_session):
    user = User(guild_id=settings.guild_id, user_id=7002, username="Rich")
    db_session.add(user)
    await db_session.flush()

    await add_balance(db_session, settings.guild_id, user.user_id, 500)
    new_balance = await add_balance(db_session, settings.guild_id, user.user_id, 250)
    await db_session.commit()

    assert new_balance == 750


async def test_set_balance_overwrites_an_existing_balance(db_session):
    user = User(guild_id=settings.guild_id, user_id=7010, username="Reset")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 999)
    await db_session.commit()

    await set_balance(db_session, settings.guild_id, user.user_id, 0)
    await db_session.commit()

    balance = await add_balance(db_session, settings.guild_id, user.user_id, 0)
    assert balance == 0


async def test_subtract_balance_reduces_balance(db_session):
    user = User(guild_id=settings.guild_id, user_id=7003, username="Spender")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 500)

    new_balance = await subtract_balance(db_session, settings.guild_id, user.user_id, 200)
    await db_session.commit()

    assert new_balance == 300


async def test_subtract_balance_raises_when_insufficient(db_session):
    user = User(guild_id=settings.guild_id, user_id=7004, username="Broke2")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 100)

    with pytest.raises(InsufficientBalanceError):
        await subtract_balance(db_session, settings.guild_id, user.user_id, 200)


async def test_subtract_balance_raises_for_user_with_no_economy_row(db_session):
    user = User(guild_id=settings.guild_id, user_id=7005, username="NeverEarned")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(InsufficientBalanceError):
        await subtract_balance(db_session, settings.guild_id, user.user_id, 1)


async def test_transfer_balance_moves_coins_between_users(db_session):
    sender = User(guild_id=settings.guild_id, user_id=7006, username="Sender")
    receiver = User(guild_id=settings.guild_id, user_id=7007, username="Receiver")
    db_session.add_all([sender, receiver])
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, sender.user_id, 1000)

    new_sender, new_receiver = await transfer_balance(db_session, settings.guild_id, sender.user_id, receiver.user_id, 300)
    await db_session.commit()

    assert new_sender == 700
    assert new_receiver == 300


async def test_transfer_balance_rejects_non_positive_amount(db_session):
    sender = User(guild_id=settings.guild_id, user_id=7008, username="Sender2")
    receiver = User(guild_id=settings.guild_id, user_id=7009, username="Receiver2")
    db_session.add_all([sender, receiver])
    await db_session.flush()

    with pytest.raises(ValueError):
        await transfer_balance(db_session, settings.guild_id, sender.user_id, receiver.user_id, 0)


async def test_transfer_balance_rejects_self_pay(db_session):
    user = User(guild_id=settings.guild_id, user_id=7010, username="Solo")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(ValueError):
        await transfer_balance(db_session, settings.guild_id, user.user_id, user.user_id, 10)
