import random

from sqlalchemy import select

from models.market import MarketItem
from services.economy import add_balance, get_balance, subtract_balance
from services.inventory import add_to_inventory, remove_from_inventory
from services.keys import add_key, get_key_count, remove_key, roll_key_rarity

SELL_REFUND_RATIO = 0.8


class MarketItemNotFoundError(Exception):
    pass


class ItemNotPurchasableError(Exception):
    pass


class ItemNotOwnedError(Exception):
    pass


class ItemNotSellableError(Exception):
    pass


class PurchaseResult:
    def __init__(self, item: MarketItem, new_balance: int):
        self.item = item
        self.new_balance = new_balance


class SellResult:
    def __init__(self, item: MarketItem, refund: int, new_balance: int):
        self.item = item
        self.refund = refund
        self.new_balance = new_balance


def _visible_to_guild(guild_id: int):
    return (MarketItem.guild_id.is_(None)) | (MarketItem.guild_id == guild_id)


async def list_purchasable_items(session, guild_id: int) -> list[MarketItem]:
    result = await session.execute(
        select(MarketItem)
        .where(MarketItem.price > 0, _visible_to_guild(guild_id))
        .order_by(MarketItem.price.asc())
    )
    return list(result.scalars().all())


async def list_all_items(session, guild_id: int) -> list[MarketItem]:
    result = await session.execute(
        select(MarketItem).where(_visible_to_guild(guild_id)).order_by(MarketItem.price.asc())
    )
    return list(result.scalars().all())


async def get_item_by_name(session, name: str) -> MarketItem | None:
    result = await session.execute(select(MarketItem).where(MarketItem.name == name))
    return result.scalar_one_or_none()


async def get_item_by_id(session, item_id: int) -> MarketItem | None:
    return await session.get(MarketItem, item_id)


async def _purchase(session, guild_id: int, user_id: int, item: MarketItem, rng=random, bypass_cost: bool = False) -> PurchaseResult:
    if item.guild_id is not None and item.guild_id != guild_id:
        raise MarketItemNotFoundError(str(item.id))
    if not bypass_cost and item.price <= 0:
        raise ItemNotPurchasableError(item.name)

    if bypass_cost:
        new_balance = await get_balance(session, guild_id, user_id)
    else:
        new_balance = await subtract_balance(session, guild_id, user_id, item.price)

    if item.item_type == "key":
        rarity = roll_key_rarity(rng=rng) if item.item_value == "aleatoire" else item.item_value
        await add_key(session, guild_id, user_id, rarity)
    else:
        await add_to_inventory(session, guild_id, user_id, item.id)

    return PurchaseResult(item=item, new_balance=new_balance)


async def purchase_item(
    session, guild_id: int, user_id: int, item_name: str, rng=random, bypass_cost: bool = False
) -> PurchaseResult:
    item = await get_item_by_name(session, item_name)
    if item is None:
        raise MarketItemNotFoundError(item_name)
    return await _purchase(session, guild_id, user_id, item, rng=rng, bypass_cost=bypass_cost)


async def purchase_item_by_id(
    session, guild_id: int, user_id: int, item_id: int, rng=random, bypass_cost: bool = False
) -> PurchaseResult:
    item = await get_item_by_id(session, item_id)
    if item is None:
        raise MarketItemNotFoundError(str(item_id))
    return await _purchase(session, guild_id, user_id, item, rng=rng, bypass_cost=bypass_cost)


async def sell_item(session, guild_id: int, user_id: int, item_id: int) -> SellResult:
    item = await get_item_by_id(session, item_id)
    if item is None:
        raise MarketItemNotFoundError(str(item_id))

    if item.item_type == "key":
        if item.item_value == "aleatoire":
            raise ItemNotSellableError(str(item_id))
        owned = await get_key_count(session, guild_id, user_id, item.item_value)
        if owned <= 0:
            raise ItemNotOwnedError(str(item_id))
        await remove_key(session, guild_id, user_id, item.item_value)
    else:
        removed = await remove_from_inventory(session, guild_id, user_id, item.id)
        if not removed:
            raise ItemNotOwnedError(str(item_id))

    refund = int(item.price * SELL_REFUND_RATIO)
    new_balance = await add_balance(session, guild_id, user_id, refund)
    return SellResult(item=item, refund=refund, new_balance=new_balance)


async def add_generic_item(session, name: str, price: int, description: str, guild_id: int) -> MarketItem:
    item = MarketItem(
        key=name, name=name, description=description, price=price, item_type="generic", item_value=None, guild_id=guild_id
    )
    session.add(item)
    await session.flush()
    return item


async def remove_item(session, name: str) -> bool:
    item = await get_item_by_name(session, name)
    if item is None:
        return False
    await session.delete(item)
    await session.flush()
    return True


async def edit_item(session, name: str, price: int, description: str) -> MarketItem | None:
    item = await get_item_by_name(session, name)
    if item is None:
        return None
    item.price = price
    item.description = description
    await session.flush()
    return item


async def edit_item_by_id(session, item_id: int, name: str, price: int, description: str) -> MarketItem | None:
    item = await session.get(MarketItem, item_id)
    if item is None:
        return None
    item.name = name
    item.price = price
    item.description = description
    await session.flush()
    return item


def format_item_list(items: list[MarketItem]) -> str:
    if not items:
        return "🛒 La boutique est vide pour le moment."
    lines = ["🛒 **Objets de la boutique** (id • nom — prix — type)"]
    for item in items:
        lines.append(f"`{item.id}` • **{item.name}** — {item.price} coins — {item.item_type}")
    return "\n".join(lines)
