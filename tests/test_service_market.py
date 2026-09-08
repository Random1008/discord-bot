import random

import pytest

from models.market import MarketItem
from models.users import User
from services.economy import InsufficientBalanceError, add_balance
from config.settings import settings
from models.inventory import UserItem
from models.keys import UserKey
from services.market import (
    ItemNotOwnedError,
    ItemNotPurchasableError,
    ItemNotSellableError,
    MarketItemNotFoundError,
    add_generic_item,
    edit_item,
    edit_item_by_id,
    format_item_list,
    get_item_by_id,
    get_item_by_name,
    list_all_items,
    list_purchasable_items,
    purchase_item,
    purchase_item_by_id,
    remove_item,
    sell_item,
)


class FixedRng(random.Random):
    def uniform(self, low, high):
        return 10.0  # always rolls "commun"


async def test_list_purchasable_items_excludes_zero_price(db_session):
    db_session.add_all(
        [
            MarketItem(key="a", name="A", description="d", price=0, item_type="generic", item_value=None),
            MarketItem(key="b", name="B", description="d", price=100, item_type="generic", item_value=None),
            MarketItem(key="c", name="C", description="d", price=50, item_type="generic", item_value=None),
        ]
    )
    await db_session.commit()

    items = await list_purchasable_items(db_session, settings.guild_id)

    assert [item.name for item in items] == ["C", "B"]


async def test_list_all_items_includes_zero_price(db_session):
    db_session.add_all(
        [
            MarketItem(key="a", name="A", description="d", price=0, item_type="generic", item_value=None),
            MarketItem(key="b", name="B", description="d", price=100, item_type="generic", item_value=None),
        ]
    )
    await db_session.commit()

    items = await list_all_items(db_session, settings.guild_id)

    assert [item.name for item in items] == ["A", "B"]


OTHER_GUILD_ID = settings.guild_id + 1


async def test_list_all_items_hides_item_restricted_to_other_guild(db_session):
    db_session.add_all(
        [
            MarketItem(key="global", name="Global", description="d", price=100, item_type="generic", item_value=None, guild_id=None),
            MarketItem(key="restricted", name="Restricted", description="d", price=100, item_type="generic", item_value=None, guild_id=OTHER_GUILD_ID),
        ]
    )
    await db_session.commit()

    items = await list_all_items(db_session, settings.guild_id)

    assert [item.name for item in items] == ["Global"]


async def test_purchase_item_restricted_to_other_guild_raises_not_found(db_session):
    item = MarketItem(key="restricted2", name="Restricted2", description="d", price=100, item_type="generic", item_value=None, guild_id=OTHER_GUILD_ID)
    db_session.add(item)
    await db_session.commit()

    user = User(guild_id=settings.guild_id, user_id=8099, username="WrongGuildBuyer")
    db_session.add(user)
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)

    with pytest.raises(MarketItemNotFoundError):
        await purchase_item_by_id(db_session, settings.guild_id, user.user_id, item.id)


async def test_purchase_item_restricted_to_own_guild_succeeds(db_session):
    item = MarketItem(key="restricted3", name="Restricted3", description="d", price=100, item_type="generic", item_value=None, guild_id=settings.guild_id)
    db_session.add(item)
    await db_session.commit()

    user = User(guild_id=settings.guild_id, user_id=8098, username="OwnGuildBuyer")
    db_session.add(user)
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)

    result = await purchase_item_by_id(db_session, settings.guild_id, user.user_id, item.id)

    assert result.new_balance == 900


async def test_purchase_generic_item_deducts_balance(db_session):
    user = User(guild_id=settings.guild_id, user_id=8001, username="Buyer")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="titre", name="Titre", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    result = await purchase_item(db_session, settings.guild_id, user.user_id, "Titre")
    await db_session.commit()

    assert result.item.name == "Titre"
    assert result.new_balance == 700


async def test_purchase_key_item_grants_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=8002, username="KeyBuyer")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="cle_rare", name="Clé Rare", description="d", price=200, item_type="key", item_value="rare"))
    await db_session.commit()

    await purchase_item(db_session, settings.guild_id, user.user_id, "Clé Rare")
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "rare")
    )
    assert result.scalar_one().count == 1


async def test_purchase_random_key_item_rolls_rarity(db_session):
    user = User(guild_id=settings.guild_id, user_id=8003, username="RandomKeyBuyer")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="cle_aleatoire", name="Clé Aléatoire", description="d", price=150, item_type="key", item_value="aleatoire"))
    await db_session.commit()

    await purchase_item(db_session, settings.guild_id, user.user_id, "Clé Aléatoire", rng=FixedRng())
    await db_session.commit()

    from sqlalchemy import select
    from models.keys import UserKey

    result = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "commun")
    )
    assert result.scalar_one().count == 1


async def test_purchase_item_not_found_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=8004, username="Confused")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(MarketItemNotFoundError):
        await purchase_item(db_session, settings.guild_id, user.user_id, "Objet Inexistant")


async def test_purchase_zero_price_item_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=8005, username="Eager")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MarketItem(key="cle_divine", name="Clé Divine", description="d", price=0, item_type="key", item_value="divin"))
    await db_session.commit()

    with pytest.raises(ItemNotPurchasableError):
        await purchase_item(db_session, settings.guild_id, user.user_id, "Clé Divine")


async def test_purchase_item_bypass_cost_skips_debit(db_session):
    user = User(guild_id=settings.guild_id, user_id=8007, username="Admin")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 50)
    db_session.add(MarketItem(key="titre3", name="Titre3", description="d", price=500, item_type="generic", item_value=None))
    await db_session.commit()

    result = await purchase_item(db_session, settings.guild_id, user.user_id, "Titre3", bypass_cost=True)
    await db_session.commit()

    assert result.new_balance == 50


