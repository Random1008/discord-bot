"""Procès : tribunal RP avec un juge IA (DeepSeek) qui anime les débats.

Deux façons d'ouvrir un procès :
1. Panneau `.setup proces` (admin) : embed personnalisable + bouton « Déposer une
   plainte » posté dans le salon configuré via `.config` (proces_channel_id).
   Un membre clique, remplit la raison, choisit le suspect dans une liste
   déroulante, et le procès s'ouvre dans un fil de discussion.
2. `$proces @joueur2 [accusation] [bypass]` : ouverture directe. « bypass » en fin
   de commande (admin uniquement) affiche le dédommagement sans débiter et ignore
   le cooldown.

Pendant le procès, l'accusateur, l'accusé et leurs complices (`!complice`)
débattent dans le fil. Le juge IA interagit (questions, relances) ; quand il
estime avoir assez d'éléments, il prononce lui-même la clôture (parole absolue :
aucun vote des participants) et rend immédiatement le verdict final.
`.proces end` (admin, tapé dans le fil du procès) fait de même sur demande :
le juge rend son jugement sur la base des éléments déjà présentés.
Coupable = 100 credits × nombre de messages versés à l'accusateur.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config.settings import settings
from services.admin_permission import can_bypass
from services.deepseek_client import DeepSeekError, judge_trial, judge_turn
from services.economy import add_balance
from services.proces_config import (
    DEFAULT_PROCES_CONFIG_PATH,
    get_proces_reglement,
    panel_message_ids,
)
from services.users import get_or_create_user
from shared.db import services as shared_services

logger = logging.getLogger(__name__)

PROCES_COOLDOWN = 3600
PROCES_CREDITS_PER_MESSAGE = 100
PROCES_MAX_MESSAGES = 200
PROCES_MAX_IMAGES = 25
JUDGE_NAME = "⚖️ Le Juge"
MAX_SELECT_OPTIONS = 25


def _fmt_duration(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def _judge_embed(text: str) -> discord.Embed:
    return discord.Embed(title=JUDGE_NAME, description=text, color=0xF1C40F)


@dataclass
class Trial:
    guild_id: int
    thread_id: int
    accuser_id: int
    accused_id: int
    accusation: str
    bypass: bool = False
    participants: dict[int, str] = field(default_factory=dict)  # user_id -> display_name
    complices: list[int] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)  # (nom, contenu)
    media: list[tuple[str, str]] = field(default_factory=list)  # (nom, url_image) chronologique
    participant_messages: int = 0
    closure_proposed: bool = False  # le juge a prononcé la clôture (débats gelés)
    closed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def name_of(self, user_id: int) -> str:
        return self.participants.get(user_id, str(user_id))

    def participant_ids(self) -> list[int]:
        ids = [self.accuser_id, self.accused_id]
        ids += list(self.complices)
        return ids

    def is_participant(self, user_id: int) -> bool:
        return user_id in self.participant_ids()


def _transcript(trial: Trial, include_judge: bool) -> str:
    lines = []
    for name, content in trial.history[-PROCES_MAX_MESSAGES:]:
        if not include_judge and name == JUDGE_NAME:
            continue
        lines.append(f"{name}: {content}")
    return "\n".join(lines)


def _extract_image_urls(message: discord.Message) -> list[str]:
    """Récupère les URL des images/GIFs d'un message (pièces jointes + embeds)."""
    urls: list[str] = []
    for att in message.attachments:
        ct = att.content_type or ""
        if ct.startswith("image/"):
            urls.append(att.url)
    for embed in message.embeds:
        etype = embed.type or ""
        if etype in ("image", "gifv"):
            candidate = None
            if embed.thumbnail and embed.thumbnail.url:
                candidate = embed.thumbnail.url
            elif embed.image and embed.image.url:
                candidate = embed.image.url
            elif embed.url:
                candidate = embed.url
            if candidate:
                urls.append(candidate)
        elif etype == "rich":
            if embed.image and embed.image.url:
                urls.append(embed.image.url)
    return urls


