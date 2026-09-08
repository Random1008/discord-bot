from datetime import date, datetime, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from cogs._xp_common import award_xp
from config.settings import settings
from models.stats import MessageStat
from services.channel_tracker import DailyChannelTracker
from services.economy import add_balance
from services.leveling import subtract_xp
from services.mod_log import send_admin_log_embed
from services.no_xp_channels import is_no_xp_channel
from services.quests import increment_quest_progress
from services.spam_guard import SPAM_MUTE_DURATION_SECONDS, MessageSpamGuard
from services.xp import EVENT_PARTICIPATION_XP, roll_message_xp

SPAM_LOG_COLOR = discord.Color.red()


def build_spam_mute_embed(member, channel, clawback_amount: int = 0) -> discord.Embed:
    minutes = int(SPAM_MUTE_DURATION_SECONDS // 60)
    embed = discord.Embed(
        title="🚫 Anti-spam XP déclenché",
        description=f"{member.mention} a envoyé trop de messages en rafale (5 messages en moins de 5 secondes).",
        color=SPAM_LOG_COLOR,
    )
    embed.add_field(name="Utilisateur", value=f"{member.mention} ({member})", inline=True)
    embed.add_field(name="Salon", value=channel.mention, inline=True)
    sanction = f"Gain d'XP coupé pendant {minutes} minutes"
    if clawback_amount > 0:
        sanction += f"\n**{clawback_amount} XP** retirés (équivalent des 10 derniers messages ayant rapporté de l'XP)"
    embed.add_field(name="Sanction", value=sanction, inline=False)
    return embed


class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._channel_tracker = DailyChannelTracker()
        self.spam_guard = MessageSpamGuard()

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    def _today(self) -> date:
        return datetime.now(timezone.utc).date()

    async def _apply_quest_progress(self, session, message, quest_key: str, amount: int) -> None:
        guild_id = message.guild.id
        result = await increment_quest_progress(session, guild_id, message.author.id, quest_key, amount, self._today())
        if result is None:
            return
        if result.just_completed:
            await award_xp(
                session,
                message.guild,
                lambda: self._announcement_channel(message.guild),
                message.author,
                result.quest.xp_reward,
            )
            await add_balance(session, guild_id, message.author.id, result.quest.coins_reward)
        # Commit unconditionally, not just on completion: increment_quest_progress only
        # flushes. Without an explicit commit here, an in-progress (not-yet-completed)
        # increment would be rolled back when this method's caller's `async with
        # self._session()` block closes the session — flush() alone does not persist
        # across a session close in production (AsyncSessionLocal creates a fresh
        # session per call, unlike this file's test fake which never actually closes).
        await session.commit()

    async def _record_message_stat(self, session, message) -> None:
        today = self._today()
        guild_id = message.guild.id
        result = await session.execute(
            select(MessageStat).where(
                MessageStat.guild_id == guild_id,
                MessageStat.user_id == message.author.id,
                MessageStat.date == today,
            )
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = MessageStat(guild_id=guild_id, user_id=message.author.id, date=today, count=0)
            session.add(stat)
        stat.count += 1
        await session.commit()

    @commands.Cog.listener()
    async def on_message(self, message) -> None:
        if message.author.bot:
            return

        guild_id = message.guild.id
        amount = roll_message_xp()
        should_award_xp, spam_mute_triggered = self.spam_guard.record_message(message.author.id)
        clawback_amount = 0
        async with self._session() as session:
            if should_award_xp and await is_no_xp_channel(session, guild_id, message.channel.id):
                should_award_xp = False
            if should_award_xp:
                await award_xp(
                    session,
                    message.guild,
                    lambda: self._announcement_channel(message.guild),
                    message.author,
                    amount,
                )
                self.spam_guard.record_awarded_xp(message.author.id, amount)
            await self._apply_quest_progress(session, message, "messages_25", 1)

            is_new_channel = self._channel_tracker.record_channel(
                message.author.id, message.channel.id, self._today()
            )
            if is_new_channel:
                await self._apply_quest_progress(session, message, "channels_3", 1)

            await self._record_message_stat(session, message)

            if spam_mute_triggered:
                clawback_amount = self.spam_guard.pop_clawback_amount(message.author.id)
                if clawback_amount > 0:
                    await subtract_xp(session, guild_id, message.author.id, clawback_amount)
                    await session.commit()

        if spam_mute_triggered:
            await send_admin_log_embed(
                message.guild,
                settings.admin_log_channel_id,
                build_spam_mute_embed(message.author, message.channel, clawback_amount),
            )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user) -> None:
        message = reaction.message
        if user.bot or user.id == message.author.id or message.author.bot:
            return

        async with self._session() as session:
            await award_xp(
                session,
                message.guild,
                lambda: self._announcement_channel(message.guild),
                message.author,
                2,
            )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user) -> None:
        message = reaction.message
        if user.bot or user.id == message.author.id or message.author.bot:
            return

        async with self._session() as session:
            await subtract_xp(session, message.guild.id, message.author.id, 2)
            await session.commit()

    @commands.command(name="event-participation")
    @commands.has_permissions(administrator=True)
    async def event_participation(self, ctx: commands.Context, member: discord.Member) -> None:
        async with self._session() as session:
            await award_xp(
                session,
                ctx.guild,
                lambda: self._announcement_channel(ctx.guild),
                member,
                EVENT_PARTICIPATION_XP,
                bypass_alt_guard=True,
            )
        await ctx.send(
            f"{member.display_name} a reçu le bonus de participation à l'événement (+{EVENT_PARTICIPATION_XP} XP)."
        )


async def setup(bot) -> None:
    await bot.add_cog(LevelingCog(bot))
