"""Monde criminel : activités illégales à risque/rendement variés.

Toutes s'utilisent avec le préfixe `$` (commandes d'argent, cf. main.py) et
partagent le même timer de prison (`prison_until`) que `$crime`/`$rob` :
en prison, aucune de ces commandes n'est utilisable (sauf bypass admin).

Cible optionnelle (mention ou ID) pour les commandes listées dans
``TARGETABLE_NAMES`` :
- sans cible : 100% de réussite, gains de base ;
- avec cible : 75% de réussite, gains doublés volés à la victime.

``$mafia`` ouvre un marché à prix réduits : 35% de réussir à entrer, le bot
t'ajoute alors aux permissions d'un salon mafia privé (configuré via
`.config`) et y poste un marché remisé -30 à -60%. L'accès est révoqué dès
que tu achètes ton unique objet. ``$blanchir`` a son propre flow (mise en
jeu) et ``$hijack`` garde son comportement actuel.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
import re

import discord
from discord.ext import commands

from config.settings import settings
from models.economy import Economy
from services.admin_permission import can_bypass
from services.economy import add_balance
from services.inventory import add_to_inventory
from services.keys import add_key, roll_key_rarity
from services.market import get_item_by_id, list_purchasable_items
from services.users import get_or_create_user
from shared.db import services as shared_services


# Vol d'un joueur : 75% de réussite mais gains doublés (×2), volés à la victime.
TARGET_SUCCESS_CHANCE = 0.75
TARGET_GAIN_MULT = 2.0

# Commandes acceptant une cible optionnelle (@mention/ID) pour voler un joueur.
# Exclues : braquage, chantage, contrebande (taux d'origine), mafia (marché
# dédié), blanchir (flow dédié) et hijack (traité à part).
TARGETABLE_NAMES = {
    "hack", "deal", "pirate", "fraude", "cambriolage",
    "escroquerie", "vol", "falsifier", "infiltration",
}

# Marché de la mafia : 35% de rentrer, remise aléatoire 30-60% sur le $shop,
# un seul achat possible, accès au salon révoqué après l'achat.
MAFIA_ENTRY_CHANCE = 0.35
MAFIA_DISCOUNT_LOW = 0.30
MAFIA_DISCOUNT_HIGH = 0.60
MAFIA_COOLDOWN = 43200
MAFIA_PCT_LOSS = 0.10
MAFIA_MIN_LOSS = 2000
MAFIA_PRISON_DURATION = 7200


def _fmt_duration(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} {m:02d}min"
    if m:
        return f"{m}min {s:02d}s"
    return f"{s}s"


def _extract_target_token(args: tuple[str, ...]) -> str | None:
    """Renvoie le premier token qui n'est pas ``bypass`` (la cible), sinon None."""
    for a in args:
        if a != "bypass":
            return a
    return None


async def _resolve_member(ctx: commands.Context, token: str):
    """Résout une cible depuis un @mention, un ID ou un pseudo/nom."""
    guild = ctx.guild
    if guild is None:
        return None
    m = re.match(r"<@!?(\d+)>", token)
    if m:
        return guild.get_member(int(m.group(1)))
    if token.isdigit():
        user_id = int(token)
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                return None
        return member
    return discord.utils.find(
        lambda u: u.name.lower() == token.lower()
        or (u.display_name or "").lower() == token.lower(),
        guild.members,
    )


def _roll_gain(spec: "CrimeSpec", target_mode: bool) -> tuple[int, str]:
    """Calcule le gain et une description (base × bonus × cible)."""
    base = random.randint(spec.gain_min, spec.gain_max)
    mult = 1.0
    parts = [f"base **{base:,}**"]
    if spec.mult_high > 0:
        m = random.uniform(spec.mult_low, spec.mult_high)
        mult *= m
        parts.append(f"× bonus ×{m:.2f}")
    if target_mode:
        mult *= TARGET_GAIN_MULT
        parts.append(f"× cible ×{TARGET_GAIN_MULT:.1f}")
    gain = round(base * mult)
    breakdown = f" ({' '.join(parts)})" if (spec.mult_high > 0 or target_mode) else ""
    return gain, breakdown


