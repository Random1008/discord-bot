import discord
from discord.ext import commands

from config.settings import YORU_DUPLICATE_RESTRICTED_GUILD_ID

# Chaque catégorie regroupe des commandes liées pour le menu déroulant.
# "entries" est une liste de tuples (usage, description) tenue à la main,
# aucune commande ici n'a de docstring/help= à récupérer automatiquement.
# "restricted_on_yoru_guild" : catégorie masquée sur le serveur où yoru a
# sa propre version équivalente (cf. main.py::_is_yoru_duplicate_command).
PLAYER_CATEGORIES = [
    {
        "key": "economie",
        "label": "Économie",
        "emoji": "💰",
        "description": "Argent, travail, braquages et investissements.",
        "restricted_on_yoru_guild": False,
        "entries": [
            ("$balance", "Voir ton solde de credits."),
            ("$pay @membre <montant>", "Payer quelqu'un."),
            ("$daily", "Récupérer ta récompense quotidienne (bonus de série)."),
            ("$work", "Travailler pour gagner des credits."),
            ("$crime", "Tenter un coup, risque de te faire arrêter."),
            ("$rob @membre", "Braquer un autre joueur."),
            ("$weekly / $monthly", "Récompenses hebdo/mensuelles."),
            ("$invest <montant>", "Investir des credits (max 5/jour, plafond 100k, gros gain x2–x2.5 mais 75% de perte)."),
            ("$stocks", "Voir l'indice de marché du serveur."),
        ],
    },
    {
        "key": "crime",
        "label": "Monde criminel",
        "emoji": "🦹",
        "description": "Activités illégales, toutes avec cooldown. Cible optionnelle (@mention ou ID) : sans cible = 100% de réussite, avec cible = 75% mais gains doublés volés à la victime.",
        "restricted_on_yoru_guild": False,
        "entries": [
            ("$hack [@cible]", "Pirater un compte bancaire (rapide, gains moyens)."),
            ("$braquage", "Braquer une banque (gros gains, gros risques, long cooldown)."),
            ("$deal [@cible]", "Transaction illégale risquée (gains variables, RP)."),
            ("$pirate [@cible]", "Pirater un serveur virtuel (gains moyens)."),
            ("$fraude [@cible]", "Fraude bancaire (gains élevés, risque de lourdes pertes)."),
            ("$cambriolage [@cible]", "Cambrioler une maison (gains élevés, risque d'alarme)."),
            ("$escroquerie [@cible]", "Arnaquer un PNJ (gains faibles, cooldown court)."),
            ("$chantage", "Faire chanter un PNJ (gains moyens, RP dramatique)."),
            ("$contrebande", "Passer de la contrebande (gains élevés, risque de douanes)."),
            ("$vol [@cible]", "Vol simple (gains faibles, rapide)."),
            ("$falsifier [@cible]", "Falsifier des documents (bonus multiplicateur)."),
            ("$mafia", "Marché de la mafia : 35% de réussir à entrer, remise -30 à -60% sur le $shop, 1 achat max (salon mafia)."),
            ("$blanchir [montant]", "Blanchir de l'argent (multiplicateur, risque de saisie)."),
            ("$infiltration [@cible]", "Infiltrer un groupe (gains moyens à élevés)."),
            ("$hijack", "Détourner un véhicule (gains élevés, risque de piège)."),
            ("$proces @membre [accusation] [bypass]", "Ouvrir un procès : l'accusateur, l'accusé et un juge IA débattent ; le juge applique le règlement du serveur (éditable via .setup proces) et voit aussi les images/GIFs postés comme preuves (coupable = 100 credits × nb de messages). Admin : « bypass » en fin pour afficher le dédommagement sans débiter. Admin : `.proces end` dans le fil pour clore et faire juger immédiatement."),
            (
                "!complice [@membre | ID]",
                "Dans un procès en cours, ajouter un complice au débat "
                "(mention/ID du membre, ou sans argument pour la liste déroulante).",
            ),
        ],
    },
    {
        "key": "boutique",
        "label": "Boutique & Caisses",
        "emoji": "🛒",
        "description": "Achats, ventes, inventaire et caisses à ouvrir.",
        "restricted_on_yoru_guild": False,
        "entries": [
            ("$shop", "Voir les objets en vente."),
            ("$buy <id>", "Acheter un objet par son id."),
            ("$sell <id>", "Revendre un objet possédé."),
            ("$inventory", "Voir ton inventaire et tes clés."),
            ("$key", "Ouvrir tes caisses (boutons par rareté, jusqu'à Divin)."),
        ],
    },
    {
        "key": "casino",
        "label": "Casino",
        "emoji": "🎰",
        "description": "Jeux de hasard : mise des credits.",
        "restricted_on_yoru_guild": True,
        "entries": [
            ("$coinflip <mise> [pile|face]", "Pile ou face."),
            ("$slots <mise>", "Machine à sous."),
            ("$dice <mise> <1-6>", "Dés."),
            ("$roulette <mise> <rouge|noir|vert>", "Roulette."),
            ("$blackjack <mise>", "Blackjack contre le croupier."),
            ("$highlow <mise> <plus|moins>", "Plus ou moins."),
            ("$poker <mise>", "Poker (5 cartes)."),
            ("$roue <mise>", "Roue de la Fortune (secteurs multiplicateurs)."),
            ("$craps <mise> <sept|plus|moins>", "Craps : parie sur la somme de deux dés."),
            ("$jackpot <mise>", "Cagnotte progressive du serveur."),
            ("$casinostats", "Voir tes statistiques casino."),
        ],
    },
    {
        "key": "gacha",
        "label": "Gacha",
        "emoji": "🎲",
        "description": "Invocations de personnages à collectionner.",
        "restricted_on_yoru_guild": True,
        "entries": [
            ("$gacha pull / multi", "Invoquer un ou plusieurs personnages."),
            ("$gacha rates / pity", "Taux d'invocation et pity actuel."),
            ("$gacha list", "Voir tous les personnages du gacha, triés par rareté."),
            ("$gacha inventory / history", "Personnages obtenus et historique."),
            ("$gacha wishlist set/clear <nom>", "Gérer ta wishlist."),
        ],
    },
    {
        "key": "tour",
        "label": "Tour RPG",
        "emoji": "🗼",
        "description": "L'ascension de la tour, 100 étages, boss, équipement persistant, titres et classes à débloquer — pilotée par des boutons, dans ton salon tower-of-<toi>.",
        "restricted_on_yoru_guild": True,
        "entries": [
            ("!towerof [@membre]", "Voir la fiche Tour d'un joueur (niveau, étage max, équipement, titres, Or...)."),
            ("🏰 Entrer", "Lancer une run ou reprendre celle en cours (choix de classe selon ton niveau, Or de départ)."),
            ("⚔️ COMBAT / ACTE / OBJET / PITIÉ", "Attaquer, examiner l'ennemi, utiliser une potion du sac, fuir."),
            ("💰 Or", "Voir ton solde d'Or et le convertir en credits."),
            ("📖 Codex", "Voir les salles et événements découverts."),
            ("🗡️ Équipement", "Équiper/déséquiper ton arme et ton armure (persistantes entre les runs)."),
        ],
    },
    {
        "key": "progression",
        "label": "Profil & Progression",
        "emoji": "🏆",
        "description": "Niveau, quêtes et classements.",
        "restricted_on_yoru_guild": False,
        "entries": [
            ("!profile [@membre]", "Voir un profil (niveau, badges, clés)."),
            ("!quest", "Voir tes quêtes du jour."),
            ("!leaderboard [xp|messages|vocal|coins]", "Classement du serveur (XP, messages, temps vocal, argent)."),
        ],
    },
]

