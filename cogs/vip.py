"""Verrou de l'étage VIP du casino (salon + rôle).

Deux règles, toutes deux volontairement sans exception :

1. Sans le rôle VIP, impossible d'écrire un message ou de lancer une commande
   dans le salon VIP — même pour un administrateur ou le propriétaire du
   serveur, qui contournent pourtant les permissions Discord :
   - le verrou de commande est un check global (main.py) ;
   - le verrou de message supprime le message et poste un rappel éphémère.
2. Le rôle VIP ne s'obtient QUE par l'achat de l'objet de boutique
   `services.market.VIP_ACCESS_ITEM_KEY` : toute attribution par un autre
   chemin (manuel, autre bot, bypass) est retirée automatiquement dès qu'elle
   est détectée, et `.vipaudit` permet de purger les porteurs illégitimes.
"""

import asyncio
import logging
import time

import discord
from discord.ext import commands

from config.settings import settings
from services.market import (
    VIP_ACCESS_ITEM_KEY,
    format_price,
    get_item_by_key,
    user_owns_item,
)

logger = logging.getLogger(__name__)

VIP_COMMAND_REFUSED = (
    "⛔ L'étage VIP est réservé aux porteurs du rôle VIP — l'accès s'achète dans la boutique."
)


class VipAccessDenied(commands.CheckFailure):
    """Commande refusée dans le salon VIP faute de rôle VIP.

    Levée par le check global : main.py l'ignore explicitement pour ne pas la
    journaliser comme une erreur (le refus est volontaire).
    """

VIP_MESSAGE_REFUSED = (
    "⛔ {member}, l'étage VIP est réservé aux porteurs du rôle VIP. "
    "L'accès s'achète dans la boutique (`$shop`, {price} credits)."
)
# Durée d'affichage du rappel posté dans le salon VIP (0 = aucun rappel).
NOTICE_TTL_SECONDS = 10.0
# Anti-spam : au plus un rappel toutes les N secondes pour un même membre.
NOTICE_COOLDOWN_SECONDS = 30.0
# Taille maximale d'une liste de membres affichée dans un embed.
MAX_LIST = 30


def vip_channel_id() -> str | None:
    return settings.vip_casino_channel_id


def vip_role_id() -> str | None:
    return settings.vip_casino_role_id


def is_vip_channel(channel) -> bool:
    """Vrai si le salon est celui de l'étage VIP configuré (`.config`)."""
    channel_id = vip_channel_id()
    if not channel_id or channel is None:
        return False
    return str(getattr(channel, "id", "")) == str(channel_id)


def has_vip_role(member) -> bool:
    """Vrai si le membre porte le rôle VIP configuré."""
    role_id = vip_role_id()
    if not role_id or member is None:
        return False
    roles = getattr(member, "roles", None) or []
    return any(str(getattr(role, "id", "")) == str(role_id) for role in roles)


async def enforce_vip_channel_lock(ctx: commands.Context) -> bool:
    """Check global : refuse toute commande dans le salon VIP sans le rôle VIP.

    Pas d'exception admin/propriétaire : le verrou est le même pour tout le
    monde (demande explicite de l'utilisateur).
    """
    if ctx.guild is None or not is_vip_channel(getattr(ctx, "channel", None)):
        return True
    if not vip_role_id():
        logger.warning("Salon VIP configuré sans rôle VIP : verrou de commande inactif.")
        return True
    if has_vip_role(getattr(ctx, "author", None)):
        return True
    await ctx.send(VIP_COMMAND_REFUSED)
    raise VipAccessDenied(VIP_COMMAND_REFUSED)