@dataclass(frozen=True)
class CrimeSpec:
    name: str
    cooldown_field: str
    cooldown: int
    success_chance: float
    emoji_success: str
    emoji_fail: str
    title_success: str
    title_fail: str
    action: str
    gain_min: int
    gain_max: int
    fine: int = 0
    pct_loss: float = 0.0
    min_loss: int = 0
    prison_duration: int = 0
    mult_low: float = 0.0
    mult_high: float = 0.0


# Rendements/risques équilibrés les uns par rapport aux autres (cf. l'énoncé).
SPECS: dict[str, CrimeSpec] = {
    "hack": CrimeSpec(
        name="hack", cooldown_field="last_hack_at", cooldown=900,
        success_chance=0.55, emoji_success="💻", emoji_fail="🚨",
        title_success="Piratage réussi !", title_fail="Piratage raté !",
        action="piraté un compte bancaire", gain_min=100, gain_max=500, fine=100,
    ),
    "braquage": CrimeSpec(
        name="braquage", cooldown_field="last_braquage_at", cooldown=21600,
        success_chance=0.35, emoji_success="🏦", emoji_fail="🚔",
        title_success="Braquage réussi !", title_fail="Braquage raté !",
        action="braqué une banque", gain_min=5000, gain_max=50000,
        fine=5000, prison_duration=3600,
    ),
    "deal": CrimeSpec(
        name="deal", cooldown_field="last_deal_at", cooldown=1800,
        success_chance=0.60, emoji_success="🤝", emoji_fail="👮",
        title_success="Deal conclu !", title_fail="Deal foireux !",
        action="conclu un deal illégal", gain_min=200, gain_max=2000, fine=200,
    ),
    "pirate": CrimeSpec(
        name="pirate", cooldown_field="last_pirate_at", cooldown=1200,
        success_chance=0.50, emoji_success="🖥️", emoji_fail="🛡️",
        title_success="Serveur piraté !", title_fail="Piratage détecté !",
        action="piraté un serveur virtuel", gain_min=300, gain_max=1500, fine=150,
    ),
    "fraude": CrimeSpec(
        name="fraude", cooldown_field="last_fraude_at", cooldown=3600,
        success_chance=0.45, emoji_success="💳", emoji_fail="🏛️",
        title_success="Fraude réussie !", title_fail="Fraude démasquée !",
        action="réussi une fraude bancaire", gain_min=2000, gain_max=10000,
        pct_loss=0.10, min_loss=500, prison_duration=1800,
    ),
    "cambriolage": CrimeSpec(
        name="cambriolage", cooldown_field="last_cambriolage_at", cooldown=2700,
        success_chance=0.50, emoji_success="🏠", emoji_fail="🚨",
        title_success="Cambriolage réussi !", title_fail="Alarme déclenchée !",
        action="cambriolé une maison", gain_min=1000, gain_max=5000,
        fine=1000, prison_duration=1800,
    ),
    "escroquerie": CrimeSpec(
        name="escroquerie", cooldown_field="last_escroquerie_at", cooldown=600,
        success_chance=0.60, emoji_success="🃏", emoji_fail="🕵️",
        title_success="Escroquerie réussie !", title_fail="Escroquerie éventée !",
        action="escroqué un PNJ", gain_min=50, gain_max=300, fine=50,
    ),
    "chantage": CrimeSpec(
        name="chantage", cooldown_field="last_chantage_at", cooldown=1500,
        success_chance=0.55, emoji_success="🎭", emoji_fail="📞",
        title_success="Chantage payant !", title_fail="Chantage retourné !",
        action="fait chanter un PNJ", gain_min=300, gain_max=1500,
        fine=300, prison_duration=1200,
    ),
    "contrebande": CrimeSpec(
        name="contrebande", cooldown_field="last_contrebande_at", cooldown=3600,
        success_chance=0.45, emoji_success="📦", emoji_fail="🛃",
        title_success="Contrebande passée !", title_fail="Arrêté aux douanes !",
        action="passé de la contrebande", gain_min=1500, gain_max=8000,
        fine=1500, prison_duration=2400,
    ),
    "vol": CrimeSpec(
        name="vol", cooldown_field="last_vol_at", cooldown=300,
        success_chance=0.65, emoji_success="👛", emoji_fail="🫳",
        title_success="Vol réussi !", title_fail="Vol raté !",
        action="volé un passant", gain_min=20, gain_max=150, fine=30,
    ),
    "falsifier": CrimeSpec(
        name="falsifier", cooldown_field="last_falsifier_at", cooldown=1800,
        success_chance=0.55, emoji_success="📜", emoji_fail="🖋️",
        title_success="Documents falsifiés !", title_fail="Falsification repérée !",
        action="falsifié des documents", gain_min=100, gain_max=400,
        fine=300, mult_low=1.5, mult_high=3.0,
    ),
    "infiltration": CrimeSpec(
        name="infiltration", cooldown_field="last_infiltration_at", cooldown=2400,
        success_chance=0.50, emoji_success="🥷", emoji_fail="🔦",
        title_success="Infiltration réussie !", title_fail="Infiltration découverte !",
        action="infiltré un groupe", gain_min=800, gain_max=4000,
        fine=800, prison_duration=1800,
    ),
    "hijack": CrimeSpec(
        name="hijack", cooldown_field="last_hijack_at", cooldown=3600,
        success_chance=0.40, emoji_success="🏎️", emoji_fail="💥",
        title_success="Véhicule détourné !", title_fail="Piège !",
        action="détourné un véhicule", gain_min=3000, gain_max=15000,
        fine=3000, prison_duration=3600,
    ),
}