async def test_purchase_item_bypass_cost_allows_zero_price(db_session):
    user = User(guild_id=settings.guild_id, user_id=8008, username="Admin2")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MarketItem(key="cle_test", name="Clé Test", description="d", price=0, item_type="key", item_value="rare"))
    await db_session.commit()

    result = await purchase_item(db_session, settings.guild_id, user.user_id, "Clé Test", bypass_cost=True)

    assert result.item.name == "Clé Test"


async def test_purchase_item_insufficient_balance_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=8006, username="Poor")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MarketItem(key="titre2", name="Titre2", description="d", price=500, item_type="generic", item_value=None))
    await db_session.commit()

    with pytest.raises(InsufficientBalanceError):
        await purchase_item(db_session, settings.guild_id, user.user_id, "Titre2")


async def test_add_edit_remove_generic_item_lifecycle(db_session):
    created = await add_generic_item(
        db_session, name="Cadre Doré", price=250, description="Un cadre de profil", guild_id=settings.guild_id
    )
    await db_session.commit()
    assert created.item_type == "generic"
    assert created.item_value is None
    assert created.guild_id == settings.guild_id

    fetched = await get_item_by_name(db_session, "Cadre Doré")
    assert fetched is not None
    assert fetched.price == 250

    edited = await edit_item(db_session, "Cadre Doré", 400, "Un cadre de profil scintillant")
    await db_session.commit()
    assert edited.price == 400
    assert edited.description == "Un cadre de profil scintillant"

    removed = await remove_item(db_session, "Cadre Doré")
    await db_session.commit()
    assert removed is True

    assert await get_item_by_name(db_session, "Cadre Doré") is None


async def test_remove_item_returns_false_when_missing(db_session):
    assert await remove_item(db_session, "N'existe pas") is False


async def test_edit_item_returns_none_when_missing(db_session):
    assert await edit_item(db_session, "N'existe pas", 100, "d") is None


async def test_purchase_generic_item_by_id_adds_to_inventory(db_session):
    user = User(guild_id=settings.guild_id, user_id=9001, username="IdBuyer")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="cadre", name="Cadre", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Cadre")
    result = await purchase_item_by_id(db_session, settings.guild_id, user.user_id, item.id)
    await db_session.commit()

    assert result.new_balance == 700

    from sqlalchemy import select

    inventory = await db_session.execute(
        select(UserItem).where(UserItem.user_id == user.user_id, UserItem.item_id == item.id)
    )
    assert inventory.scalar_one().count == 1


async def test_purchase_item_by_id_not_found_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=9002, username="Confused")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(MarketItemNotFoundError):
        await purchase_item_by_id(db_session, settings.guild_id, user.user_id, 999999)


async def test_sell_generic_item_refunds_80_percent_and_removes_from_inventory(db_session):
    user = User(guild_id=settings.guild_id, user_id=9003, username="Seller")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="cadre2", name="Cadre2", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Cadre2")
    await purchase_item_by_id(db_session, settings.guild_id, user.user_id, item.id)
    await db_session.commit()

    result = await sell_item(db_session, settings.guild_id, user.user_id, item.id)
    await db_session.commit()

    assert result.refund == 240  # 80% of 300
    assert result.new_balance == 940  # 1000 - 300 + 240

    from sqlalchemy import select

    inventory = await db_session.execute(
        select(UserItem).where(UserItem.user_id == user.user_id, UserItem.item_id == item.id)
    )
    assert inventory.scalar_one().count == 0


async def test_sell_generic_item_not_owned_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=9004, username="EmptyHanded")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MarketItem(key="cadre3", name="Cadre3", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Cadre3")

    with pytest.raises(ItemNotOwnedError):
        await sell_item(db_session, settings.guild_id, user.user_id, item.id)


async def test_sell_key_refunds_and_decrements_user_key(db_session):
    user = User(guild_id=settings.guild_id, user_id=9005, username="KeySeller")
    db_session.add(user)
    await db_session.flush()
    await add_balance(db_session, settings.guild_id, user.user_id, 1000)
    db_session.add(MarketItem(key="cle_rare2", name="Clé Rare2", description="d", price=200, item_type="key", item_value="rare"))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Clé Rare2")
    await purchase_item_by_id(db_session, settings.guild_id, user.user_id, item.id)
    await db_session.commit()

    result = await sell_item(db_session, settings.guild_id, user.user_id, item.id)
    await db_session.commit()

    assert result.refund == 160  # 80% of 200

    from sqlalchemy import select

    keys = await db_session.execute(
        select(UserKey).where(UserKey.user_id == user.user_id, UserKey.rarity == "rare")
    )
    assert keys.scalar_one().count == 0


async def test_sell_random_key_catalog_entry_is_not_sellable(db_session):
    user = User(guild_id=settings.guild_id, user_id=9006, username="Confused2")
    db_session.add(user)
    await db_session.flush()
    db_session.add(MarketItem(key="cle_aleatoire2", name="Clé Aléatoire2", description="d", price=150, item_type="key", item_value="aleatoire"))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Clé Aléatoire2")

    with pytest.raises(ItemNotSellableError):
        await sell_item(db_session, settings.guild_id, user.user_id, item.id)


async def test_sell_item_not_found_raises(db_session):
    user = User(guild_id=settings.guild_id, user_id=9007, username="Lost")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(MarketItemNotFoundError):
        await sell_item(db_session, settings.guild_id, user.user_id, 999999)


async def test_format_item_list_shows_ids():
    items = [MarketItem(id=1, key="a", name="A", description="Desc A", price=100, item_type="generic", item_value=None)]
    listing = format_item_list(items)
    assert "`1`" in listing
    assert "**A**" in listing
