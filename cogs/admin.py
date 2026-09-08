import discord
from discord.ext import commands
from sqlalchemy.exc import NoResultFound

from cogs._xp_common import award_xp
from config.settings import ADMIN_PERMISSION_OWNER_ID, settings
from services.admin_actions import (
    grant_reward_by_level,
    reset_casino,
    reset_currency,
    reset_gacha,
    reset_market,
    reset_tower,
    reset_user,
    set_level,
)
from services.admin_permission import grant_permission, revoke_permission
from services.bot_access import block_user, unblock_user
from services.economy import InsufficientBalanceError, add_balance, set_balance, subtract_balance
from services.leveling import subtract_xp
from services.rewards import grant_badge_by_key
from services.rpg_db import admin_adjust_floor_reached_max, admin_set_floor_reached_max
from services.users import get_or_create_user

def _is_permission_owner(ctx: commands.Context) -> bool:
    return ctx.author.id == ADMIN_PERMISSION_OWNER_ID


RESET_ACTIONS = {
    "argent": (reset_currency, "solde, série quotidienne et boost coins"),
    "monnaie": (reset_currency, "solde, série quotidienne et boost coins"),
    "tour": (reset_tower, "progression de la Tour RPG (niveau, étages, équipement, titres) et Or"),
    "tower": (reset_tower, "progression de la Tour RPG (niveau, étages, équipement, titres) et Or"),
    "casino": (reset_casino, "stats casino et effets casino actifs"),
    "gacha": (reset_gacha, "pity/fragments, personnages, historique et wishlist gacha"),
}


