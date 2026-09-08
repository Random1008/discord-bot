from datetime import date, datetime, timezone

from discord.ext import commands, tasks
from sqlalchemy import select

from cogs._xp_common import award_xp
from config.settings import settings
from models.stats import VoiceStat
from services.economy import add_balance
from services.no_xp_channels import add_no_xp_channel, is_no_xp_channel, list_no_xp_channels, remove_no_xp_channel
from services.quests import increment_quest_progress
from services.voice_tracker import VoiceTracker
from services.xp import voice_xp_for_seconds

VOICE_SYNC_INTERVAL_SECONDS = 90


def _is_inactive(voice_state) -> bool:
    return voice_state is None or bool(voice_state.self_mute or voice_state.self_deaf)


class VoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker = VoiceTracker()

    async def cog_load(self) -> None:
        self.sync_voice_activity.start()

    async def cog_unload(self) -> None:
        self.sync_voice_activity.cancel()

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    def _today(self) -> date:
        return datetime.now(timezone.utc).date()

    async def _record_voice_stat(self, session, guild_id: int, member_id: int, seconds: int) -> None:
        today = self._today()
        result = await session.execute(
            select(VoiceStat).where(
                VoiceStat.guild_id == guild_id, VoiceStat.user_id == member_id, VoiceStat.date == today
            )
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = VoiceStat(guild_id=guild_id, user_id=member_id, date=today, seconds=0)
            session.add(stat)
        stat.seconds += seconds
        await session.commit()

    async def _process_voice_tick(self, session, guild, member, voice_state) -> None:
        guild_id = guild.id
        channel = voice_state.channel if voice_state is not None else None

        channel_id = channel.id if channel is not None else None
        if channel_id is not None and await is_no_xp_channel(session, guild_id, channel_id):
            channel_id = None

        human_count = 0
        if channel is not None and channel_id is not None:
            human_count = sum(1 for m in channel.members if not m.bot and not _is_inactive(m.voice))

        effective_channel_id = None if _is_inactive(voice_state) else channel_id
        payable_seconds = self.tracker.update_channel(member.id, effective_channel_id, human_count)
        if payable_seconds <= 0:
            return

        amount = voice_xp_for_seconds(payable_seconds)
        await award_xp(session, guild, lambda: self._announcement_channel(guild), member, amount)

        payable_minutes = payable_seconds // 60
        if payable_minutes > 0:
            result = await increment_quest_progress(
                session, guild_id, member.id, "voice_60min", payable_minutes, self._today()
            )
            if result is not None:
                if result.just_completed:
                    await award_xp(
                        session, guild, lambda: self._announcement_channel(guild), member, result.quest.xp_reward
                    )
                    await add_balance(session, guild_id, member.id, result.quest.coins_reward)
                # Commit unconditionally, not just on completion — see the equivalent
                # note in cogs/leveling.py's _apply_quest_progress: increment_quest_progress
                # only flushes, and this session closes at the end of this `async with`
                # block, which would roll back an uncommitted in-progress increment.
                await session.commit()

        await self._record_voice_stat(session, guild_id, member.id, payable_seconds)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if member.bot:
            return

        async with self._session() as session:
            await self._process_voice_tick(session, member.guild, member, after)

    @tasks.loop(seconds=VOICE_SYNC_INTERVAL_SECONDS)
    async def sync_voice_activity(self) -> None:
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                members = [m for m in channel.members if not m.bot]
                if not members:
                    continue
                async with self._session() as session:
                    for member in members:
                        await self._process_voice_tick(session, guild, member, member.voice)

    @sync_voice_activity.before_loop
    async def _before_sync_voice_activity(self) -> None:
        await self.bot.wait_until_ready()

    @commands.command(name="unxp")
    @commands.has_permissions(administrator=True)
    async def unxp_channel(self, ctx: commands.Context, channel_ref: str) -> None:
        guild_id = ctx.guild.id
        if channel_ref == "list":
            async with self._session() as session:
                channel_ids = await list_no_xp_channels(session, guild_id)
            if not channel_ids:
                await ctx.send("Aucun salon exclu de l'XP vocal.")
                return
            lines = "\n".join(f"- <#{channel_id}>" for channel_id in channel_ids)
            await ctx.send(f"Salons exclus de l'XP vocal :\n{lines}")
            return

        try:
            channel_id = int(channel_ref)
        except ValueError:
            await ctx.send(f"Usage : `{ctx.prefix}unxp [id du salon]` ou `{ctx.prefix}unxp list`")
            return

        async with self._session() as session:
            already_excluded = await add_no_xp_channel(session, guild_id, channel_id)
            await session.commit()

        if already_excluded:
            await ctx.send(f"Le salon <#{channel_id}> est déjà exclu de l'XP vocal.")
        else:
            await ctx.send(f"🔇 Le salon <#{channel_id}> est désormais exclu de l'XP vocal.")

    @commands.command(name="xp")
    @commands.has_permissions(administrator=True)
    async def xp_channel(self, ctx: commands.Context, channel_id: int) -> None:
        async with self._session() as session:
            removed = await remove_no_xp_channel(session, ctx.guild.id, channel_id)
            await session.commit()

        if removed:
            await ctx.send(f"🔊 Le salon <#{channel_id}> peut de nouveau donner de l'XP vocal.")
        else:
            await ctx.send(f"Le salon <#{channel_id}> n'était pas exclu de l'XP vocal.")


async def setup(bot) -> None:
    await bot.add_cog(VoiceCog(bot))
