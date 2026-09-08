from datetime import datetime, timezone

import discord
from discord.ext import commands

from services.quests import QuestStatus, get_daily_quests_status

QUEST_COLOR = discord.Color.blurple()


def build_quest_embed(statuses: list[QuestStatus]) -> discord.Embed:
    embed = discord.Embed(title="📜 Quêtes du jour", color=QUEST_COLOR)
    if not statuses:
        embed.description = "Aucune quête configurée."
        return embed
    for quest in statuses:
        icon = "✅" if quest.completed else "▫️"
        rewards = []
        if quest.xp_reward:
            rewards.append(f"{quest.xp_reward} XP")
        if quest.coins_reward:
            rewards.append(f"{quest.coins_reward} coins")
        reward_text = f" — Récompense : {', '.join(rewards)}" if rewards else ""
        progress = min(quest.progress, quest.target_count)
        embed.add_field(
            name=f"{icon} {quest.description}",
            value=f"{progress}/{quest.target_count}{reward_text}",
            inline=False,
        )
    return embed


class QuestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _today(self):
        return datetime.now(timezone.utc).date()

    @commands.command(name="quest")
    async def quest(self, ctx: commands.Context) -> None:
        async with self._session() as session:
            statuses = await get_daily_quests_status(session, ctx.guild.id, ctx.author.id, self._today())
        await ctx.send(embed=build_quest_embed(statuses))


async def setup(bot) -> None:
    await bot.add_cog(QuestCog(bot))