# blanchir a un flow dédié (mise en jeu, multiplicateur, saisie).
BLANCHIR_COOLDOWN = 3600
BLANCHIR_SUCCESS_CHANCE = 0.50
BLANCHIR_MULT_LOW = 1.3
BLANCHIR_MULT_HIGH = 1.8


class MafiaMarketSelect(discord.ui.Select):
    """Menu du marché de la mafia : choisit UN objet au prix réduit."""

    def __init__(self, cog, author_id: int, guild_id: int, items, discount: float) -> None:
        # items : liste de tuples (item_id, name, price)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.discount = discount
        options = []
        for item_id, name, price in items[:25]:
            discounted = max(1, int(price * (1 - discount)))
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    value=str(item_id),
                    description=f"{discounted} coins (-{int(discount * 100)}%) au lieu de {price}",
                )
            )
        super().__init__(placeholder="Choisis UN objet (1 seul achat possible)...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce marché n'est pas le tien.", ephemeral=True)
            return

        item_id = int(self.values[0])
        try:
            async with self.cog._session() as session:
                await get_or_create_user(session, self.guild_id, self.author_id, interaction.user.display_name)
                name, discounted, new_bal = await self.cog._mafia_purchase(
                    session, self.guild_id, self.author_id, item_id, self.discount
                )
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        self.disabled = True
        await interaction.response.edit_message(
            content=(
                f"✅ Tu as acheté **{name}** pour **{discounted:,} coins** "
                f"(-{int(self.discount * 100)}%). Solde : **{new_bal:,} credits**."
            ),
            view=self.view,
        )

        # Accès révoqué dès l'achat (réalisé par la vue parente).
        view = self.view
        if view is not None and hasattr(view, "revoke_access"):
            await view.revoke_access()


