import discord


async def send_admin_log_embed(guild, channel_id: str | None, embed: discord.Embed) -> None:
    if guild is None or not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        return
    await channel.send(embed=embed)
