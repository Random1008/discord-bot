from discord.ext import commands

from services.invites import diff_invite_uses
from services.users import get_or_create_user


class InvitesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._uses_by_guild: dict[int, dict[str, int]] = {}
        self._inviter_by_code: dict[int, dict[str, int]] = {}

    def _session(self):
        return self.bot.session_factory()

    async def _snapshot_guild(self, guild) -> None:
        invites = await guild.invites()
        self._uses_by_guild[guild.id] = {invite.code: invite.uses for invite in invites}
        self._inviter_by_code[guild.id] = {invite.code: invite.inviter.id for invite in invites}

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._snapshot_guild(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite) -> None:
        self._uses_by_guild.setdefault(invite.guild.id, {})[invite.code] = 0
        self._inviter_by_code.setdefault(invite.guild.id, {})[invite.code] = invite.inviter.id

    @commands.Cog.listener()
    async def on_member_join(self, member) -> None:
        guild = member.guild
        before = self._uses_by_guild.get(guild.id, {})
        invites = await guild.invites()
        after = {invite.code: invite.uses for invite in invites}
        inviter_by_code = {invite.code: invite.inviter.id for invite in invites}
        inviter_obj_by_code = {invite.code: invite.inviter for invite in invites}

        used_code = diff_invite_uses(before, after)

        async with self._session() as session:
            new_user = await get_or_create_user(session, guild.id, member.id, member.display_name)
            if used_code is not None:
                inviter = inviter_obj_by_code.get(used_code)
                if inviter is not None:
                    await get_or_create_user(
                        session, guild.id, inviter.id, getattr(inviter, "display_name", None) or inviter.name
                    )
                new_user.invited_by_guild_id = guild.id
                new_user.invited_by_user_id = inviter_by_code.get(used_code)
            await session.commit()

        self._uses_by_guild[guild.id] = after
        self._inviter_by_code[guild.id] = inviter_by_code


async def setup(bot) -> None:
    await bot.add_cog(InvitesCog(bot))
