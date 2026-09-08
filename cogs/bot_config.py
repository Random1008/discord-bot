from pathlib import Path

import discord
from discord.ext import commands

from config.settings import settings
from services.config_editor import (
    DEFAULT_ENV_PATH,
    InvalidConfigValueError,
    parse_amount_input,
    parse_id_input,
    parse_secret_input,
    set_leaderboard_role,
    set_settings_value,
)
from services.config_overview import ConfigEntry, ConfigSection, build_config_sections
from services.leaderboard_roles import parse_role_config
from utils.permissions import is_admin

ROLE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "leaderboard_roles.txt"


def format_entry_value(guild, entry: ConfigEntry) -> str:
    if entry.kind == "amount":
        return str(entry.value)

    if entry.kind == "secret":
        return "✅ configurée" if entry.value else "❌ non configurée"

    if not entry.value:
        return "❌ non configuré"

    resolved = None
    if guild is not None:
        resolved = guild.get_role(int(entry.value)) if entry.kind == "role" else guild.get_channel(int(entry.value))

    if resolved is not None:
        return resolved.mention
    return f"⚠️ ID `{entry.value}` introuvable sur ce serveur"


def _select_description(entry: ConfigEntry) -> str:
    if entry.kind == "secret":
        return "Configurée" if entry.value else "Non configurée"
    if entry.kind == "amount" or entry.value:
        return f"Actuel : {entry.value}"
    return "Non configuré"


def build_config_embed(guild, sections: list[ConfigSection]) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Configuration de Colombina",
        description=(
            "IDs de rôles/salons configurés via les variables d'environnement.\n"
            "Clique sur ✏️ **Modifier** pour changer une valeur."
        ),
    )
    for section in sections:
        lines = [f"**{entry.label}** — {format_entry_value(guild, entry)}" for entry in section.entries]
        embed.add_field(name=section.title, value="\n".join(lines), inline=False)
    return embed


class ConfigEditModal(discord.ui.Modal):
    def __init__(self, cog: "BotConfigCog", entry: ConfigEntry, message: discord.Message | None) -> None:
        super().__init__(title=f"Modifier : {entry.label}"[:45])
        self.cog = cog
        self.entry = entry
        self.message = message
        if entry.kind == "amount":
            self.value_input = discord.ui.TextInput(
                label="Nombre entier positif ou nul",
                default=str(entry.value),
                required=True,
                max_length=10,
            )
        elif entry.kind == "secret":
            self.value_input = discord.ui.TextInput(
                label="Nouvelle valeur, ou vide pour effacer",
                default="",
                required=False,
                max_length=200,
            )
        else:
            self.value_input = discord.ui.TextInput(
                label="ID, mention, ou vide pour effacer",
                default=str(entry.value) if entry.value else "",
                required=False,
                max_length=100,
            )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.entry.kind == "amount":
            try:
                new_value = parse_amount_input(self.value_input.value)
            except InvalidConfigValueError:
                await interaction.response.send_message(
                    "❌ Valeur invalide — donne un nombre entier positif ou nul.", ephemeral=True
                )
                return
            set_settings_value(settings, self.entry.key, new_value, env_path=self.cog._env_path)
            await interaction.response.send_message(f"✅ **{self.entry.label}** → `{new_value}`", ephemeral=True)
            if self.message is not None:
                embed = build_config_embed(self.message.guild, self.cog._sections())
                await self.message.edit(embed=embed)
            return

        if self.entry.kind == "secret":
            new_value = parse_secret_input(self.value_input.value)
            set_settings_value(settings, self.entry.key, new_value, env_path=self.cog._env_path)
            summary = "configurée" if new_value is not None else "effacée"
            await interaction.response.send_message(f"✅ **{self.entry.label}** → {summary}", ephemeral=True)
            if self.message is not None:
                embed = build_config_embed(self.message.guild, self.cog._sections())
                await self.message.edit(embed=embed)
            return

        try:
            new_value = parse_id_input(self.value_input.value)
        except InvalidConfigValueError:
            await interaction.response.send_message(
                "❌ Valeur invalide — donne un ID Discord, une mention de rôle/salon, ou laisse vide pour effacer.",
                ephemeral=True,
            )
            return

        if self.entry.source == "leaderboard":
            set_leaderboard_role(self.cog._role_config_path, self.entry.key, new_value)
        else:
            set_settings_value(settings, self.entry.key, new_value, env_path=self.cog._env_path)

        warning = ""
        if new_value is not None and interaction.guild is not None:
            resolved = (
                interaction.guild.get_role(int(new_value))
                if self.entry.kind == "role"
                else interaction.guild.get_channel(int(new_value))
            )
            if resolved is None:
                warning = "\n⚠️ Introuvable sur ce serveur (peut être valide sur l'autre serveur de Colombina)."

        summary = f"`{new_value}`{warning}" if new_value is not None else "effacé"
        await interaction.response.send_message(f"✅ **{self.entry.label}** → {summary}", ephemeral=True)

        if self.message is not None:
            embed = build_config_embed(self.message.guild, self.cog._sections())
            await self.message.edit(embed=embed)


