import random

import discord
from discord.ext import commands

from cogs._xp_common import award_xp
from config.settings import settings
from services.admin_permission import can_bypass
from services.crates import CRATE_RARITIES, NoKeyOwnedError, get_key_counts, open_crate
from services.users import get_or_create_user

RARITY_LABELS = {
    "commun": "🟢 Commune",
    "rare": "🔵 Rare",
    "epique": "🟣 Épique",
    "legendaire": "🟠 Légendaire",
    "mythique": "🔴 Mythique",
    "divin": "⚪ Divine",
}

RARITY_BUTTON_STYLES = {
    "commun": discord.ButtonStyle.secondary,
    "rare": discord.ButtonStyle.primary,
    "epique": discord.ButtonStyle.primary,
    "legendaire": discord.ButtonStyle.success,
    "mythique": discord.ButtonStyle.danger,
    "divin": discord.ButtonStyle.success,
}

CRATE_BUTTONS_PER_ROW = 3


def build_crate_embed(counts: dict[str, int], bypass: bool = False) -> discord.Embed:
    description = "Choisis une caisse à ouvrir avec le bouton correspondant, ou tente ta chance avec 🎲 Aléatoire."
    if bypass:
        description += "\n🔓 **Mode bypass actif** — ouverture possible sans clé."
    embed = discord.Embed(title="🗝️ Tes caisses", description=description)
    for rarity in CRATE_RARITIES:
        embed.add_field(name=RARITY_LABELS[rarity], value=f"{counts[rarity]} clé(s)", inline=True)
    return embed


def _describe_result(result) -> str:
    lines = [f"**{result.label}**"]
    if result.pull_results:
        for pull_result in result.pull_results:
            if pull_result.character is not None:
                lines.append(f"🎉 {pull_result.rarity} : **{pull_result.character}**")
            else:
                lines.append(f"🌑 {pull_result.rarity} !")
    for extra in result.extra_results:
        lines.append(_describe_result(extra))
    return "\n".join(lines)


async def _apply_xp_recursively(session, guild, channel_resolver, member, result) -> None:
    if result.kind == "xp":
        await award_xp(session, guild, channel_resolver, member, result.value)
    for extra in result.extra_results:
        await _apply_xp_recursively(session, guild, channel_resolver, member, extra)


async def _open_crate_and_respond(interaction: discord.Interaction, view: "CrateView", rarity: str) -> None:
    cog = view.cog
    guild_id = interaction.guild.id
    async with cog._session() as session:
        try:
            result = await open_crate(session, guild_id, interaction.user.id, rarity, bypass=view.bypass)
        except NoKeyOwnedError:
            await session.rollback()
            await interaction.response.send_message(
                f"Tu n'as plus de clé {RARITY_LABELS[rarity]}.", ephemeral=True
            )
            return

        await _apply_xp_recursively(
            session,
            interaction.guild,
            lambda: cog._announcement_channel(interaction.guild),
            interaction.user,
            result,
        )
        await session.commit()

        counts = await get_key_counts(session, guild_id, interaction.user.id)

    prefix = "🔓 [bypass] " if view.bypass else "🎉 "
    message = f"{prefix}Tu as ouvert une caisse **{RARITY_LABELS[rarity]}** et obtenu : {_describe_result(result)}"
    await interaction.response.send_message(message, ephemeral=True)

    new_view = CrateView(cog, view.author_id, counts, bypass=view.bypass)
    await interaction.message.edit(embed=build_crate_embed(counts, bypass=view.bypass), view=new_view)


class CrateButton(discord.ui.Button):
    def __init__(self, rarity: str, disabled: bool, row: int) -> None:
        super().__init__(label=RARITY_LABELS[rarity], style=RARITY_BUTTON_STYLES[rarity], disabled=disabled, row=row)
        self.rarity = rarity

    async def callback(self, interaction: discord.Interaction) -> None:
        view: CrateView = self.view
        if interaction.user.id != view.author_id:
            await interaction.response.send_message(
                "Seul le joueur ayant lancé la commande peut ouvrir ses caisses.", ephemeral=True
            )
            return
        await _open_crate_and_respond(interaction, view, self.rarity)


class RandomCrateButton(discord.ui.Button):
    def __init__(self, disabled: bool) -> None:
        row = (len(CRATE_RARITIES) - 1) // CRATE_BUTTONS_PER_ROW + 1
        super().__init__(label="🎲 Aléatoire", style=discord.ButtonStyle.blurple, disabled=disabled, row=row)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: CrateView = self.view
        if interaction.user.id != view.author_id:
            await interaction.response.send_message(
                "Seul le joueur ayant lancé la commande peut ouvrir ses caisses.", ephemeral=True
            )
            return

        eligible = CRATE_RARITIES if view.bypass else [r for r in CRATE_RARITIES if view.counts[r] > 0]
        if not eligible:
            await interaction.response.send_message("Tu n'as aucune caisse à ouvrir.", ephemeral=True)
            return

        rarity = random.choice(eligible)
        await _open_crate_and_respond(interaction, view, rarity)


class CrateView(discord.ui.View):
    def __init__(self, cog: "CrateCog", author_id: int, counts: dict[str, int], bypass: bool = False) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.bypass = bypass
        self.counts = counts
        self.buttons_by_rarity: dict[str, CrateButton] = {}
        for index, rarity in enumerate(CRATE_RARITIES):
            disabled = counts[rarity] <= 0 and not bypass
            button = CrateButton(rarity, disabled=disabled, row=index // CRATE_BUTTONS_PER_ROW)
            self.buttons_by_rarity[rarity] = button
            self.add_item(button)

        random_disabled = not bypass and not any(counts[rarity] > 0 for rarity in CRATE_RARITIES)
        self.random_button = RandomCrateButton(disabled=random_disabled)
        self.add_item(self.random_button)


class CrateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _announcement_channel(self, guild):
        if guild is None or not settings.level_up_channel_id:
            return None
        return guild.get_channel(int(settings.level_up_channel_id))

    @commands.command(name="key")
    async def key(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id

        async with self._session() as session:
            effective_bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            await session.commit()
            counts = await get_key_counts(session, guild_id, ctx.author.id)

        view = CrateView(self, ctx.author.id, counts, bypass=effective_bypass)
        await ctx.send(embed=build_crate_embed(counts, bypass=effective_bypass), view=view)


async def setup(bot) -> None:
    await bot.add_cog(CrateCog(bot))
