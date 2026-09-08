from models.market import MarketItem


async def test_market_item_roundtrip(db_session):
    item = MarketItem(
        key="cle_rare", name="Clé Rare", description="Une clé de rareté rare",
        price=0, item_type="key", item_value="rare",
    )
    db_session.add(item)
    await db_session.commit()

    fetched = await db_session.get(MarketItem, item.id)
    assert fetched.key == "cle_rare"
    assert fetched.name == "Clé Rare"
    assert fetched.price == 0
    assert fetched.item_type == "key"
    assert fetched.item_value == "rare"


async def test_market_item_generic_has_no_item_value(db_session):
    item = MarketItem(
        key="titre_perso", name="Titre Personnalisé", description="Un titre sur mesure",
        price=500, item_type="generic", item_value=None,
    )
    db_session.add(item)
    await db_session.commit()

    fetched = await db_session.get(MarketItem, item.id)
    assert fetched.item_value is None
