import io
from datetime import date, datetime, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from models.badges import Badge, UserBadge
from models.economy import Economy
from models.levels import Level
from services.leaderboard import get_xp_rank
from services.leveling import xp_for_level
from services.profile_card import ProfileCardData, render_profile_card
from services.profile_stats import gather_profile_stats
from services.users import get_or_create_user


class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _today(self) -> date:
        return datetime.now(timezone.utc).date()

    @commands.command(name="profile")
    async def profile(self, ctx: commands.Context, membre: discord.Member | None = None) -> None:
        target = membre or ctx.author
        avatar_bytes = await target.display_avatar.read()
        guild_id = ctx.guild.id

        async with self._session() as session:
            await get_or_create_user(session, guild_id, target.id, target.display_name)
            level_row = await session.get(Level, (guild_id, target.id))
            xp = level_row.xp if level_row is not None else 0
            level = level_row.level if level_row is not None else 0
            prestige = level_row.prestige if level_row is not None else 0

            economy = await session.get(Economy, (guild_id, target.id))
            balance = economy.balance if economy is not None else 0

            badge_result = await session.execute(
                select(Badge.name)
                .join(UserBadge, UserBadge.badge_id == Badge.id)
                .where(UserBadge.guild_id == guild_id, UserBadge.user_id == target.id)
            )
            badge_names = [row[0] for row in badge_result.all()]

            rank = await get_xp_rank(session, guild_id, target.id)
            stats = await gather_profile_stats(session, guild_id, target.id, self._today())
            await session.commit()

        current_level_xp = xp - xp_for_level(level)
        xp_needed = xp_for_level(level + 1) - xp_for_level(level)
        key_count = sum(stats.keys_by_rarity.values())

        card_data = ProfileCardData(
            username=target.display_name,
            level=level,
            current_level_xp=current_level_xp,
            xp_needed_for_next_level=xp_needed,
            rank=rank,
            key_count=key_count,
        )
        card_bytes = render_profile_card(card_data, avatar_bytes)

        quest_lines = [
            f"{'✅' if q.completed else '▫️'} {q.description} ({min(q.progress, q.target_count)}/{q.target_count})"
            for q in stats.quests_today
        ]
        keys_lines = [f"{rarity}: {count}" for rarity, count in stats.keys_by_rarity.items()]

        embed = discord.Embed(title=f"Stats de {target.display_name}")
        embed.add_field(name="Prestige", value=str(prestige), inline=True)
        embed.add_field(name="Solde", value=f"{balance} coins", inline=True)
        embed.add_field(name="Messages envoyés", value=str(stats.total_messages), inline=True)
        embed.add_field(name="Temps vocal (secondes)", value=str(stats.total_voice_seconds), inline=True)
        embed.add_field(name="Badges", value=", ".join(badge_names) or "Aucun", inline=False)
        embed.add_field(name="Quêtes du jour", value="\n".join(quest_lines) or "Aucune", inline=False)
        embed.add_field(name="Clés", value="\n".join(keys_lines) or "Aucune", inline=False)

        file = discord.File(io.BytesIO(card_bytes), filename="profile.png")
        embed.set_image(url="attachment://profile.png")

        await ctx.send(file=file, embed=embed)



    @commands.command(name="effects")
    async def effects(self, ctx: commands.Context) -> None:
        from services.effects import _active_effects as get_effects
        guild_id = ctx.guild.id
        async with self._session() as session:
            all_types = [
                "xp_boost", "coins_boost", "casino_jackpot_chance_boost",
                "casino_insurance", "casino_double_win", "casino_free_bet",
                "streak_protection", "gacha_rate_boost",
            ]
            lines = []
            for etype in all_types:
                effects = await get_effects(session, guild_id, ctx.author.id, etype)
                if effects:
                    labels = {
                        "xp_boost": "⚡ Boost XP",
                        "coins_boost": "💰 Boost Coins",
                        "casino_jackpot_chance_boost": "🎰 Boost Jackpot",
                        "casino_insurance": "🛡️ Assurance Casino",
                        "casino_double_win": "✨ Double Gain",
                        "casino_free_bet": "🎲 Pari Gratuit",
                        "streak_protection": "📅 Protection Série",
                        "gacha_rate_boost": "🌈 Boost Gacha",
                    }
                    label = labels.get(etype, etype)
                    for e in effects:
                        details = []
                        if e.magnitude and e.magnitude != 1.0:
                            details.append(f"x{e.magnitude}")
                        if e.uses_remaining:
                            details.append(f"{e.uses_remaining} usage(s)")
                        if e.expires_at:
                            remaining = e.expires_at - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                            if remaining.total_seconds() > 0:
                                h = int(remaining.total_seconds() // 3600)
                                m = int((remaining.total_seconds() % 3600) // 60)
                                details.append(f"{h}h{m:02d} restant(s)")
                        line = f"{label}"
                        if details:
                            line += f" ({', '.join(details)})"
                        lines.append(line)
            if not lines:
                await ctx.send("✨ Aucun effet actif pour le moment. Ouvre des caisses avec `$key` pour en obtenir !")
            else:
                await ctx.send("**✨ Tes effets actifs :**\n" + "\n".join(lines))

async def setup(bot) -> None:
    await bot.add_cog(ProfileCog(bot))
