from discord.ext import commands

from cogs._xp_common import PRESTIGE_ROLE_SETTINGS, REWARD_ROLE_SETTINGS
from config.settings import settings
from services.leveling import get_all_levels
from services.rewards import get_role_reward_thresholds
from services.role_reconciliation import compute_expected_reward_role_ids, compute_role_diff, resolve_role_ids


class ReconcileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    @commands.command(name="act")
    @commands.has_permissions(administrator=True)
    async def act(self, ctx: commands.Context) -> None:
        """Recalcule tous les rôles automatiques du serveur à partir de l'état actuel
        (niveau, prestige, classements) : ajoute ceux qui manquent, retire ceux qui ne
        sont plus justifiés. Rattrape les cas où un rôle a été retiré/donné à la main,
        ou désynchronisé par un .resetuser/.setlevel."""
        guild = ctx.guild
        if guild is None:
            return

        async with self._session() as session:
            reward_thresholds = await get_role_reward_thresholds(session)
            levels = await get_all_levels(session, guild.id)

        reward_role_ids = resolve_role_ids(REWARD_ROLE_SETTINGS, settings)
        prestige_role_ids = resolve_role_ids(PRESTIGE_ROLE_SETTINGS, settings)
        managed_role_ids = set(reward_role_ids.values()) | set(prestige_role_ids.values())

        added = 0
        removed = 0
        for user_id, level, prestige in levels:
            member = guild.get_member(user_id)
            if member is None:
                continue

            expected = compute_expected_reward_role_ids(
                level, prestige, reward_role_ids, reward_thresholds, prestige_role_ids
            )
            current = {role.id for role in member.roles}
            to_add, to_remove = compute_role_diff(current, expected, managed_role_ids)

            for role_id in to_add:
                role = guild.get_role(role_id)
                if role is not None:
                    await member.add_roles(role)
                    added += 1
            for role_id in to_remove:
                role = guild.get_role(role_id)
                if role is not None:
                    await member.remove_roles(role)
                    removed += 1

        classement_cog = self.bot.get_cog("ClassementRolesCog")
        if classement_cog is not None:
            await classement_cog.run_sweep(guild)

        await ctx.send(
            f"✅ Réconciliation terminée : {added} rôle(s) de récompense/prestige ajouté(s), "
            f"{removed} retiré(s). Rôles de classement (roi du chat, maître vocal, top XP) "
            "et badges également remis à jour."
        )


async def setup(bot) -> None:
    await bot.add_cog(ReconcileCog(bot))
