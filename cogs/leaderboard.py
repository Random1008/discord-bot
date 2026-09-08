import logging
from typing import Literal

import discord
from discord.ext import commands

from services.leaderboard import (
    get_coins_leaderboard,
    get_message_leaderboard,
    get_voice_leaderboard,
    get_xp_leaderboard,
)

logger = logging.getLogger(__name__)

LEADERBOARD_FETCHERS = {
    "xp": get_xp_leaderboard,
    "messages": get_message_leaderboard,
    "vocal": get_voice_leaderboard,
    "coins": get_coins_leaderboard,
}

LEADERBOARD_LABELS = {
    "xp": "XP",
    "messages": "Messages",
    "vocal": "Temps vocal (secondes)",
    "coins": "Coins",
}

LEADERBOARD_EMOJIS = {
    "xp": "✨",
    "messages": "💬",
    "vocal": "🎙️",
    "coins": "💰",
}

RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

LEADERBOARD_COLOR = 0xF1C40F


def build_leaderboard_embed(type: str, entries: list) -> discord.Embed:
    label = LEADERBOARD_LABELS[type]
    embed = discord.Embed(
        title=f"🏆 Classement {LEADERBOARD_EMOJIS[type]} {label}",
        color=LEADERBOARD_COLOR,
    )
    if not entries:
        embed.description = "Aucune donnée pour ce classement."
    else:
        embed.description = "\n".join(
            f"{RANK_MEDALS.get(rank, f'`#{rank}`')} **{entry.username}** — {entry.score} {label}"
            for rank, entry in enumerate(entries, start=1)
        )
    embed.set_footer(text="Classement calculé en temps réel à chaque exécution de la commande.")
    return embed


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    @commands.command(name="leaderboard")
    async def leaderboard(
        self, ctx: commands.Context, type: Literal["xp", "messages", "vocal", "coins"] = "xp"
    ) -> None:
        fetcher = LEADERBOARD_FETCHERS[type]
        async with self._session() as session:
            entries = await fetcher(session, ctx.guild.id, limit=10)

        await ctx.send(embed=build_leaderboard_embed(type, entries))

        # Mise à jour immédiate des rôles de classement : chaque exécution de
        # `!leaderboard` recalcule et réattribue les rôles (Roi du Chat, Riche,
        # Top 10…), sans attendre le passage hebdomadaire.
        if ctx.guild is not None:
            classement = self.bot.get_cog("ClassementRolesCog")
            if classement is not None:
                try:
                    await classement.refresh_roles(ctx.guild)
                except Exception:
                    logger.exception("Échec de la mise à jour des rôles de classement après !leaderboard")


async def setup(bot) -> None:
    await bot.add_cog(LeaderboardCog(bot))