ADMIN_CATEGORIES = [
    {
        "key": "admin_general",
        "label": "Aide & Configuration",
        "emoji": "🛠️",
        "description": "Aide, configuration du bot et panneaux (bienvenue, procès).",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".adminhelp", "Afficher ce menu."),
            (
                ".config",
                "Voir et modifier la configuration (salons, rôles, montants, clé IA). Une fois le salon "
                "de logs admin défini, chaque commande admin y est journalisée automatiquement.",
            ),
            (".setup welcome", "Configurer le message de bienvenue (titre/texte/image, popup)."),
            (
                ".setup proces",
                "Créer le panneau des procès (embed personnalisable + bouton « Déposer une plainte ») "
                "envoyé dans le salon configuré via .config. Le bouton « Configurer » permet aussi de "
                "modifier le règlement du serveur appliqué par le juge IA.",
            ),
            (
                ".proces end",
                "Clore le procès en cours (à taper dans son fil) : le juge rend immédiatement "
                "son jugement sur la base des éléments déjà présentés.",
            ),
        ],
    },
    {
        "key": "admin_acces",
        "label": "Permissions & Accès",
        "emoji": "🔐",
        "description": "Bloquer/débloquer un membre et gérer la whitelist admin.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".bot off @membre", "Bloquer un membre : il ne peut plus utiliser aucune commande du bot."),
            (".bot on @membre", "Débloquer un membre."),
            (".permadd @membre", "Autoriser un membre à utiliser les commandes admin (en plus du rôle requis)."),
            (".permremove @membre", "Retirer l'accès admin d'un membre."),
        ],
    },
    {
        "key": "admin_argent",
        "label": "Argent",
        "emoji": "💰",
        "description": "Gestion du solde de credits des membres.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".addcoins / .removecoins @membre <montant>", "Ajouter/retirer des credits."),
            (".money add / .money remove @membre <montant>", "Ajouter/retirer des credits (alias de addcoins/removecoins)."),
            (".money reset @membre", "Remettre le solde d'un membre à 0."),
        ],
    },
    {
        "key": "admin_xp",
        "label": "XP, Niveaux & Récompenses",
        "emoji": "✨",
        "description": "Gestion du niveau, de l'XP, des récompenses et de l'XP vocal.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".setlevel @membre <niveau>", "Forcer le niveau d'un membre."),
            (".addxp / .removexp @membre <montant>", "Ajouter/retirer de l'XP."),
            (".event-participation @membre", "Bonus d'XP ponctuel (participation à un événement)."),
            (".givereward @membre [badge] [niveau]", "Donner un badge (par sa clé) ou rejouer les récompenses d'un niveau."),
            (".unxp <id|list>", "Exclure un salon de l'XP vocal (ou lister les salons exclus)."),
            (".xp <id>", "Réactiver l'XP vocal pour un salon."),
        ],
    },
    {
        "key": "admin_boutique",
        "label": "Boutique",
        "emoji": "🛒",
        "description": "Gestion des objets en vente dans la boutique.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".market add <nom> <desc> <prix>", "Ajouter un objet à la boutique."),
            (".market remove <nom>", "Retirer un objet de la boutique."),
            (".market edit <id>", "Modifier un objet (ouvre une popup)."),
            (".market list", "Lister tous les objets de la boutique."),
        ],
    },
    {
        "key": "admin_gacha",
        "label": "Gacha",
        "emoji": "🎲",
        "description": "Gestion de la collection gacha d'un membre.",
        "restricted_on_yoru_guild": True,
        "entries": [
            (".gacha add / .gacha remove @membre <nom>", "Donner/retirer un personnage précis (par son nom exact)."),
            (".gacha reset @membre", "Vider entièrement la collection gacha d'un membre."),
        ],
    },
    {
        "key": "admin_tour",
        "label": "Tour RPG",
        "emoji": "🗼",
        "description": "Gestion de la Tour RPG : panneau de jeu et étage max atteint.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".tourpanel [@membre]", "Poster le panneau de la Tour (avec @membre : dans son salon tower-of-<membre>)."),
            (".tower set @membre <étage>", "Fixer l'étage max atteint d'un membre."),
            (".tower add / .tower remove @membre <montant>", "Ajouter/retirer des étages à l'étage max atteint."),
            (".tower reset @membre", "Remettre l'étage max atteint d'un membre à 0."),
        ],
    },
    {
        "key": "admin_roles",
        "label": "Rôles & classements",
        "emoji": "🏆",
        "description": "Recalcul des rôles automatiques et des classements.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (
                ".act",
                "Recalculer tous les rôles automatiques (récompenses de niveau, prestige, classements) "
                "à partir de l'état actuel : ajoute ceux qui manquent, retire ceux qui ne sont plus justifiés.",
            ),
        ],
    },
    {
        "key": "admin_reset",
        "label": "Réinitialisation",
        "emoji": "♻️",
        "description": "Réinitialisation partielle ou totale d'un membre.",
        "restricted_on_yoru_guild": False,
        "entries": [
            (".resetuser @membre", "Réinitialiser toute la progression d'un membre (irréversible)."),
            (
                ".reset @membre <argent|tour|casino|gacha|boutique|all>",
                "Réinitialiser une partie ciblée d'un membre (irréversible). « all » et « boutique » demandent "
                "si les articles de la boutique doivent être supprimés ou juste mis à prix 0.",
            ),
        ],
    },
]