class ConfigEntrySelect(discord.ui.Select):
    """Lists the settings within a single section — a section never has enough
    entries to hit Discord's 25-option-per-select limit, unlike the flat list
    of every setting across every section."""

    def __init__(self, cog: "BotConfigCog", message: discord.Message | None, author_id: int, section: ConfigSection) -> None:
        self.cog = cog
        self.message = message
        self.author_id = author_id
        self.entries_by_key = {entry.key: entry for entry in section.entries}
        options = [
            discord.SelectOption(
                label=entry.label[:100],
                value=entry.key,
                description=_select_description(entry)[:100],
            )
            for entry in section.entries
        ]
        super().__init__(placeholder=f"{section.title} — choisis un paramètre...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu n'est pas le tien.", ephemeral=True)
            return
        entry = self.entries_by_key[self.values[0]]
        await interaction.response.send_modal(ConfigEditModal(self.cog, entry, self.message))


class ConfigEntrySelectView(discord.ui.View):
    def __init__(self, cog: "BotConfigCog", message: discord.Message | None, author_id: int, section: ConfigSection) -> None:
        super().__init__(timeout=180)
        self.add_item(ConfigEntrySelect(cog, message, author_id, section))


class ConfigSectionSelect(discord.ui.Select):
    def __init__(
        self, cog: "BotConfigCog", message: discord.Message | None, author_id: int, sections: list[ConfigSection]
    ) -> None:
        self.cog = cog
        self.message = message
        self.author_id = author_id
        self.sections_by_title = {section.title: section for section in sections}
        options = [
            discord.SelectOption(
                label=section.title[:100],
                value=section.title,
                description=f"{len(section.entries)} paramètre(s)",
            )
            for section in sections
        ]
        super().__init__(placeholder="Choisis une catégorie...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu n'est pas le tien.", ephemeral=True)
            return
        section = self.sections_by_title[self.values[0]]
        entry_view = ConfigEntrySelectView(self.cog, self.message, self.author_id, section)
        await interaction.response.edit_message(
            content=f"Catégorie **{section.title}** — choisis un paramètre :", view=entry_view
        )


class ConfigSectionSelectView(discord.ui.View):
    def __init__(
        self, cog: "BotConfigCog", message: discord.Message | None, author_id: int, sections: list[ConfigSection]
    ) -> None:
        super().__init__(timeout=180)
        self.add_item(ConfigSectionSelect(cog, message, author_id, sections))


class ConfigOverviewView(discord.ui.View):
    def __init__(self, cog: "BotConfigCog", author_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.message: discord.Message | None = None

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "Seul l'administrateur ayant lancé la commande peut modifier la configuration.", ephemeral=True
            )
            return
        sections = self.cog._sections()
        select_view = ConfigSectionSelectView(self.cog, self.message, self.author_id, sections)
        await interaction.response.send_message("Choisis une catégorie :", view=select_view, ephemeral=True)

    @discord.ui.button(label="Réinitialiser", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "Seul l'administrateur ayant lancé la commande peut réinitialiser la configuration.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "⚠️ Réinitialiser **tous** les paramètres de configuration (salons, rôles, montants, clé API) ?",
            view=_ConfirmResetView(self.cog, self.author_id, self.message),
            ephemeral=True,
        )


class _ConfirmResetView(discord.ui.View):
    def __init__(self, cog: "BotConfigCog", author_id: int, config_message: discord.Message | None) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id
        self.config_message = config_message

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce choix n'est pas le tien.", ephemeral=True)
            return
        self.cog._clear_all_config()
        if self.config_message is not None:
            embed = build_config_embed(self.config_message.guild, self.cog._sections())
            await self.config_message.edit(embed=embed)
        await interaction.response.edit_message(content="✅ Configuration réinitialisée.", view=None)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce choix n'est pas le tien.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Annulé.", view=None)


class BotConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._role_config_path = ROLE_CONFIG_PATH
        self._env_path = DEFAULT_ENV_PATH

    def _sections(self) -> list[ConfigSection]:
        leaderboard_roles = parse_role_config(self._role_config_path.read_text(encoding="utf-8"))
        return build_config_sections(settings, leaderboard_roles)

    def _clear_all_config(self) -> None:
        """Efface tous les paramètres listés dans .config (remet à vide, la clé
        API incluse). Chaque entrée est remise à None dans settings et dans le
        fichier .env / leaderboard_roles.txt."""
        for section in self._sections():
            for entry in section.entries:
                if entry.source == "leaderboard":
                    set_leaderboard_role(self._role_config_path, entry.key, None)
                else:
                    set_settings_value(settings, entry.key, None, env_path=self._env_path)

    @commands.command(name="config")
    @commands.has_permissions(administrator=True)
    async def config(self, ctx: commands.Context) -> None:
        sections = self._sections()
        embed = build_config_embed(ctx.guild, sections)
        view = ConfigOverviewView(self, author_id=ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot) -> None:
    await bot.add_cog(BotConfigCog(bot))