class MafiaMarketView(discord.ui.View):
    def __init__(self, cog, author, channel, items, discount: float) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.author = author
        self.channel = channel
        self.guild_id = channel.guild.id
        self.discount = discount
        self._access_revoked = False
        self.message: discord.Message | None = None
        self.add_item(MafiaMarketSelect(cog, author.id, channel.guild.id, items, discount))

    async def revoke_access(self) -> None:
        """Retire l'accès au salon mafia (idempotent)."""
        if self._access_revoked:
            return
        self._access_revoked = True
        member = self.channel.guild.get_member(self.author.id) or self.author
        try:
            await self.channel.set_permissions(member, overwrite=None)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.revoke_access()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class UnderworldCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    async def _is_in_prison(self, session, guild_id: int, user_id: int) -> tuple[bool, int]:
        """Retourne (en_prison, secondes_restantes)."""
        prison_until = await shared_services.get_economy_cooldown(session, guild_id, user_id, "prison_until")
        if prison_until is None:
            return False, 0
        if prison_until.tzinfo is None:
            prison_until = prison_until.replace(tzinfo=timezone.utc)
        rem = int((prison_until - datetime.now(timezone.utc)).total_seconds())
        return rem > 0, max(0, rem)

    async def _mafia_purchase(self, session, guild_id: int, user_id: int, item_id: int, discount: float):
        """Achète un objet au prix réduit. Lève ValueError si impossible."""
        item = await get_item_by_id(session, item_id)
        if item is None or item.price <= 0:
            raise ValueError("cet objet n'est plus disponible")
        name = item.name
        discounted = max(1, int(item.price * (1 - discount)))
        economy = await session.get(Economy, (guild_id, user_id))
        wallet = economy.balance if economy else 0
        if wallet < discounted:
            raise ValueError(f"solde insuffisant ({wallet:,} < {discounted:,} coins)")
        new_bal = await add_balance(session, guild_id, user_id, -discounted)
        if item.item_type == "key":
            rarity = roll_key_rarity() if item.item_value == "aleatoire" else item.item_value
            await add_key(session, guild_id, user_id, rarity)
        else:
            await add_to_inventory(session, guild_id, user_id, item.id)
        await session.commit()
        return name, discounted, new_bal

    async def _mafia_market(self, ctx: commands.Context, args: tuple[str, ...]) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id

        mafia_channel_id = settings.mafia_channel_id
        channel = None
        if mafia_channel_id:
            try:
                channel = ctx.guild.get_channel(int(mafia_channel_id))
            except ValueError:
                channel = None
        if channel is None:
            await ctx.send("❌ Le salon du marché de la mafia n'est pas configuré (admin : `.config` → Salons).")
            return

        suffix = ""

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)

            if not bypass:
                in_prison, rem = await self._is_in_prison(session, guild_id, ctx.author.id)
                if in_prison:
                    await ctx.send(f"🔒 Tu es en prison. Libéré dans **{_fmt_duration(rem)}**.")
                    return

            last = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_mafia_at")
            if not bypass and last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < MAFIA_COOLDOWN:
                    rem = MAFIA_COOLDOWN - int(elapsed)
                    await ctx.send(f"⏳ Cooldown `mafia`. Reviens dans **{_fmt_duration(rem)}**.")
                    return

            await shared_services.set_economy_cooldown(
                session, guild_id, ctx.author.id, "last_mafia_at", datetime.now(timezone.utc)
            )
            suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)

            if random.random() >= MAFIA_ENTRY_CHANCE:
                economy = await session.get(Economy, (guild_id, ctx.author.id))
                total = (economy.balance if economy else 0) + (economy.bank_balance if economy else 0)
                loss = max(MAFIA_MIN_LOSS, int(total * MAFIA_PCT_LOSS))
                new_bal = await add_balance(session, guild_id, ctx.author.id, -loss)
                await shared_services.set_economy_cooldown(
                    session, guild_id, ctx.author.id, "prison_until",
                    datetime.now(timezone.utc) + timedelta(seconds=MAFIA_PRISON_DURATION),
                )
                await session.commit()
                embed = discord.Embed(
                    title="🔫 La mafia s'est retournée !",
                    description=(
                        f"Les portes ne se sont pas ouvertes. Pertes : **{loss:,} credits**"
                        f" ({MAFIA_PCT_LOSS:.0%} de ton argent).\nPrison : **{_fmt_duration(MAFIA_PRISON_DURATION)}**\n"
                        f"Solde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0xE74C3C,
                )
                await ctx.send(embed=embed)
                return

            items = await list_purchasable_items(session, guild_id)
            items_data = [(item.id, item.name, item.price) for item in items]
            discount = random.uniform(MAFIA_DISCOUNT_LOW, MAFIA_DISCOUNT_HIGH)
            await session.commit()

        if not items_data:
            await ctx.send("🏪 Le marché de la mafia est vide pour le moment.")
            return

        # Ouvrir les portes : accorder l'accès au salon mafia.
        try:
            await channel.set_permissions(ctx.author, read_messages=True)
        except discord.Forbidden:
            await ctx.send("❌ Le bot n'a pas la permission de modifier le salon mafia (il lui faut « Gérer les salons »).")
            return
        except discord.HTTPException:
            await ctx.send("❌ Impossible de modifier les permissions du salon mafia.")
            return

        pct = int(discount * 100)
        embed = discord.Embed(
            title="🕴️ Marché de la mafia",
            description=(
                f"**Promo -{pct}%** sur tous les objets du shop.\n"
                f"Choisis **UN** objet (1 seul achat possible) dans le menu ci-dessous."
            ),
            color=0x2ECC71,
        )
        view = MafiaMarketView(self, ctx.author, channel, items_data, discount)
        view.message = await channel.send(embed=embed, view=view)

        await ctx.send(f"🕴️ Les portes s'ouvrent ! Rends-toi dans {channel.mention} (-{pct}% sur tout, 1 seul achat).")

    async def _run_crime(self, ctx: commands.Context, spec: CrimeSpec, args: tuple[str, ...]) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id

        can_target = spec.name in TARGETABLE_NAMES
        target = None
        target_mode = False
        if can_target:
            target_token = _extract_target_token(args)
            if target_token is not None:
                target = await _resolve_member(ctx, target_token)
                if target is None:
                    await ctx.send("❌ Cible introuvable. Utilise un @mention ou un ID.")
                    return
                if target.bot or target.id == ctx.author.id:
                    await ctx.send("❌ Cible invalide.")
                    return
                target_mode = True

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)

            if not bypass:
                in_prison, rem = await self._is_in_prison(session, guild_id, ctx.author.id)
                if in_prison:
                    await ctx.send(f"🔒 Tu es en prison. Libéré dans **{_fmt_duration(rem)}**.")
                    return

            last = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, spec.cooldown_field)
            if not bypass and last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < spec.cooldown:
                    rem = spec.cooldown - int(elapsed)
                    await ctx.send(f"⏳ Cooldown `{spec.name}`. Reviens dans **{_fmt_duration(rem)}**.")
                    return

            await shared_services.set_economy_cooldown(
                session, guild_id, ctx.author.id, spec.cooldown_field, datetime.now(timezone.utc)
            )

            suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)

            victim_bal = 0
            if target_mode:
                await get_or_create_user(session, guild_id, target.id, target.display_name)
                victim = await session.get(Economy, (guild_id, target.id))
                victim_bal = victim.balance if victim else 0
                if victim_bal <= 0:
                    await ctx.send(f"❌ {target.display_name} n'a rien à voler (portefeuille : 0 credits).")
                    return

            if can_target:
                success_chance = TARGET_SUCCESS_CHANCE if target_mode else 1.0
            else:
                success_chance = spec.success_chance

            if random.random() < success_chance:
                gain, breakdown = _roll_gain(spec, target_mode)
                if target_mode:
                    if gain > victim_bal:
                        gain = victim_bal
                    await add_balance(session, guild_id, target.id, -gain)
                    new_bal = await add_balance(session, guild_id, ctx.author.id, gain)
                    await session.commit()
                    embed = discord.Embed(
                        title=f"{spec.emoji_success} {spec.title_success}",
                        description=(
                            f"Tu as {spec.action} et volé **{gain:,} credits** à "
                            f"{target.display_name}{breakdown}.\n"
                            f"Solde : **{new_bal:,} credits**{suffix}"
                        ),
                        color=0x2ECC71,
                    )
                else:
                    new_bal = await add_balance(session, guild_id, ctx.author.id, gain)
                    await session.commit()
                    embed = discord.Embed(
                        title=f"{spec.emoji_success} {spec.title_success}",
                        description=(
                            f"Tu as {spec.action} et gagné **{gain:,} credits**{breakdown}.\n"
                            f"Solde : **{new_bal:,} credits**{suffix}"
                        ),
                        color=0x2ECC71,
                    )
            else:
                if spec.pct_loss > 0:
                    economy = await session.get(Economy, (guild_id, ctx.author.id))
                    total_money = (economy.balance if economy else 0) + (economy.bank_balance if economy else 0)
                    loss = max(spec.min_loss, int(total_money * spec.pct_loss))
                    loss_desc = f"Pertes : **{loss:,} credits** ({spec.pct_loss:.0%} de ton argent)"
                else:
                    loss = spec.fine
                    loss_desc = f"Amende : **{loss:,} credits**"
                new_bal = await add_balance(session, guild_id, ctx.author.id, -loss)

                prison_note = ""
                if spec.prison_duration > 0:
                    await shared_services.set_economy_cooldown(
                        session, guild_id, ctx.author.id, "prison_until",
                        datetime.now(timezone.utc) + timedelta(seconds=spec.prison_duration),
                    )
                    prison_note = f"\nPrison : **{_fmt_duration(spec.prison_duration)}**"
                await session.commit()
                if target_mode:
                    caught = f" en voulant voler {target.display_name}."
                else:
                    caught = "."
                embed = discord.Embed(
                    title=f"{spec.emoji_fail} {spec.title_fail}",
                    description=(
                        f"Tu t'es fait attraper{caught} {loss_desc}.{prison_note}\n"
                        f"Solde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0xE74C3C,
                )

        await ctx.send(embed=embed)

    async def _blanchir(self, ctx: commands.Context, args: tuple[str, ...]) -> None:
        wants_bypass = "bypass" in args
        amount_tokens = [a for a in args if a != "bypass"]
        guild_id = ctx.guild.id

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)

            if not bypass:
                in_prison, rem = await self._is_in_prison(session, guild_id, ctx.author.id)
                if in_prison:
                    await ctx.send(f"🔒 Tu es en prison. Libéré dans **{_fmt_duration(rem)}**.")
                    return

            last = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_blanchir_at")
            if not bypass and last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < BLANCHIR_COOLDOWN:
                    rem = BLANCHIR_COOLDOWN - int(elapsed)
                    await ctx.send(f"⏳ Cooldown `blanchir`. Reviens dans **{_fmt_duration(rem)}**.")
                    return

            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            economy = await session.get(Economy, (guild_id, ctx.author.id))
            wallet = economy.balance if economy else 0

            if amount_tokens:
                try:
                    amount = int(amount_tokens[0])
                except ValueError:
                    await ctx.send("❌ Montant invalide.")
                    return
                if amount <= 0:
                    await ctx.send("❌ Le montant doit être positif.")
                    return
                if amount > wallet:
                    await ctx.send(f"❌ Solde insuffisant (portefeuille : {wallet:,} credits).")
                    return
            else:
                if wallet < 100:
                    await ctx.send("❌ Il te faut au moins **100 credits** en portefeuille pour blanchir.")
                    return
                amount = min(wallet, max(100, wallet // 10))

            await shared_services.set_economy_cooldown(
                session, guild_id, ctx.author.id, "last_blanchir_at", datetime.now(timezone.utc)
            )

            suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
            if random.random() < BLANCHIR_SUCCESS_CHANCE:
                mult = random.uniform(BLANCHIR_MULT_LOW, BLANCHIR_MULT_HIGH)
                profit = int(amount * (mult - 1))
                new_bal = await add_balance(session, guild_id, ctx.author.id, profit)
                await session.commit()
                embed = discord.Embed(
                    title="🧼 Blanchiment réussi !",
                    description=(
                        f"Tu as blanchi **{amount:,} credits** et encaissé **{profit:,} credits** de profit"
                        f" (×{mult:.2f}).\nSolde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0x2ECC71,
                )
            else:
                new_bal = await add_balance(session, guild_id, ctx.author.id, -amount)
                await session.commit()
                embed = discord.Embed(
                    title="🚔 Saisie !",
                    description=(
                        f"Les **{amount:,} credits** blanchis ont été saisis.\n"
                        f"Solde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0xE74C3C,
                )

        await ctx.send(embed=embed)

    @commands.command(name="hack")
    async def hack(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["hack"], args)

    @commands.command(name="braquage")
    async def braquage(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["braquage"], args)

    @commands.command(name="deal")
    async def deal(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["deal"], args)

    @commands.command(name="pirate")
    async def pirate(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["pirate"], args)

    @commands.command(name="fraude")
    async def fraude(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["fraude"], args)

    @commands.command(name="cambriolage")
    async def cambriolage(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["cambriolage"], args)

    @commands.command(name="escroquerie")
    async def escroquerie(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["escroquerie"], args)

    @commands.command(name="chantage")
    async def chantage(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["chantage"], args)

    @commands.command(name="contrebande")
    async def contrebande(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["contrebande"], args)

    @commands.command(name="vol")
    async def vol(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["vol"], args)

    @commands.command(name="falsifier")
    async def falsifier(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["falsifier"], args)

    @commands.command(name="mafia")
    async def mafia(self, ctx: commands.Context, *args: str) -> None:
        await self._mafia_market(ctx, args)

    @commands.command(name="blanchir")
    async def blanchir(self, ctx: commands.Context, *args: str) -> None:
        await self._blanchir(ctx, args)

    @commands.command(name="infiltration")
    async def infiltration(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["infiltration"], args)

    @commands.command(name="hijack")
    async def hijack(self, ctx: commands.Context, *args: str) -> None:
        await self._run_crime(ctx, SPECS["hijack"], args)


async def setup(bot) -> None:
    await bot.add_cog(UnderworldCog(bot))