# Présentation en langage simple pour un public qui ne connaît pas encore le
# bot (contrairement à PLAYER_CATEGORIES, orienté syntaxe de commandes pour
# des joueurs déjà familiers). Utilisé par !maj.
MAJ_SECTIONS = [
    {
        "emoji": "💰",
        "title": "Économie & progression",
        "restricted_on_yoru_guild": False,
        "text": (
            "En discutant et en passant du temps en vocal, tu gagnes de l'XP et montes "
            "de niveau. Chaque palier peut débloquer des récompenses (rôles, credits, "
            "badges...). Tu peux aussi gagner des credits (la monnaie du bot) en "
            "travaillant, en tentant ta chance, ou en les faisant fructifier."
        ),
    },
    {
        "emoji": "🛒",
        "title": "Boutique & caisses",
        "restricted_on_yoru_guild": False,
        "text": (
            "Une boutique en jeu permet d'acheter et de revendre des objets avec tes "
            "credits, et des caisses à ouvrir (du commun jusqu'au très rare) offrent des "
            "récompenses aléatoires : bonus temporaires, objets, invocations, et plus."
        ),
    },
    {
        "emoji": "🎰",
        "title": "Casino",
        "restricted_on_yoru_guild": True,
        "text": (
            "Plusieurs mini-jeux de hasard (pile ou face, dés, machine à sous, roulette, "
            "blackjack, poker...) où tu peux miser tes credits pour tenter de les "
            "multiplier."
        ),
    },
    {
        "emoji": "🎲",
        "title": "Gacha",
        "restricted_on_yoru_guild": True,
        "text": (
            "Un système d'invocation façon gacha pour collectionner des personnages, "
            "avec des raretés croissantes et un suivi de ta collection."
        ),
    },
    {
        "emoji": "🗼",
        "title": "Tour RPG",
        "restricted_on_yoru_guild": True,
        "text": (
            "Un mode aventure solo : grimpe les étages d'une tour remplie de monstres, "
            "gagne de l'Or et débloque un codex au fil de ta progression."
        ),
    },
    {
        "emoji": "🏆",
        "title": "Profil & classements",
        "restricted_on_yoru_guild": False,
        "text": (
            "Un profil affiche ton niveau, tes badges et ta progression. Des classements "
            "(messages, vocal, XP) mettent en avant les membres les plus actifs."
        ),
    },
]