class _StripAccessView(discord.ui.View):
    """Confirmation avant de retirer les accès VIP illégitimes (`.vipaudit`)."""

    def __init__(self, cog: "VipCog", members: list, author_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.members = members
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Seul l'auteur de la commande peut valider.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Retirer les accès illégitimes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        removed = await self.cog.strip_illegitimate(self.members)
        self.confirm.disabled = True
        self.cancel.disabled = True
        await interaction.edit_original_response(
            content=f"🧹 {removed} accès VIP illégitime(s) retiré(s)."
        )
        self.stop()

    @discord.ui.button(label="Laisser", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Aucun accès retiré.", embed=None, view=None)
        self.stop()


class VipCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self._last_notice: dict[int, float] = {}

    def _session(self):
        return self.bot.session_factory()

    # ---------------------------------------------------------------- achat

    async def owns_access(self, guild_id: int, user_id: int) -> bool:
        """Vrai si le joueur a acheté l'accès VIP en boutique.

        Sans objet configuré en base, on ne peut pas arbitrer : on laisse le
        rôle en place (pas de retrait hasardeux en production).
        """
        async with self._session() as session:
            item = await get_item_by_key(session, VIP_ACCESS_ITEM_KEY)
            if item is None:
                return True
            return await user_owns_item(session, guild_id, user_id, item.id)

    async def strip_illegitimate(self, members: list) -> int:
        """Retire le rôle VIP aux membres qui ne l'ont pas acheté."""
        role_id = vip_role_id()
        if not role_id:
            return 0
        role_id_int = int(role_id)
        removed = 0
        for member in members:
            guild = getattr(member, "guild", None)
            role = guild.get_role(role_id_int) if guild is not None else None
            if role is None:
                continue
            try:
                await member.remove_roles(
                    role, reason="Accès casino VIP obtenu sans achat (boutique uniquement)"
                )
            except (discord.Forbidden, discord.HTTPException):
                logger.warning("Impossible de retirer le rôle VIP à %s", member)
                continue
            removed += 1
        return removed

    # ------------------------------------------------- verrou de messages

    async def _notice(self, channel, member) -> None:
        now = time.monotonic()
        if now - self._last_notice.get(member.id, 0.0) < NOTICE_COOLDOWN_SECONDS:
            return
        self._last_notice[member.id] = now
        if NOTICE_TTL_SECONDS <= 0:
            return
        try:
            notice = await channel.send(
                VIP_MESSAGE_REFUSED.format(member=member.mention, price=format_price(10_000_000_000))
            )
        except (discord.Forbidden, discord.HTTPException):
            return
        asyncio.create_task(self._delete_later(notice))

    async def _delete_later(self, message) -> None:
        await asyncio.sleep(NOTICE_TTL_SECONDS)
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Supprime tout message d'un non-porteur du rôle dans le salon VIP."""
        if getattr(message, "guild", None) is None:
            return
        if not is_vip_channel(getattr(message, "channel", None)):
            return
        author = getattr(message, "author", None)
        if author is None or getattr(author, "bot", False):
            return
        if has_vip_role(author):
            return
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Message du salon VIP non supprimé (permissions manquantes ?)")
        await self._notice(message.channel, author)

    # --------------------------------------------- rôle obtenu autrement

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Annule immédiatement un rôle VIP obtenu sans achat."""
        role_id = vip_role_id()
        if not role_id:
            return
        guild = getattr(after, "guild", None)
        if guild is None:
            return
        role_id_int = int(role_id)

        def _has(member) -> bool:
            return any(getattr(r, "id", None) == role_id_int for r in (getattr(member, "roles", None) or []))

        if _has(before) or not _has(after):
            return
        if await self.owns_access(guild.id, after.id):
            return

        role = guild.get_role(role_id_int)
        if role is None:
            return
        try:
            await after.remove_roles(
                role, reason="Accès casino VIP obtenu sans achat (boutique uniquement)"
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Rôle VIP illégitime non retiré à %s", after)
            return
        logger.info("Rôle VIP retiré à %s : obtenu sans achat", after)
        try:
            await after.send(
                "⛔ Ton rôle **Casino VIP** a été retiré : cet accès s'obtient uniquement en "
                "l'achetant dans la boutique (`$shop`)."
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ------------------------------------------------------- commandes

    @commands.command(name="vipguard")
    @commands.has_permissions(administrator=True)
    async def vipguard(self, ctx: commands.Context, action: str = "on") -> None:
        """Applique (ou retire) les permissions Discord du salon VIP.

        `on` : @everyone ne peut plus écrire, le rôle VIP et le bot si.
        `off` : retire les surcharges posées par le bot.
        """
        action = (action or "on").lower()
        if action not in ("on", "off"):
            await ctx.send(f"Usage : `{ctx.prefix}vipguard [on|off]`.")
            return
        channel_id = vip_channel_id()
        role_id = vip_role_id()
        if not channel_id:
            await ctx.send("❌ Aucun salon VIP configuré (`.config`).")
            return
        if not role_id:
            await ctx.send("❌ Aucun rôle VIP configuré (`.config`).")
            return

        channel = ctx.guild.get_channel(int(channel_id))
        if channel is None:
            await ctx.send(f"❌ Salon VIP introuvable (id `{channel_id}`).")
            return
        role = ctx.guild.get_role(int(role_id))
        if role is None:
            await ctx.send(f"❌ Rôle VIP introuvable (id `{role_id}`).")
            return
        bot_member = getattr(ctx.guild, "me", None)

        try:
            if action == "on":
                await channel.set_permissions(
                    ctx.guild.default_role,
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False,
                    create_public_threads=False,
                    create_private_threads=False,
                    send_messages_in_threads=False,
                    reason="Verrou étage VIP",
                )
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    add_reactions=True,
                    read_message_history=True,
                    create_public_threads=True,
                    reason="Accès étage VIP",
                )
                if bot_member is not None:
                    await channel.set_permissions(
                        bot_member,
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True,
                        embed_links=True,
                        attach_files=True,
                        add_reactions=True,
                        reason="Le bot anime et nettoie l'étage VIP",
                    )
            else:
                await channel.set_permissions(
                    ctx.guild.default_role, overwrite=None, reason="Verrou étage VIP retiré"
                )
                await channel.set_permissions(role, overwrite=None, reason="Verrou étage VIP retiré")
                if bot_member is not None:
                    await channel.set_permissions(
                        bot_member, overwrite=None, reason="Verrou étage VIP retiré"
                    )
        except discord.Forbidden:
            await ctx.send("❌ Permission refusée : je dois pouvoir gérer les salons (**Gérer les salons**).")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"❌ Échec de la mise à jour des permissions : `{exc}`.")
            return

        if action == "on":
            await ctx.send(
                f"🔒 **{channel.mention}** verrouillé : seul le rôle **{role.name}** (et moi) peut y écrire. "
                "Les admins contournent les permissions Discord : leurs messages y sont supprimés "
                "automatiquement."
            )
        else:
            await ctx.send(f"🔓 Permissions de **{channel.mention}** remises à l'état par défaut.")

    @commands.command(name="vipaudit")
    @commands.has_permissions(administrator=True)
    async def vipaudit(self, ctx: commands.Context) -> None:
        """Liste les porteurs du rôle VIP qui ne l'ont pas acheté en boutique."""
        role_id = vip_role_id()
        if not role_id:
            await ctx.send("❌ Aucun rôle VIP configuré (`.config`).")
            return
        role_id_int = int(role_id)
        holders = [
            member
            for member in ctx.guild.members
            if any(getattr(r, "id", None) == role_id_int for r in member.roles)
        ]
        if not holders:
            await ctx.send("✅ Personne ne porte le rôle VIP pour le moment.")
            return

        illegitimate = []
        for member in holders:
            if not await self.owns_access(ctx.guild.id, member.id):
                illegitimate.append(member)

        if not illegitimate:
            await ctx.send(
                f"✅ Les {len(holders)} porteur(s) du rôle VIP ont tous acheté leur accès en boutique."
            )
            return

        embed = discord.Embed(
            title="🕵️ Audit du rôle VIP",
            description=(
                f"{len(illegitimate)} membre(s) sur {len(holders)} portent le rôle VIP sans l'avoir acheté.\n"
                "L'attribution manuelle est annulée automatiquement, mais les accès antérieurs peuvent "
                "être purgés ici."
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Sans achat",
            value="\n".join(m.mention for m in illegitimate[:MAX_LIST]) or "—",
            inline=False,
        )
        await ctx.send(embed=embed, view=_StripAccessView(self, illegitimate, ctx.author.id))


async def setup(bot) -> None:
    await bot.add_cog(VipCog(bot))
