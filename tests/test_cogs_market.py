from unittest.mock import Mock

import discord

from config.settings import ADMIN_PERMISSION_ROLE_ID, settings
from models.market import MarketItem
from models.users import User
from services.admin_permission import grant_permission
from cogs.market import EditItemModal, MarketCog


class FakeUser:
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name


class FakeRole:
    def __init__(self, id):
        self.id = id


async def make_admin(db_session, id, display_name, guild_id=None):
    admin = Mock(spec=discord.Member)
    admin.id = id
    admin.display_name = display_name
    admin.roles = [FakeRole(id=ADMIN_PERMISSION_ROLE_ID)]
    await grant_permission(db_session, guild_id if guild_id is not None else settings.guild_id, id, granted_by=1)
    return admin


class FakeGuild:
    def __init__(self, id=None):
        self.id = id if id is not None else settings.guild_id


class FakeResponse:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, ephemeral=False):
        self.messages.append((content, ephemeral))


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()


class FakeContext:
    def __init__(self, prefix="!", author=None, guild=None):
        self.prefix = prefix
        self.author = author
        self.guild = guild if guild is not None else FakeGuild()
        self.sent = []

    async def send(self, content=None, *, embed=None, view=None):
        self.sent.append(embed if embed is not None else content)


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


async def test_shop_only_lists_purchasable_items(db_session):
    db_session.add(MarketItem(key="titre", name="Titre", description="Un titre", price=200, item_type="generic", item_value=None))
    db_session.add(MarketItem(key="cle_divine", name="Clé Divine", description="d", price=0, item_type="key", item_value="divin"))
    await db_session.commit()

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.shop.callback(cog, ctx)

    embed = ctx.sent[0]
    assert embed.title == "🛒 Boutique"
    fields = {f.name: f.value for f in embed.fields}
    assert any("Titre" in name and "200" in value for name, value in fields.items())
    # L'objet à 0 coin est masqué de la boutique (non disponible).
    assert all("Clé Divine" not in name for name in fields)


async def test_shop_shows_empty_message(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.shop.callback(cog, ctx)

    embed = ctx.sent[0]
    assert "vide" in embed.description


async def test_buy_deducts_balance_and_confirms(db_session):
    from services.economy import add_balance
    from services.market import get_item_by_name
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 21001, "Buyer")
    await add_balance(db_session, settings.guild_id, 21001, 1000)
    db_session.add(MarketItem(key="titre2", name="Titre2", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Titre2")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21001, display_name="Buyer"))

    await cog.buy.callback(cog, ctx, args=str(item.id))

    assert "acheté" in ctx.sent[0]


async def test_buy_bypass_admin_skips_cost_on_unpriced_item(db_session):
    from services.market import get_item_by_name

    db_session.add(MarketItem(key="cle_test", name="Clé Test", description="d", price=0, item_type="key", item_value="rare"))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Clé Test")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    admin = await make_admin(db_session, id=21010, display_name="Admin")
    ctx = FakeContext(author=admin)

    await cog.buy.callback(cog, ctx, args=f"bypass {item.id}")

    assert "Bypass" in ctx.sent[0]
    assert "obtenu" in ctx.sent[0]


async def test_buy_bypass_ignored_for_non_admin(db_session):
    from services.market import get_item_by_name

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21011, display_name="Regular"))
    db_session.add(MarketItem(key="cle_test2", name="Clé Test2", description="d", price=0, item_type="key", item_value="rare"))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Clé Test2")

    await cog.buy.callback(cog, ctx, args=f"bypass {item.id}")

    # bypass ignoré (non-admin) : "bypass" reste collé, "bypass <id>" n'est pas un entier valide.
    assert "Usage" in ctx.sent[0]


async def test_buy_unknown_item_reports_not_found(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21002, display_name="Confused"))

    await cog.buy.callback(cog, ctx, args="999999")

    assert "introuvable" in ctx.sent[0]


async def test_buy_rejects_non_numeric_argument(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21003, display_name="Confused2"))

    await cog.buy.callback(cog, ctx, args="N'existe pas")

    assert "Usage" in ctx.sent[0]


async def test_sell_refunds_and_confirms(db_session):
    from services.economy import add_balance
    from services.market import get_item_by_name
    from services.users import get_or_create_user

    await get_or_create_user(db_session, settings.guild_id, 21020, "Seller")
    await add_balance(db_session, settings.guild_id, 21020, 1000)
    db_session.add(MarketItem(key="titre8", name="Titre8", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Titre8")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21020, display_name="Seller"))

    await cog.buy.callback(cog, ctx, args=str(item.id))
    await cog.sell.callback(cog, ctx, args=str(item.id))

    assert "vendu" in ctx.sent[-1]
    assert "240" in ctx.sent[-1]  # 80% of 300


async def test_sell_not_owned_reports_error(db_session):
    from services.market import get_item_by_name

    db_session.add(MarketItem(key="titre9", name="Titre9", description="d", price=300, item_type="generic", item_value=None))
    await db_session.commit()

    item = await get_item_by_name(db_session, "Titre9")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21021, display_name="EmptyHanded"))

    await cog.sell.callback(cog, ctx, args=str(item.id))

    assert "possèdes pas" in ctx.sent[0]