EMBED_COLOR = 0x5865F2

PREFIX_LEGEND = (
    "`$` économie (achats, jeux, gacha...) · `.` admin · `!` tout le reste"
)


def visible_player_categories(guild_id: int | None) -> list[dict]:
    if guild_id == YORU_DUPLICATE_RESTRICTED_GUILD_ID:
        return [c for c in PLAYER_CATEGORIES if not c["restricted_on_yoru_guild"]]
    return PLAYER_CATEGORIES


def visible_maj_sections(guild_id: int | None) -> list[dict]:
    if guild_id == YORU_DUPLICATE_RESTRICTED_GUILD_ID:
        return [s for s in MAJ_SECTIONS if not s["restricted_on_yoru_guild"]]
    return MAJ_SECTIONS


def visible_admin_categories(guild_id: int | None) -> list[dict]:
    if guild_id == YORU_DUPLICATE_RESTRICTED_GUILD_ID:
        return [c for c in ADMIN_CATEGORIES if not c["restricted_on_yoru_guild"]]
    return ADMIN_CATEGORIES


def build_maj_embed(guild_id: int | None) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Découvrir Colombina",
        description=(
            "Colombina est un bot Discord tout-en-un : progression, économie, jeux et "
            "collection. Voici, en quelques mots, ce qu'il propose :"
        ),
        color=EMBED_COLOR,
    )
    for section in visible_maj_sections(guild_id):
        embed.add_field(name=f"{section['emoji']} {section['title']}", value=section["text"], inline=False)
    embed.set_footer(text="Tape !help pour la liste détaillée des commandes.")
    return embed