def _member_options(guild: discord.Guild, excluded: set[int]) -> list[discord.SelectOption]:
    options = []
    for member in guild.members:
        if member.bot or member.id in excluded:
            continue
        options.append(discord.SelectOption(label=member.display_name[:100], value=str(member.id)))
        if len(options) >= MAX_SELECT_OPTIONS:
            break
    return options


async def _resolve_member(guild: discord.Guild, cible: str) -> discord.Member | None:
    """Résout une cible de `!complice @membre` / `!complice 123456` : mention,
    ID brut, ou nom d'utilisateur / display name (fallback)."""
    raw = cible.strip()
    if raw.startswith("<@") and raw.endswith(">"):
        raw = raw[2:-1].lstrip("!")
    try:
        user_id = int(raw)
    except ValueError:
        name = cible.strip().lower()
        return discord.utils.find(
            lambda m: not m.bot
            and (m.name.lower() == name or (m.display_name or "").lower() == name),
            guild.members,
        )
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None
    return member


class TrialVerdictView(discord.ui.View):
    """Bouton de repli sur le message d'ouverture : l'accusateur peut forcer le verdict."""

    def __init__(self, cog: "ProcesCog", trial: Trial) -> None:
        super().__init__(timeout=21600)
        self.cog = cog
        self.trial = trial

    @discord.ui.button(label="Rendre le verdict", style=discord.ButtonStyle.primary, emoji="⚖️")
    async def verdict_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.trial.accuser_id:
            await interaction.response.send_message("❌ Seul l'accusateur peut rendre le verdict.", ephemeral=True)
            return
        if self.trial.closed:
            await interaction.response.send_message("❌ Le procès est déjà terminé.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog._render_final_verdict(self.trial, interaction.channel)



class PlainteModal(discord.ui.Modal, title="Déposer une plainte"):
    def __init__(self, cog: "ProcesCog", accuser: discord.Member) -> None:
        super().__init__()
        self.cog = cog
        self.accuser = accuser
        self.raison_input = discord.ui.TextInput(
            label="Raison (décris les faits)",
            style=discord.TextStyle.paragraph,
            placeholder="Ex. : il a abusé de son pouvoir…",
            required=True,
            max_length=1000,
        )
        self.add_item(self.raison_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raison = self.raison_input.value.strip()
        if not raison:
            await interaction.response.send_message("❌ La raison est obligatoire.", ephemeral=True)
            return
        options = _member_options(interaction.guild, excluded={self.accuser.id})
        if not options:
            await interaction.response.send_message("❌ Aucun suspect disponible.", ephemeral=True)
            return
        view = SuspectSelectView(self.cog, self.accuser, raison, options)
        await interaction.response.send_message(
            "Choisis le **suspect** dans la liste ci-dessous :", view=view, ephemeral=True
        )


class SuspectSelect(discord.ui.Select):
    def __init__(
        self, cog: "ProcesCog", accuser: discord.Member, raison: str, options: list[discord.SelectOption]
    ) -> None:
        super().__init__(placeholder="Choisis le suspect…", options=options, min_values=1, max_values=1)
        self.cog = cog
        self.accuser = accuser
        self.raison = raison

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.accuser.id:
            await interaction.response.send_message("Cette liste n'est pas pour toi.", ephemeral=True)
            return
        accused = interaction.guild.get_member(int(self.values[0]))
        if accused is None or accused.bot:
            await interaction.response.send_message("❌ Suspect invalide.", ephemeral=True)
            return
        if accused.id == self.accuser.id:
            await interaction.response.send_message("❌ Tu ne peux pas t'accuser toi-même.", ephemeral=True)
            return

        guild_id = interaction.guild_id
        async with self.cog._session() as session:
            last = await shared_services.get_economy_cooldown(
                session, guild_id, self.accuser.id, "last_proces_at"
            )
            if last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < PROCES_COOLDOWN:
                    rem = PROCES_COOLDOWN - int(elapsed)
                    await interaction.response.send_message(
                        f"⏳ Cooldown `proces`. Reviens dans **{_fmt_duration(rem)}**.", ephemeral=True
                    )
                    return
            await shared_services.set_economy_cooldown(
                session, guild_id, self.accuser.id, "last_proces_at", datetime.now(timezone.utc)
            )
            await session.commit()

        try:
            thread = await interaction.channel.create_thread(
                name=f"⚖️ Procès : {self.accuser.display_name} contre {accused.display_name}",
                type=discord.ChannelType.public_thread,
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Impossible de créer le fil (permission requise).", ephemeral=True
            )
            return

        await self.cog._start_trial(interaction.guild, thread, self.accuser, accused, self.raison, bypass=False)
        await interaction.response.send_message(f"⚖️ Procès ouvert dans {thread.mention}.", ephemeral=True)


class SuspectSelectView(discord.ui.View):
    def __init__(
        self, cog: "ProcesCog", accuser: discord.Member, raison: str, options: list[discord.SelectOption]
    ) -> None:
        super().__init__(timeout=840)
        self.add_item(SuspectSelect(cog, accuser, raison, options))


class ProcesPanelView(discord.ui.View):
    """Panneau posté par `.setup proces` : bouton « Déposer une plainte ».

    timeout=None + custom_id fixe = vue persistante : elle est ré-attachée à
    chaque démarrage du bot via `bot.add_view` pour les message_id enregistrés
    dans proces_config.json, donc le bouton survit aussi aux redémarrages.
    """

    def __init__(self, cog: "ProcesCog | None") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Déposer une plainte", style=discord.ButtonStyle.primary, emoji="⚖️", custom_id="proces:deposer_plainte"
    )
    async def plainte_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.cog is None or not settings.deepseek_api_key:
            await interaction.response.send_message(
                "❌ Les procès ne sont pas encore configurés (clé IA manquante).", ephemeral=True
            )
            return
        await interaction.response.send_modal(PlainteModal(self.cog, interaction.user))


class CompliceSelect(discord.ui.Select):
    def __init__(
        self, cog: "ProcesCog", trial: Trial, author_id: int, options: list[discord.SelectOption]
    ) -> None:
        super().__init__(placeholder="Choisis un complice…", options=options, min_values=1, max_values=1)
        self.cog = cog
        self.trial = trial
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette liste n'est pas pour toi.", ephemeral=True)
            return
        member = interaction.guild.get_member(int(self.values[0]))
        if member is None or member.bot:
            await interaction.response.send_message("❌ Membre invalide.", ephemeral=True)
            return
        trial = self.trial
        if trial.closed:
            await interaction.response.send_message("❌ Le procès est terminé.", ephemeral=True)
            return
        if member.id in trial.participant_ids():
            await interaction.response.send_message("❌ Cette personne est déjà dans le procès.", ephemeral=True)
            return
        trial.complices.append(member.id)
        trial.participants[member.id] = member.display_name
        await interaction.response.send_message(
            f"✅ {member.mention} est maintenant complice et peut participer au débat."
        )


class CompliceSelectView(discord.ui.View):
    def __init__(
        self, cog: "ProcesCog", trial: Trial, author_id: int, options: list[discord.SelectOption]
    ) -> None:
        super().__init__(timeout=840)
        self.add_item(CompliceSelect(cog, trial, author_id, options))


class ProcesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trials: dict[int, Trial] = {}
        self._panels_reattached = False

    def _session(self):
        return self.bot.session_factory()

    def _current_reglement(self) -> str:
        """Règlement du serveur à appliquer par le juge (lu à chaque audience :
        une mise à jour via `.setup proces` est prise en compte immédiatement)."""
        try:
            return get_proces_reglement(DEFAULT_PROCES_CONFIG_PATH)
        except Exception:
            return ""

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Ré-attache les panneaux « Déposer une plainte » enregistrés dans
        proces_config.json : sans ça, les boutons (pourtant persistants via
        custom_id) ne répondraient plus après un redémarrage du bot."""
        if self._panels_reattached:
            return
        self._panels_reattached = True
        for message_id in panel_message_ids(DEFAULT_PROCES_CONFIG_PATH):
            try:
                self.bot.add_view(ProcesPanelView(self), message_id=message_id)
                logger.info("Panneau des procès ré-attaché (message %s)", message_id)
            except Exception as exc:
                logger.warning("Ré-attache du panneau %s impossible : %s", message_id, exc)

    async def _start_trial(
        self,
        guild: discord.Guild,
        thread: discord.Thread,
        accuser: discord.Member,
        accused: discord.Member,
        accusation: str,
        *,
        bypass: bool = False,
    ) -> Trial:
        trial = Trial(
            guild_id=guild.id,
            thread_id=thread.id,
            accuser_id=accuser.id,
            accused_id=accused.id,
            accusation=accusation,
            bypass=bypass,
            participants={accuser.id: accuser.display_name, accused.id: accused.display_name},
        )
        self.trials[thread.id] = trial

        embed = discord.Embed(
            title="⚖️ Procès",
            description=(
                f"**Accusateur :** {accuser.mention}\n"
                f"**Accusé :** {accused.mention}\n"
                f"**Accusation :** {accusation}\n\n"
                "Débattez ici. Le juge IA anime l'audience ; sa parole est absolue : quand il "
                "estime avoir assez d'éléments, il prononce la clôture et rend la sentence.\n"
                "`!complice` pour ajouter un complice au débat."
            ),
            color=0x5865F2,
        )
        view = TrialVerdictView(self, trial)
        await thread.send(content=f"{accuser.mention} {accused.mention}", embed=embed, view=view)

        await self._judge_opening(trial, thread)
        return trial

    async def _judge_opening(self, trial: Trial, thread: discord.Thread) -> None:
        if not settings.deepseek_api_key:
            return
        try:
            result = await judge_turn(
                trial.accusation,
                "",
                settings.deepseek_api_key,
                opening=True,
                reglement=self._current_reglement(),
            )
        except Exception as exc:
            logger.warning("Juge IA indisponible à l'ouverture du procès : %s", exc)
            await thread.send(
                embed=discord.Embed(description="⚖️ Le juge est momentanément indisponible.", color=0x95A5A6)
            )
            return
        text = result["reponse"]
        if not text:
            return
        trial.history.append((JUDGE_NAME, text))
        await thread.send(embed=_judge_embed(text))
        if result["proposer_cloture"]:
            # Parole absolue du juge : clôture immédiate + sentence, sans vote des parties.
            trial.closure_proposed = True
            await self._render_final_verdict(trial, thread)

    async def _judge_speaks(self, trial: Trial, thread: discord.Thread) -> None:
        if not settings.deepseek_api_key:
            return
        try:
            result = await judge_turn(
                trial.accusation,
                _transcript(trial, include_judge=True),
                settings.deepseek_api_key,
                images=trial.media[-PROCES_MAX_IMAGES:],
                reglement=self._current_reglement(),
            )
        except Exception as exc:
            logger.warning("Juge IA indisponible pendant le procès : %s", exc)
            return
        text = result["reponse"]
        if not text:
            return
        trial.history.append((JUDGE_NAME, text))
        await thread.send(embed=_judge_embed(text))
        if result["proposer_cloture"]:
            # Parole absolue du juge : il prononce la clôture (débats gelés) ;
            # le verdict est rendu juste après par on_message, hors du verrou.
            trial.closure_proposed = True

    async def _render_final_verdict(self, trial: Trial, channel: discord.abc.Messageable) -> None:
        async with trial.lock:
            if trial.closed:
                return
            trial.closed = True

        transcript = _transcript(trial, include_judge=False)
        amount = trial.participant_messages * PROCES_CREDITS_PER_MESSAGE

        if not settings.deepseek_api_key:
            await channel.send("❌ Clé IA non configurée — verdict impossible.")
            return

        try:
            verdict = await judge_trial(
                trial.accusation,
                transcript,
                settings.deepseek_api_key,
                images=trial.media[-PROCES_MAX_IMAGES:],
                reglement=self._current_reglement(),
            )
        except Exception as exc:
            await channel.send(f"❌ Le juge IA a rencontré une erreur : {exc}")
            return

        outcome = verdict.get("verdict", "inconclusif")
        reason = str(verdict.get("raison", "")).strip()
        accused_name = trial.name_of(trial.accused_id)
        accuser_name = trial.name_of(trial.accuser_id)

        if outcome == "coupable":
            if trial.bypass:
                embed = discord.Embed(
                    title="⚖️ Verdict : coupable (bypass)",
                    description=(
                        f"**{accused_name}** est reconnu **coupable**.\n"
                        f"{reason}\n\n"
                        f"Dédommagement (bypass — non débité) : **{amount:,} credits** "
                        f"({trial.participant_messages} message(s) × {PROCES_CREDITS_PER_MESSAGE})."
                    ),
                    color=0xE74C3C,
                )
            else:
                async with self._session() as session:
                    await get_or_create_user(session, trial.guild_id, trial.accused_id, accused_name)
                    await get_or_create_user(session, trial.guild_id, trial.accuser_id, accuser_name)
                    # Sentence souveraine : le condamné peut être endetté sans
                    # plancher (solde négatif illimité), même sans de quoi payer.
                    await add_balance(session, trial.guild_id, trial.accused_id, -amount, floor=None)
                    await add_balance(session, trial.guild_id, trial.accuser_id, amount)
                    await session.commit()
                embed = discord.Embed(
                    title="⚖️ Verdict : coupable",
                    description=(
                        f"**{accused_name}** est reconnu **coupable**.\n"
                        f"{reason}\n\n"
                        f"Dédommagement : **{amount:,} credits** "
                        f"({trial.participant_messages} message(s) × {PROCES_CREDITS_PER_MESSAGE}) versés à l'accusateur."
                    ),
                    color=0xE74C3C,
                )
        elif outcome == "innocent":
            embed = discord.Embed(
                title="⚖️ Verdict : innocent",
                description=f"**{accused_name}** est **innocent**.\n{reason}",
                color=0x2ECC71,
            )
        else:
            embed = discord.Embed(
                title="⚖️ Verdict : inconclusif",
                description=f"Preuves insuffisantes pour trancher.\n{reason}",
                color=0xF1C40F,
            )

        await channel.send(embed=embed)
        self.trials.pop(trial.thread_id, None)

    @commands.group(name="proces", invoke_without_command=True)
    async def proces(self, ctx: commands.Context, accused: discord.Member, *, accusation: str | None = None) -> None:
        """Ouvre un procès (`$proces @membre [accusation]`). La sous-commande
        admin `.proces end` (tapée dans le fil) fait juger immédiatement."""
        if accused.bot or accused.id == ctx.author.id:
            await ctx.send("❌ Cible invalide.")
            return

        if not settings.deepseek_api_key:
            await ctx.send("❌ La clé IA n'est pas configurée (admin : `.config` → Intégrations IA).")
            return

        accusation_text = (accusation or "").strip()
        words = accusation_text.split()
        # « bypass » est un mot-clé placé à la fin : `$proces @joueur2 bypass`.
        wants_bypass = bool(words) and words[-1].lower() == "bypass"
        if wants_bypass:
            words = words[:-1]
        accusation_text = " ".join(words).strip() or "Accusation non précisée."

        guild_id = ctx.guild.id
        bypass = False
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            if not bypass:
                last = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_proces_at")
                if last is not None:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                    if elapsed < PROCES_COOLDOWN:
                        rem = PROCES_COOLDOWN - int(elapsed)
                        await ctx.send(f"⏳ Cooldown `proces`. Reviens dans **{_fmt_duration(rem)}**.")
                        return
            await shared_services.set_economy_cooldown(
                session, guild_id, ctx.author.id, "last_proces_at", datetime.now(timezone.utc)
            )
            await session.commit()

        try:
            thread = await ctx.message.create_thread(
                name=f"⚖️ Procès : {ctx.author.display_name} contre {accused.display_name}"
            )
        except discord.HTTPException:
            await ctx.send("❌ Impossible de créer le fil (permission « Gérer les fils » requise).")
            return

        await self._start_trial(ctx.guild, thread, ctx.author, accused, accusation_text, bypass=bypass)
        await ctx.send(f"⚖️ Procès ouvert contre {accused.mention} dans {thread.mention}.")

    @proces.command(name="end")
    @commands.has_permissions(administrator=True)
    async def proces_end(self, ctx: commands.Context) -> None:
        """`.proces end` (admin, dans le fil du procès) : clôt l'audience et fait
        rendre au juge son jugement immédiat, sur les éléments déjà présentés."""
        trial = self.trials.get(ctx.channel.id)
        if trial is None:
            await ctx.send(
                "❌ Aucun procès en cours dans ce salon. Tape `.proces end` dans le fil du procès."
            )
            return
        if trial.closed:
            await ctx.send("⚖️ Le procès est déjà terminé.")
            return
        if not settings.deepseek_api_key:
            await ctx.send("❌ Clé IA non configurée — jugement impossible.")
            return
        # Le juge clôt l'audience et juge sur l'existant (parole absolue).
        trial.closure_proposed = True
        await ctx.send(
            embed=_judge_embed(
                "L'audience est close. Je rends mon jugement sur la base des éléments déjà présentés."
            )
        )
        await self._render_final_verdict(trial, ctx.channel)

    @commands.command(name="complice")
    async def complice(self, ctx: commands.Context, cible: str | None = None) -> None:
        trial = self.trials.get(ctx.channel.id)
        if trial is None or trial.closed:
            await ctx.send("❌ `!complice` est disponible uniquement dans un procès en cours.")
            return
        if not trial.is_participant(ctx.author.id):
            await ctx.send("❌ Seuls les parties du procès peuvent ajouter un complice.")
            return

        # Sans argument : liste déroulante (comportement historique).
        if cible is None:
            options = _member_options(ctx.guild, excluded=set(trial.participant_ids()))
            if not options:
                await ctx.send("❌ Aucun membre disponible à ajouter comme complice.")
                return
            view = CompliceSelectView(self, trial, author_id=ctx.author.id, options=options)
            await ctx.send("Choisis le **complice** à ajouter au débat :", view=view)
            return

        # Avec argument : ajout direct par mention (@pseudo), ID ou nom.
        member = await _resolve_member(ctx.guild, cible)
        if member is None or member.bot:
            await ctx.send(
                "❌ Membre introuvable. Mentionne le membre (`@pseudo`) ou donne son ID "
                "(ou lance `!complice` sans argument pour la liste déroulante)."
            )
            return
        if member.id in trial.participant_ids():
            await ctx.send("❌ Cette personne est déjà dans le procès.")
            return
        trial.complices.append(member.id)
        trial.participants[member.id] = member.display_name
        await ctx.send(f"✅ {member.mention} est maintenant complice et peut participer au débat.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        trial = self.trials.get(message.channel.id)
        if trial is None or trial.closed or trial.closure_proposed:
            return
        if not trial.is_participant(message.author.id):
            return
        content = message.content
        image_urls = _extract_image_urls(message)
        if not content and not image_urls:
            return
        name = trial.name_of(message.author.id)
        if content:
            trial.history.append((name, content))
        for url in image_urls:
            trial.history.append((name, f"[🖼️ image jointe : {url}]"))
            trial.media.append((name, url))
        trial.participant_messages += 1
        async with trial.lock:
            async with message.channel.typing():
                await self._judge_speaks(trial, message.channel)
        # Clôture prononcée par le juge : verdict rendu hors du verrou
        # (_render_final_verdict ré-acquiert trial.lock).
        if trial.closure_proposed and not trial.closed:
            await self._render_final_verdict(trial, message.channel)


async def setup(bot) -> None:
    await bot.add_cog(ProcesCog(bot))