async def test_inventory_lists_owned_items_and_keys(db_session):
    from services.economy import add_balance
    from services.keys import add_key
    from services.market import get_item_by_name

    db_session.add(MarketItem(key="titre10", name="Titre10", description="d", price=100, item_type="generic", item_value=None))
    await db_session.commit()
    await add_balance(db_session, settings.guild_id, 21022, 1000)
    await add_key(db_session, settings.guild_id, 21022, "rare")
    await db_session.commit()

    item = await get_item_by_name(db_session, "Titre10")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21022, display_name="Hoarder"))

    await cog.buy.callback(cog, ctx, args=str(item.id))
    await cog.inventory.callback(cog, ctx)

    listing = ctx.sent[-1]
    assert "Titre10" in listing
    assert "rare" in listing


async def test_inventory_empty_reports_message(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=21023, display_name="Bare"))

    await cog.inventory.callback(cog, ctx)

    assert "vide" in ctx.sent[0]


async def test_market_add_creates_generic_item(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.market_add.callback(cog, ctx, "Cadre Doré", "Un cadre stylé", 250)

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Cadre Doré")
    assert item is not None
    assert item.price == 250
    assert item.guild_id == ctx.guild.id
    assert "ajouté" in ctx.sent[0]


async def test_market_group_without_subcommand_shows_usage(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.market.callback(cog, ctx)

    assert "Usage" in ctx.sent[0]


async def test_market_list_shows_ids(db_session):
    db_session.add(MarketItem(key="titre11", name="Titre11", description="d", price=150, item_type="generic", item_value=None))
    await db_session.commit()

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Titre11")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.market_list.callback(cog, ctx)

    assert "Titre11" in ctx.sent[0]
    assert f"`{item.id}`" in ctx.sent[0]


async def test_market_remove(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.market_add.callback(cog, ctx, "Titre3", "d", 100)

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Titre3")
    assert item is not None

    await cog.market_remove.callback(cog, ctx, name="Titre3")

    assert await get_item_by_name(db_session, "Titre3") is None


async def test_market_edit_unknown_id_reports_not_found(db_session):
    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext()

    await cog.market_edit.callback(cog, ctx, 999999)

    assert "introuvable" in ctx.sent[0]


async def test_market_edit_posts_button_view(db_session):
    db_session.add(MarketItem(key="titre5", name="Titre5", description="d", price=150, item_type="generic", item_value=None))
    await db_session.commit()

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Titre5")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    ctx = FakeContext(author=FakeUser(id=1, display_name="Admin"))

    await cog.market_edit.callback(cog, ctx, item.id)

    assert f"`{item.id}`" in ctx.sent[0]
    assert "Titre5" in ctx.sent[0]


async def test_edit_item_modal_updates_item(db_session):
    db_session.add(MarketItem(key="titre6", name="Titre6", description="d", price=100, item_type="generic", item_value=None))
    await db_session.commit()

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Titre6")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    modal = EditItemModal(cog, item)
    modal.name_input._value = "Titre6 Renomme"
    modal.description_input._value = "nouvelle description"
    modal.price_input._value = "500"

    interaction = FakeInteraction(FakeUser(id=1, display_name="Admin"))
    await modal.on_submit(interaction)

    updated = await get_item_by_name(db_session, "Titre6 Renomme")
    assert updated is not None
    assert updated.price == 500
    assert updated.description == "nouvelle description"
    assert "mis à jour" in interaction.response.messages[0][0]


async def test_edit_item_modal_rejects_invalid_price(db_session):
    db_session.add(MarketItem(key="titre7", name="Titre7", description="d", price=100, item_type="generic", item_value=None))
    await db_session.commit()

    from services.market import get_item_by_name

    item = await get_item_by_name(db_session, "Titre7")

    session_factory = lambda: _FakeSessionContext(db_session)
    cog = MarketCog(bot=FakeBot(session_factory))
    modal = EditItemModal(cog, item)
    modal.price_input._value = "pas un nombre"

    interaction = FakeInteraction(FakeUser(id=1, display_name="Admin"))
    await modal.on_submit(interaction)

    assert "nombre entier" in interaction.response.messages[0][0]