def _build_embed(category: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"{category['emoji']} {category['label']}",
        description=category["description"],
        color=EMBED_COLOR,
    )
    for usage, desc in category["entries"]:
        embed.add_field(name=f"`{usage}`", value=desc, inline=False)
    return embed


def _build_overview_embed(categories: list[dict], title: str) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description="Choisis une catégorie dans le menu déroulant ci-dessous.",
        color=EMBED_COLOR,
    )
    for category in categories:
        embed.add_field(
            name=f"{category['emoji']} {category['label']}",
            value=category["description"],
            inline=False,
        )
    embed.set_footer(text=PREFIX_LEGEND)
    return embed


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, categories: list[dict], author_id: int) -> None:
        self.categories = categories
        self.author_id = author_id
        options = [
            discord.SelectOption(
                label=category["label"],
                value=category["key"],
                emoji=category["emoji"],
                description=category["description"][:100],
            )
            for category in categories
        ]
        super().__init__(placeholder="Choisis une catégorie...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Ce menu n'est pas le tien. Utilise `!help` pour en ouvrir un.",
                ephemeral=True,
            )
            return
        category = next(c for c in self.categories if c["key"] == self.values[0])
        await interaction.response.edit_message(embed=_build_embed(category))


class HelpView(discord.ui.View):
    def __init__(self, categories: list[dict], author_id: int) -> None:
        super().__init__(timeout=180)
        self.message: discord.Message | None = None
        self.add_item(HelpCategorySelect(categories, author_id))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class HelpCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id if ctx.guild is not None else None
        categories = visible_player_categories(guild_id)
        embed = _build_overview_embed(categories, "📖 Aide — Colombina")
        view = HelpView(categories, ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="maj")
    async def maj_cmd(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id if ctx.guild is not None else None
        await ctx.send(embed=build_maj_embed(guild_id))

    @commands.command(name="adminhelp")
    @commands.has_permissions(administrator=True)
    async def adminhelp_cmd(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id if ctx.guild is not None else None
        categories = visible_admin_categories(guild_id)
        embed = _build_overview_embed(categories, "🛠️ Aide administrateur")
        view = HelpView(categories, ctx.author.id)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot) -> None:
    await bot.add_cog(HelpCog(bot))