class _MarketResetView(discord.ui.View):
    """Demande à l'admin comment réinitialiser la boutique : supprimer les
    articles ou seulement réinitialiser leurs prix."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.mode: str | None = None

    def _choose(self, interaction: discord.Interaction, mode: str) -> None:
        self.mode = mode
        for item in self.children:
            item.disabled = True
        self.stop()

    @discord.ui.button(label="🗑️ Supprimer les articles", style=discord.ButtonStyle.danger)
    async def _delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce choix n'est pas le tien.", ephemeral=True)
            return
        self._choose(interaction, "delete")
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="🏷️ Réinitialiser les prix", style=discord.ButtonStyle.primary)
    async def _reset_price(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce choix n'est pas le tien.", ephemeral=True)
            return
        self._choose(interaction, "reset_price")
        await interaction.response.edit_message(view=self)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    @commands.command(name="setlevel")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx: commands.Context, membre: discord.Member, niveau: int) -> None:
        if niveau < 0:
            await ctx.send("Le niveau ne peut pas être négatif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            level_row = await set_level(session, guild_id, membre.id, niveau)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} est maintenant niveau **{level_row.level}** ({level_row.xp} XP).")

    @commands.command(name="addxp")
    @commands.has_permissions(administrator=True)
    async def addxp(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        async with self._session() as session:
            await award_xp(
                session,
                ctx.guild,
                lambda: self._announcement_channel(ctx.guild),
                membre,
                montant,
                bypass_alt_guard=True,
            )

        await ctx.send(f"🛠️ {membre.display_name} a reçu **{montant}** XP.")

    @commands.command(name="removexp")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            remaining_xp = await subtract_xp(session, guild_id, membre.id, montant)
            await session.commit()

        await ctx.send(f"🛠️ {montant} XP retirés à {membre.display_name} (XP restant : {remaining_xp}).")

    @commands.command(name="addcoins")
    @commands.has_permissions(administrator=True)
    async def addcoins(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            new_balance = await add_balance(session, guild_id, membre.id, montant)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} a reçu **{montant}** coins (solde : {new_balance}).")

    @commands.command(name="removecoins")
    @commands.has_permissions(administrator=True)
    async def removecoins(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            try:
                new_balance = await subtract_balance(session, guild_id, membre.id, montant, floor=None)  # dette illimitée autorisée
            except InsufficientBalanceError as error:
                await ctx.send(
                    f"{membre.display_name} n'a que **{error.available}** coins (retrait de {montant} demandé)."
                )
                return
            await session.commit()

        await ctx.send(f"🛠️ {montant} coins retirés à {membre.display_name} (solde : {new_balance}).")

    @commands.command(name="resetuser")
    @commands.has_permissions(administrator=True)
    async def resetuser(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await reset_user(session, guild_id, membre.id)
            await session.commit()

        await ctx.send(
            f"🛠️ {membre.display_name} a été entièrement réinitialisé (XP, niveau, prestige, coins, badges, objets — clés gacha conservées)."
        )

    async def _prompt_market_mode(self, ctx: commands.Context) -> str | None:
        """Demande : supprimer les articles de la boutique ou réinitialiser les prix."""
        view = _MarketResetView(ctx.author.id)
        await ctx.send("🛒 Boutique : que veux-tu faire des articles ?", view=view)
        timed_out = await view.wait()
        if timed_out:
            return None
        return view.mode

    @commands.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx: commands.Context, membre: discord.Member, categorie: str) -> None:
        categorie = categorie.lower()
        valid = set(RESET_ACTIONS) | {"boutique", "market", "all"}
        if categorie not in valid:
            await ctx.send("Catégorie invalide. Choisis parmi : argent, tour, casino, gacha, boutique, all.")
            return

        guild_id = ctx.guild.id
        touches_market = categorie in ("boutique", "market", "all")
        market_mode: str | None = None
        if touches_market:
            market_mode = await self._prompt_market_mode(ctx)
            if market_mode is None:
                await ctx.send("⏱️ Reset annulé.")
                return

        async with self._session() as session:
            if categorie in ("boutique", "market"):
                count = await reset_market(session, guild_id, market_mode)
                verb = "supprimé(s)" if market_mode == "delete" else "mis à prix 0 (inachetables)"
                await session.commit()
                await ctx.send(f"🛠️ Boutique : **{count}** article(s) {verb}.")
                return

            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            if categorie == "all":
                await reset_user(session, guild_id, membre.id)
                count = await reset_market(session, guild_id, market_mode)
                verb = "supprimé(s)" if market_mode == "delete" else "mis à prix 0 (inachetables)"
                await session.commit()
                await ctx.send(
                    f"🛠️ {membre.display_name} entièrement réinitialisé (clés gacha conservées). "
                    f"Boutique : **{count}** article(s) {verb}."
                )
                return

            action, label = RESET_ACTIONS[categorie]
            await action(session, guild_id, membre.id)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} : **{label}** réinitialisé(s) (irréversible).")

    @commands.group(name="money", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def money(self, ctx: commands.Context) -> None:
        await ctx.send(f"Usage : `{ctx.prefix}money add|remove|reset @membre [montant]`")

    @money.command(name="add")
    @commands.has_permissions(administrator=True)
    async def money_add(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            new_balance = await add_balance(session, guild_id, membre.id, montant)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} a reçu **{montant}** coins (solde : {new_balance}).")

    @money.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def money_remove(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            try:
                new_balance = await subtract_balance(session, guild_id, membre.id, montant, floor=None)  # dette illimitée autorisée
            except InsufficientBalanceError as error:
                await ctx.send(
                    f"{membre.display_name} n'a que **{error.available}** coins (retrait de {montant} demandé)."
                )
                return
            await session.commit()

        await ctx.send(f"🛠️ {montant} coins retirés à {membre.display_name} (solde : {new_balance}).")

    @money.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def money_reset(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await set_balance(session, guild_id, membre.id, 0)
            await session.commit()

        await ctx.send(f"🛠️ Solde de {membre.display_name} réinitialisé à **0**.")

    @commands.group(name="tower", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def tower(self, ctx: commands.Context) -> None:
        await ctx.send(f"Usage : `{ctx.prefix}tower set|add|remove|reset @membre [étage]`")

    @tower.command(name="set")
    @commands.has_permissions(administrator=True)
    async def tower_set(self, ctx: commands.Context, membre: discord.Member, etage: int) -> None:
        if etage < 0:
            await ctx.send("L'étage ne peut pas être négatif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            new_floor = await admin_set_floor_reached_max(session, guild_id, membre.id, etage)
            await session.commit()

        await ctx.send(f"🛠️ Étage max de {membre.display_name} fixé à **{new_floor}**.")

    @tower.command(name="add")
    @commands.has_permissions(administrator=True)
    async def tower_add(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            new_floor = await admin_adjust_floor_reached_max(session, guild_id, membre.id, montant)
            await session.commit()

        await ctx.send(f"🛠️ Étage max de {membre.display_name} : +{montant} → **{new_floor}**.")

    @tower.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def tower_remove(self, ctx: commands.Context, membre: discord.Member, montant: int) -> None:
        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            new_floor = await admin_adjust_floor_reached_max(session, guild_id, membre.id, -montant)
            await session.commit()

        await ctx.send(f"🛠️ Étage max de {membre.display_name} : -{montant} → **{new_floor}**.")

    @tower.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def tower_reset(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await admin_set_floor_reached_max(session, guild_id, membre.id, 0)
            await session.commit()

        await ctx.send(f"🛠️ Étage max de {membre.display_name} réinitialisé à **0**.")

    @commands.command(name="givereward")
    @commands.has_permissions(administrator=True)
    async def givereward(
        self,
        ctx: commands.Context,
        membre: discord.Member,
        badge: str | None = None,
        niveau: int | None = None,
    ) -> None:
        if (badge is None) == (niveau is None):
            await ctx.send("Précise soit `badge`, soit `niveau` (exactement un des deux).")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)

            if badge is not None:
                try:
                    outcome = await grant_badge_by_key(session, guild_id, membre.id, badge)
                except NoResultFound:
                    await ctx.send(f"Aucun badge avec la clé `{badge}` n'existe.")
                    return
                await session.commit()
                await ctx.send(f"🛠️ Badge **{outcome.reward_value}** accordé à {membre.display_name}.")
                return

            outcomes = await grant_reward_by_level(session, guild_id, membre.id, niveau)
            await session.commit()

        if not outcomes:
            await ctx.send(f"Aucune récompense n'est définie pour le niveau {niveau}.")
            return

        details = ", ".join(outcome.detail for outcome in outcomes)
        await ctx.send(f"🛠️ Récompense(s) du niveau {niveau} accordée(s) à {membre.display_name} : {details}.")

    @commands.group(name="bot", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def access_group(self, ctx: commands.Context) -> None:
        await ctx.send(f"Usage : `{ctx.prefix}bot on|off @membre`")

    @access_group.command(name="off")
    @commands.has_permissions(administrator=True)
    async def access_off(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await block_user(session, guild_id, membre.id, ctx.author.id)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} ne peut plus interagir avec le bot.")

    @access_group.command(name="on")
    @commands.has_permissions(administrator=True)
    async def access_on(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await unblock_user(session, guild_id, membre.id)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} peut de nouveau interagir avec le bot.")

    @commands.command(name="permadd")
    @commands.check(_is_permission_owner)
    async def permadd(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await grant_permission(session, guild_id, membre.id, ctx.author.id)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} peut désormais utiliser les commandes admin (avec le rôle requis).")

    @commands.command(name="permremove")
    @commands.check(_is_permission_owner)
    async def permremove(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await revoke_permission(session, guild_id, membre.id)
            await session.commit()

        await ctx.send(f"🛠️ {membre.display_name} ne peut plus utiliser les commandes admin.")


async def setup(bot) -> None:
    await bot.add_cog(AdminCog(bot))
