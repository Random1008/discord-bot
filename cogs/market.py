import discord
from discord.ext import commands
from sqlalchemy import select

from models.keys import UserKey
from models.market import MarketItem
from services.admin_permission import can_bypass
from services.economy import InsufficientBalanceError
from services.inventory import list_inventory
from services.market import (
    ItemNotOwnedError,
    ItemNotPurchasableError,
    ItemNotSellableError,
    MarketItemNotFoundError,
    add_generic_item,
    edit_item_by_id,
    format_item_list,
    get_item_by_id,
    list_all_items,
    list_purchasable_items,
    purchase_item_by_id,
    remove_item,
    sell_item,
)
from services.users import get_or_create_user
from utils.permissions import is_admin

SHOP_COLOR = discord.Color.gold()


def build_shop_embed(items: list[MarketItem]) -> discord.Embed:
    embed = discord.Embed(title="🛒 Boutique", color=SHOP_COLOR)
    if not items:
        embed.description = "La boutique est vide pour le moment."
        return embed
    for item in items:
        embed.add_field(
            name=f"{item.name} — `{item.id}`",
            value=f"**{item.price}** coins\n{item.description}",
            inline=False,
        )
    return embed


class EditItemModal(discord.ui.Modal, title="Modifier l'objet"):
    def __init__(self, cog: "MarketCog", item: MarketItem) -> None:
        super().__init__()
        self.cog = cog
        self.item_id = item.id
        self.name_input = discord.ui.TextInput(label="Nom", default=item.name, max_length=100)
        self.description_input = discord.ui.TextInput(
            label="Description", default=item.description, style=discord.TextStyle.paragraph, max_length=255
        )
        self.price_input = discord.ui.TextInput(label="Prix", default=str(item.price), max_length=10)
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            price = int(self.price_input.value)
        except ValueError:
            await interaction.response.send_message("Le prix doit être un nombre entier.", ephemeral=True)
            return

        async with self.cog._session() as session:
            try:
                item = await edit_item_by_id(
                    session,
                    self.item_id,
                    name=self.name_input.value,
                    price=price,
                    description=self.description_input.value,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                await interaction.response.send_message(
                    "Ce nom est déjà utilisé par un autre objet.", ephemeral=True
                )
                return

        if item is None:
            await interaction.response.send_message("Objet introuvable (peut-être déjà supprimé).", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✏️ Objet `{item.id}` mis à jour : **{item.name}** — {item.price} coins — {item.description}",
            ephemeral=True,
        )


class EditItemView(discord.ui.View):
    def __init__(self, cog: "MarketCog", item: MarketItem, author_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.item = item
        self.author_id = author_id

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "Seul l'administrateur ayant lancé la commande peut modifier cet objet.", ephemeral=True
            )
            return
        await interaction.response.send_modal(EditItemModal(self.cog, self.item))


class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context) -> None:
        # Seuls les objets avec un prix > 0 sont disponibles à l'achat (et donc
        # listés ici) : un objet à 0 coin est masqué de la boutique.
        async with self._session() as session:
            items = await list_purchasable_items(session, ctx.guild.id)
        await ctx.send(embed=build_shop_embed(items))

    @commands.command(name="buy")
    async def buy(self, ctx: commands.Context, *, args: str) -> None:
        first_word, _, remainder = args.partition(" ")
        wants_bypass = first_word == "bypass"
        guild_id = ctx.guild.id

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            remaining = remainder.strip() if bypass else args

            try:
                item_id = int(remaining.strip())
            except ValueError:
                await ctx.send(f"Usage : `{ctx.prefix}buy [id]` (voir les ids avec `{ctx.prefix}shop`).")
                return

            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            try:
                result = await purchase_item_by_id(session, guild_id, ctx.author.id, item_id, bypass_cost=bypass)
            except MarketItemNotFoundError:
                await ctx.send(f"Objet introuvable pour l'id `{item_id}`.")
                return
            except ItemNotPurchasableError:
                await ctx.send("Cet objet n'est pas disponible à l'achat.")
                return
            except InsufficientBalanceError:
                await ctx.send("Solde insuffisant.")
                return
            await session.commit()

        if bypass:
            await ctx.send(f"✅ [Bypass admin] **{result.item.name}** obtenu sans débit. Solde : {result.new_balance}.")
        else:
            await ctx.send(
                f"✅ Tu as acheté **{result.item.name}** pour {result.item.price} coins. Solde restant : {result.new_balance}."
            )

    @commands.command(name="sell")
    async def sell(self, ctx: commands.Context, *, args: str) -> None:
        try:
            item_id = int(args.strip())
        except ValueError:
            await ctx.send(f"Usage : `{ctx.prefix}sell [id]` (voir tes objets avec `{ctx.prefix}inventory`).")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            try:
                result = await sell_item(session, guild_id, ctx.author.id, item_id)
            except MarketItemNotFoundError:
                await ctx.send(f"Objet introuvable pour l'id `{item_id}`.")
                return
            except ItemNotSellableError:
                await ctx.send("Cet objet ne peut pas être revendu directement.")
                return
            except ItemNotOwnedError:
                await ctx.send("Tu ne possèdes pas cet objet.")
                return
            await session.commit()

        await ctx.send(
            f"💰 Tu as vendu **{result.item.name}** pour {result.refund} coins. Solde restant : {result.new_balance}."
        )

    @commands.command(name="inventory")
    async def inventory(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            inventory_rows = await list_inventory(session, guild_id, ctx.author.id)
            items_by_id = {}
            for row in inventory_rows:
                item = await get_item_by_id(session, row.item_id)
                if item is not None:
                    items_by_id[row.item_id] = item

            key_result = await session.execute(
                select(UserKey).where(
                    UserKey.guild_id == guild_id, UserKey.user_id == ctx.author.id, UserKey.count > 0
                )
            )
            keys = list(key_result.scalars().all())

        lines = ["🎒 **Ton inventaire**"]
        for row in inventory_rows:
            item = items_by_id.get(row.item_id)
            if item is not None:
                lines.append(f"`{item.id}` • **{item.name}** x{row.count}")
        for key in keys:
            lines.append(f"🔑 {key.rarity} x{key.count}")

        if len(lines) == 1:
            await ctx.send("🎒 Ton inventaire est vide.")
            return
        await ctx.send("\n".join(lines))

    @commands.group(name="market", invoke_without_command=True)
    async def market(self, ctx: commands.Context) -> None:
        await ctx.send(f"Usage : `{ctx.prefix}market add|remove|edit|list ...`")

    @market.command(name="list")
    @commands.has_permissions(administrator=True)
    async def market_list(self, ctx: commands.Context) -> None:
        async with self._session() as session:
            items = await list_all_items(session, ctx.guild.id)
        await ctx.send(format_item_list(items))

    @market.command(name="add")
    @commands.has_permissions(administrator=True)
    async def market_add(self, ctx: commands.Context, name: str, description: str, price: int) -> None:
        async with self._session() as session:
            await add_generic_item(session, name=name, price=price, description=description, guild_id=ctx.guild.id)
            await session.commit()
        await ctx.send(f"✅ Objet **{name}** ajouté à la boutique de ce serveur ({price} coins).")

    @market.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def market_remove(self, ctx: commands.Context, *, name: str) -> None:
        async with self._session() as session:
            removed = await remove_item(session, name)
            await session.commit()
        if removed:
            await ctx.send(f"🗑️ Objet **{name}** retiré de la boutique.")
        else:
            await ctx.send(f"Objet introuvable : {name}")

    @market.command(name="edit")
    @commands.has_permissions(administrator=True)
    async def market_edit(self, ctx: commands.Context, item_id: int) -> None:
        async with self._session() as session:
            item = await get_item_by_id(session, item_id)
        if item is None:
            await ctx.send(f"Objet introuvable pour l'id `{item_id}`.")
            return
        view = EditItemView(self, item, author_id=ctx.author.id)
        view.message = await ctx.send(f"Édition de `{item.id}` • **{item.name}** :", view=view)


async def setup(bot) -> None:
    await bot.add_cog(MarketCog(bot))
