import discord


def is_admin(user) -> bool:
    return isinstance(user, discord.Member) and user.guild_permissions.administrator
