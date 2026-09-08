from datetime import datetime, timezone
from pathlib import Path

from discord.ext import commands, tasks

from config.settings import settings
from services.announcements import format_reward_message
from services.classement_badges import sweep_classement_badges
from services.leaderboard import get_coins_leaderboard, get_message_leaderboard, get_voice_leaderboard
from services.leaderboard_roles import compute_multi_role_changes, compute_role_changes, parse_role_config

# Rôles à un seul détenteur : donnés uniquement au n°1 du classement.
ROLE_CONFIG_LEADERBOARD = {
    "roi_du_chat": get_message_leaderboard,
    "maitre_vocal": get_voice_leaderboard,
    "riche": get_coins_leaderboard,
}

# Rôles multi-détenteurs : donnés à tout le top 10 du classement.
MULTI_ROLE_CONFIG_LEADERBOARD = {
    "top_10_vocal": get_voice_leaderboard,
    "top_10_message": get_message_leaderboard,
    "top_10_argent": get_coins_leaderboard,
}

# Même fichier que celui édité par `.config` (source="leaderboard") : les IDs de
# rôle sont lus ici à chaque passage hebdomadaire, pas dans le .env.
LEADERBOARD_ROLES_PATH = Path(__file__).resolve().parent.parent / "config" / "leaderboard_roles.txt"


class ClassementRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._role_config_path = LEADERBOARD_ROLES_PATH

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    async def cog_load(self) -> None:
        self.weekly_sweep.start()

    def cog_unload(self) -> None:
        self.weekly_sweep.cancel()

    @tasks.loop(hours=168)
    async def weekly_sweep(self) -> None:
        for guild in self.bot.guilds:
            await self.run_sweep(guild)

    @weekly_sweep.before_loop
    async def before_weekly_sweep(self) -> None:
        await self.bot.wait_until_ready()

    async def run_sweep(self, guild) -> None:
        async with self._session() as session:
            outcomes = await sweep_classement_badges(session, guild.id, datetime.now(timezone.utc))
            await session.commit()

        channel = self._announcement_channel(guild)
        if channel is not None:
            for user_id, outcome in outcomes:
                member = guild.get_member(user_id)
                display_name = member.display_name if member is not None else str(user_id)
                await channel.send(format_reward_message(display_name, outcome))

        await self._rotate_roles(guild)

    async def _rotate_roles(self, guild) -> None:
        config = parse_role_config(self._role_config_path.read_text(encoding="utf-8"))
        for key, fetcher in {**ROLE_CONFIG_LEADERBOARD, **MULTI_ROLE_CONFIG_LEADERBOARD}.items():
            role_id = config.get(key)
            if not role_id:
                continue
            role = guild.get_role(role_id)
            if role is None:
                continue
            if key in ROLE_CONFIG_LEADERBOARD:
                await self._rotate_single_holder_role(guild, role, fetcher)
            elif key in MULTI_ROLE_CONFIG_LEADERBOARD:
                await self._rotate_multi_holder_role(guild, role, fetcher)

    async def refresh_roles(self, guild) -> None:
        """Recalcule et réattribue tous les rôles de classement immédiatement.

        Appelé à chaque exécution de `!leaderboard` (en plus du passage
        hebdomadaire) pour que les rôles reflètent les classements en temps réel.
        """
        await self._rotate_roles(guild)

    async def _rotate_single_holder_role(self, guild, role, fetcher) -> None:
        async with self._session() as session:
            leaderboard = await fetcher(session, guild.id, limit=1)

        new_holder_id = leaderboard[0].user_id if leaderboard else None
        current_holder_ids = {member.id for member in role.members}
        to_remove, to_add = compute_role_changes(current_holder_ids, new_holder_id)

        for member_id in to_remove:
            member = guild.get_member(member_id)
            if member is not None:
                await member.remove_roles(role)

        if to_add is not None:
            member = guild.get_member(to_add)
            if member is not None:
                await member.add_roles(role)

    async def _rotate_multi_holder_role(self, guild, role, fetcher) -> None:
        async with self._session() as session:
            leaderboard = await fetcher(session, guild.id, limit=10)

        eligible_ids = {entry.user_id for entry in leaderboard}
        current_holder_ids = {member.id for member in role.members}
        to_remove, to_add = compute_multi_role_changes(current_holder_ids, eligible_ids)

        for member_id in to_remove:
            member = guild.get_member(member_id)
            if member is not None:
                await member.remove_roles(role)

        for member_id in to_add:
            member = guild.get_member(member_id)
            if member is not None:
                await member.add_roles(role)


async def setup(bot) -> None:
    await bot.add_cog(ClassementRolesCog(bot))
