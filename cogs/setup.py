import discord
from discord.ext import commands

from config.settings import settings
from services.proces_config import (
    DEFAULT_PROCES_CONFIG_PATH,
    add_panel_message,
    build_proces_embed,
    load_proces_config,
    save_proces_config,
)
from services.welcome_config import DEFAULT_WELCOME_CONFIG_PATH, build_welcome_embed, load_welcome_config, save_welcome_config
from utils.permissions import is_admin


class WelcomeEditModal(discord.ui.Modal, title="Message de bienvenue"):
    def __init__(self, cog: "SetupCog", config: dict, message: discord.Message | None) -> None:
        super().__init__()
        self.cog = cog
        self.message = message
        self.title_input = discord.ui.TextInput(label="Titre", default=config["title"], max_length=256)
        self.text_input = discord.ui.TextInput(
            label="Texte (utilise {membre} pour mentionner)",
            style=discord.TextStyle.paragraph,
            default=config["text"],
            max_length=2000,
        )
        self.image_input = discord.ui.TextInput(
            label="URL de l'image (optionnel)",
            required=False,
            default=config.get("image_url") or "",
            max_length=500,
        )
        self.add_item(self.title_input)
        self.add_item(self.text_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        image_url = self.image_input.value.strip() or None
        save_welcome_config(self.cog._welcome_config_path, self.title_input.value, self.text_input.value, image_url)
        new_config = load_welcome_config(self.cog._welcome_config_path)

        await interaction.response.send_message(
            "✅ Message de bienvenue mis à jour. Aperçu :", embed=build_welcome_embed(new_config), ephemeral=True
        )
        if self.message is not None:
            await self.message.edit(embed=build_welcome_embed(new_config))


class WelcomeConfigView(discord.ui.View):
    def __init__(self, cog: "SetupCog", author_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.message: discord.Message | None = None

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "Seul l'administrateur ayant lancé la commande peut modifier ce message.", ephemeral=True
            )
            return
        config = load_welcome_config(self.cog._welcome_config_path)
        await interaction.response.send_modal(WelcomeEditModal(self.cog, config, self.message))


class ProcesSetupView(discord.ui.View):
    def __init__(self, cog: "SetupCog", author_id: int) -> None:
        # timeout=None : le bouton Configurer ne meurt plus après 10 minutes ;
        # il vit jusqu'au redémarrage du bot (relancer .setup proces après un reboot).
        super().__init__(timeout=None)
        self.cog = cog
        self.author_id = author_id

    @discord.ui.button(label="Configurer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def configure_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "Seul l'administrateur ayant lancé la commande peut configurer le panneau.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ProcesSetupModal(self.cog))


class ProcesSetupModal(discord.ui.Modal, title="Panneau des procès"):
    def __init__(self, cog: "SetupCog") -> None:
        super().__init__()
        self.cog = cog
        config = load_proces_config(self.cog._proces_config_path)
        self.title_input = discord.ui.TextInput(label="Titre de l'embed", default=config["title"], max_length=256)
        self.text_input = discord.ui.TextInput(
            label="Texte de l'embed",
            style=discord.TextStyle.paragraph,
            default=config["text"],
            max_length=2000,
        )
        self.reglement_input = discord.ui.TextInput(
            label="Règlement du serveur (appliqué par le juge IA)",
            style=discord.TextStyle.paragraph,
            default=config["reglement"],
            max_length=4000,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.text_input)
        self.add_item(self.reglement_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = self.title_input.value.strip() or "⚖️ Tribunal — Déposer une plainte"
        text = self.text_input.value.strip() or "Clique sur le bouton pour déposer une plainte."
        save_proces_config(
            self.cog._proces_config_path,
            title,
            text,
            reglement=self.reglement_input.value.strip(),
        )
        new_config = load_proces_config(self.cog._proces_config_path)

        channel_id = settings.proces_channel_id
        if not channel_id:
            await interaction.response.send_message(
                "✅ Panneau enregistré. ⚠️ Aucun salon de procès défini : configure-le dans `.config` "
                "(Salon des procès) puis relance `.setup proces`.",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(int(channel_id))
        if channel is None:
            await interaction.response.send_message(
                f"⚠️ Salon de procès introuvable (ID `{channel_id}`). Vérifie `.config`.",
                ephemeral=True,
            )
            return

        from cogs.proces import ProcesPanelView

        proces_cog = self.cog.bot.get_cog("ProcesCog")
        panel_msg = await channel.send(embed=build_proces_embed(new_config), view=ProcesPanelView(proces_cog))
        # Enregistre le message du panneau pour le ré-attacher au prochain démarrage
        # (bouton immortel même après un redémarrage du bot).
        add_panel_message(DEFAULT_PROCES_CONFIG_PATH, panel_msg.id)
        await interaction.response.send_message(
            f"✅ Panneau de procès envoyé dans {channel.mention}.", ephemeral=True
        )


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._welcome_config_path = DEFAULT_WELCOME_CONFIG_PATH
        self._proces_config_path = DEFAULT_PROCES_CONFIG_PATH

    @commands.group(name="setup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def setup_group(self, ctx: commands.Context) -> None:
        await ctx.send(f"Usage : `{ctx.prefix}setup welcome` · `{ctx.prefix}setup proces`")

    @setup_group.command(name="welcome")
    @commands.has_permissions(administrator=True)
    async def setup_welcome(self, ctx: commands.Context) -> None:
        config = load_welcome_config(self._welcome_config_path)
        embed = build_welcome_embed(config)
        view = WelcomeConfigView(self, author_id=ctx.author.id)
        view.message = await ctx.send(
            "Configuration du message de bienvenue (posté quand un membre rejoint le serveur) — "
            "aperçu ci-dessous, `{membre}` sera remplacé par la mention du nouveau membre :",
            embed=embed,
            view=view,
        )

    @setup_group.command(name="proces")
    @commands.has_permissions(administrator=True)
    async def setup_proces(self, ctx: commands.Context) -> None:
        config = load_proces_config(self._proces_config_path)
        await ctx.send(
            "Panneau des procès : clique sur **Configurer** pour personnaliser l'embed puis l'envoyer "
            "dans le salon configuré dans `.config`. Aperçu actuel :",
            embed=build_proces_embed(config),
            view=ProcesSetupView(self, author_id=ctx.author.id),
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not settings.welcome_channel_id:
            return
        channel = member.guild.get_channel(int(settings.welcome_channel_id))
        if channel is None:
            return
        config = load_welcome_config(self._welcome_config_path)
        await channel.send(embed=build_welcome_embed(config, member))


async def setup(bot) -> None:
    await bot.add_cog(SetupCog(bot))
