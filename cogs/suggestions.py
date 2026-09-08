import json
from dataclasses import dataclass, field
from pathlib import Path

import discord
from discord.ext import commands, tasks

from config.settings import settings
from services.deepseek_client import MAX_CLARIFICATION_QUESTIONS, DeepSeekError, conduct_clarification_turn
from services.mod_log import send_admin_log_embed
from services.suggestion_queue import DONE_DIR, FAILED_DIR, write_suggestion_job

# Garde-fou en dur : seuls ces deux comptes Discord (identité confirmée hors
# bande) peuvent accepter ou refuser une suggestion, quel que soit leur rôle
# sur le serveur. Volontairement non éditable via .config.
SUGGESTION_APPROVER_IDS = {1173059024661532703, 1284946513205657631}

COMMAND_PREFIX_CHARS = ("!", "$", ".", "+")
RESULT_POLL_INTERVAL_SECONDS = 15
RESULT_LOG_TAIL_CHARS = 500


@dataclass
class SuggestionSession:
    requester_id: int
    requester_display: str
    guild_id: int
    channel_id: int
    idea: str
    history: list[tuple[str, str]] = field(default_factory=list)
    pending_question: str | None = None


def build_validation_embed(requester, idea: str) -> discord.Embed:
    embed = discord.Embed(
        title="💡 Nouvelle suggestion",
        description=f"{requester.mention} veut : {idea}",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Demandé par {requester}")
    return embed


def build_validation_result_embed(requester_display: str, idea: str, *, accepted: bool, approver) -> discord.Embed:
    title = "✅ Suggestion acceptée" if accepted else "❌ Suggestion refusée"
    color = discord.Color.green() if accepted else discord.Color.red()
    embed = discord.Embed(title=title, description=idea, color=color)
    embed.add_field(name="Demandé par", value=requester_display, inline=True)
    embed.add_field(name="Décidé par", value=str(approver), inline=True)
    return embed


def build_result_embed(result: dict, *, success: bool) -> discord.Embed:
    if success:
        embed = discord.Embed(
            title="🤖 Fonctionnalité implémentée et déployée",
            description=result.get("idea", ""),
            color=discord.Color.green(),
        )
    else:
        stage = result.get("stage", "inconnue")
        embed = discord.Embed(
            title=f"⚠️ Échec de l'implémentation automatique (étape : {stage})",
            description=result.get("idea", ""),
            color=discord.Color.orange(),
        )
        detail = result.get("test_output") or result.get("claude_output") or result.get("deploy_output") or ""
        if detail:
            embed.add_field(name="Détail (fin du log)", value=f"```{detail[-RESULT_LOG_TAIL_CHARS:]}```", inline=False)
    embed.add_field(name="Demandé par", value=result.get("requester_display", "?"), inline=True)
    return embed


class AcceptRefuseView(discord.ui.View):
    def __init__(
        self,
        cog: "SuggestionsCog",
        requester_id: int,
        requester_display: str,
        idea: str,
        channel_id: int,
        guild_id: int,
    ) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.requester_id = requester_id
        self.requester_display = requester_display
        self.idea = idea
        self.channel_id = channel_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in SUGGESTION_APPROVER_IDS:
            await interaction.response.send_message(
                "Seuls les deux administrateurs désignés peuvent valider les suggestions.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await self.cog.handle_accept(interaction, self)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="❌")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await self.cog.handle_refuse(interaction, self)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.open_requesters: set[int] = set()
        self.active_sessions: dict[int, SuggestionSession] = {}

    async def cog_load(self) -> None:
        self.poll_suggestion_results.start()

    async def cog_unload(self) -> None:
        self.poll_suggestion_results.cancel()

    @tasks.loop(seconds=RESULT_POLL_INTERVAL_SECONDS)
    async def poll_suggestion_results(self) -> None:
        await self._poll_once()

    async def _poll_once(self) -> None:
        for result_dir, success in ((DONE_DIR, True), (FAILED_DIR, False)):
            if not result_dir.exists():
                continue
            for result_path in sorted(result_dir.glob("*.json")):
                await self._report_result(result_path, success)

    async def _report_result(self, result_path: Path, success: bool) -> None:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result_path.unlink(missing_ok=True)
            return

        embed = build_result_embed(result, success=success)
        channel = self.bot.get_channel(result["channel_id"])
        if channel is not None:
            await channel.send(content=f"<@{result['requester_id']}>", embed=embed)
            await send_admin_log_embed(getattr(channel, "guild", None), settings.admin_log_channel_id, embed)

        result_path.unlink(missing_ok=True)

    def _suggestion_channel_id(self) -> int | None:
        return int(settings.suggestion_channel_id) if settings.suggestion_channel_id else None

    def _validation_channel(self, guild):
        if guild is None or not settings.suggestion_validation_channel_id:
            return None
        return guild.get_channel(int(settings.suggestion_validation_channel_id))

    @commands.command(name="suggest")
    async def suggest(self, ctx: commands.Context, *, idea: str) -> None:
        suggestion_channel_id = self._suggestion_channel_id()
        if suggestion_channel_id is None or ctx.channel.id != suggestion_channel_id:
            await ctx.send("❌ Cette commande s'utilise uniquement dans le salon dédié aux suggestions.")
            return

        if not settings.suggestion_validation_channel_id or not settings.deepseek_api_key:
            await ctx.send(
                "⚠️ Le système de suggestions n'est pas encore configuré (salon de validation ou clé IA manquants)."
            )
            return

        validation_channel = self._validation_channel(ctx.guild)
        if validation_channel is None:
            await ctx.send("⚠️ Le salon de validation configuré est introuvable.")
            return

        if ctx.author.id in self.open_requesters:
            await ctx.send("⏳ Tu as déjà une suggestion en cours de traitement, attends qu'elle soit résolue.")
            return

        self.open_requesters.add(ctx.author.id)
        view = AcceptRefuseView(self, ctx.author.id, str(ctx.author), idea, suggestion_channel_id, ctx.guild.id)
        await validation_channel.send(embed=build_validation_embed(ctx.author, idea), view=view)
        await ctx.send("✅ Ta suggestion a été transmise pour validation.")

    async def handle_refuse(self, interaction: discord.Interaction, view: AcceptRefuseView) -> None:
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=build_validation_result_embed(view.requester_display, view.idea, accepted=False, approver=interaction.user),
            view=view,
        )
        self.open_requesters.discard(view.requester_id)

        await send_admin_log_embed(
            interaction.guild,
            settings.admin_log_channel_id,
            build_validation_result_embed(view.requester_display, view.idea, accepted=False, approver=interaction.user),
        )

        channel = interaction.guild.get_channel(view.channel_id) if interaction.guild else None
        if channel is not None:
            await channel.send(f"<@{view.requester_id}> ta suggestion a été refusée par {interaction.user.mention}.")

    async def handle_accept(self, interaction: discord.Interaction, view: AcceptRefuseView) -> None:
        for item in view.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=build_validation_result_embed(view.requester_display, view.idea, accepted=True, approver=interaction.user),
            view=view,
        )

        await send_admin_log_embed(
            interaction.guild,
            settings.admin_log_channel_id,
            build_validation_result_embed(view.requester_display, view.idea, accepted=True, approver=interaction.user),
        )

        channel = interaction.guild.get_channel(view.channel_id) if interaction.guild else None

        session = SuggestionSession(
            requester_id=view.requester_id,
            requester_display=view.requester_display,
            guild_id=view.guild_id,
            channel_id=view.channel_id,
            idea=view.idea,
        )

        try:
            turn = await conduct_clarification_turn(session.idea, session.history, settings.deepseek_api_key)
        except DeepSeekError:
            self.open_requesters.discard(view.requester_id)
            if channel is not None:
                await channel.send(
                    f"<@{view.requester_id}> ⚠️ Erreur lors du lancement de l'entretien avec l'IA, contacte un admin."
                )
            return

        if turn.done:
            await self._finalize_session(channel, session, turn.final_prompt)
            return

        session.pending_question = turn.question
        self.active_sessions[view.requester_id] = session
        if channel is not None:
            await channel.send(f"<@{view.requester_id}> {turn.question}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        session = self.active_sessions.get(message.author.id)
        if session is None or message.channel.id != session.channel_id:
            return
        if message.content.startswith(COMMAND_PREFIX_CHARS):
            return

        prospective_history = session.history + [(session.pending_question, message.content)]
        force_done = len(prospective_history) >= MAX_CLARIFICATION_QUESTIONS

        try:
            turn = await conduct_clarification_turn(
                session.idea, prospective_history, settings.deepseek_api_key, force_done=force_done
            )
        except DeepSeekError:
            await message.channel.send(f"{message.author.mention} ⚠️ Erreur de l'IA, réessaie ta réponse.")
            return

        session.history = prospective_history
        session.pending_question = None

        if turn.done:
            del self.active_sessions[message.author.id]
            await self._finalize_session(message.channel, session, turn.final_prompt)
            return

        session.pending_question = turn.question
        await message.channel.send(f"{message.author.mention} {turn.question}")

    async def _finalize_session(self, channel, session: SuggestionSession, final_prompt: str) -> None:
        self.open_requesters.discard(session.requester_id)
        job_id = write_suggestion_job(
            requester_id=session.requester_id,
            requester_display=session.requester_display,
            guild_id=session.guild_id,
            channel_id=session.channel_id,
            idea=session.idea,
            transcript=session.history,
            final_prompt=final_prompt,
        )
        if channel is not None:
            await channel.send(
                f"<@{session.requester_id}> 🤖 Entretien terminé — ta suggestion a été transmise automatiquement "
                f"pour implémentation (réf. `{job_id[:8]}`)."
            )


async def setup(bot) -> None:
    await bot.add_cog(SuggestionsCog(bot))
