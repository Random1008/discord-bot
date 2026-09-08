import asyncio
import logging
import random

import discord
from discord.ext import commands

from config.settings import ADMIN_PERMISSION_ROLE_ID, YORU_DUPLICATE_RESTRICTED_GUILD_ID, settings
from database.engine import AsyncSessionLocal
from services.admin_permission import has_permission
from services.bot_access import is_blocked
from utils.cog_loader import load_all_extensions
from utils.logging import configure_logging
from utils.redis_client import create_redis_client, ping

logger = logging.getLogger(__name__)


class WrongPrefixScope(commands.CheckFailure):
    def __init__(self, expected_prefix: str) -> None:
        self.expected_prefix = expected_prefix
        super().__init__(f"Cette commande s'utilise avec le préfixe {expected_prefix}")


class FeatureUnavailableOnGuild(commands.CheckFailure):
    pass


class UserBlocked(commands.CheckFailure):
    pass


class MissingAdminPermission(commands.CheckFailure):
    pass


class DebtBlocked(commands.CheckFailure):
    pass


def _is_yoru_duplicate_command(ctx: commands.Context) -> bool:
    module = type(ctx.cog).__module__ if ctx.cog is not None else ""
    return (
        module.startswith("cogs.tour")
        or module.startswith("cogs.casino")
        or module.startswith("cogs.gacha")
    )



# Commandes interdites quand le solde est < 1 (endettement). Les commandes
# $balance, $pay, $daily, $work, $weekly, $monthly restent utilisables pour
# se sortir du trou.
DEBT_BLOCKED_MODULE_PREFIXES = {"cogs.casino", "cogs.gacha", "cogs.crates", "cogs.underworld", "cogs.proces"}
DEBT_BLOCKED_COMMAND_NAMES = {"buy", "invest", "crime", "rob"}

# Commandes hébergées dans un module « argent » (donc préfixe `$` par défaut) mais
# qui ne sont PAS des commandes d'argent : elles utilisent le préfixe `!` et ne
# sont pas bloquées quand le joueur est endetté.
NON_MONEY_COMMAND_NAMES = {"complice"}


def _is_money_command(ctx: commands.Context) -> bool:
    module = type(ctx.cog).__module__ if ctx.cog is not None else ""
    return (
        module.startswith("cogs.economy")
        or module.startswith("cogs.market")
        or module.startswith("cogs.crates")
        or module.startswith("cogs.casino")
        or module.startswith("cogs.crime")
        or module.startswith("cogs.invest")
        or module.startswith("cogs.gacha")
        or module.startswith("cogs.underworld")
        or module.startswith("cogs.proces")
    )


# Commandes admin (protégées par @commands.has_permissions(administrator=True))
# regroupées ici : elles ne répondent qu'au préfixe . — jamais à !/$.
ADMIN_COMMAND_NAMES = {
    "adminhelp",
    "tourpanel",
    "setlevel",
    "addxp",
    "removexp",
    "addcoins",
    "removecoins",
    "resetuser",
    "reset",
    "money",
    "money add",
    "money remove",
    "money reset",
    "tower",
    "tower set",
    "tower add",
    "tower remove",
    "tower reset",
    "gacha add",
    "gacha remove",
    "gacha reset",
    "givereward",
    "event-participation",
    "unxp",
    "xp",
    "config",
    "market",
    "market add",
    "market remove",
    "market edit",
    "market list",
    "setup",
    "setup welcome",
    "setup proces",
    "act",
    "bot",
    "bot on",
    "bot off",
    "permadd",
    "permremove",
    "proces end",
}

# Commandes admin qui gèrent la whitelist elle-même : exemptées uniquement de
# la vérification "entrée whitelist" ci-dessous (sinon personne ne pourrait
# jamais les utiliser la première fois) — le rôle reste requis, et
# cogs/admin.py les restreint en plus à ADMIN_PERMISSION_OWNER_ID.
ADMIN_PERMISSION_BOOTSTRAP_COMMANDS = {"permadd", "permremove"}


# Réponses humoristiques quand un message commence par `$` mais n'est pas une
# commande reconnue. {name} est remplacé par le nom de commande tapé.
UNKNOWN_DOLLAR_COMMAND_PHRASES = [
    "Ah oui, la commande `{name}`… millésime 2026, introuvable même sur Google.",
    "T'as demandé un truc qui n'existe pas, même le chef vient de faire une mise à jour.",
    "Cette commande n'existe tellement pas qu'elle vient de porter plainte pour usurpation d'identité.",
    "J'admire ta confiance : inventer une commande et la demander comme si c'était au menu.",
    'Le serveur : "Désolé, on ne fait pas ça."',
    'Même ChatGPT vient de répondre : "Frérot, je connais pas."',
    "Cette commande est tellement rare qu'elle n'existe que dans ton imagination.",
    "T'as pas fait une erreur de commande, t'as créé un nouveau DLC.",
    "Attends, je vais demander au chef s'il peut télécharger ta commande.",
    "Félicitations, tu viens d'inventer le plat du jour. Dommage qu'il n'existe pas.",
]


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix=["!", "$", ".", "+"], intents=intents, help_command=None)
    bot.session_factory = AsyncSessionLocal

    @bot.check
    async def enforce_prefix_scope(ctx: commands.Context) -> bool:
        if ctx.guild is not None and ctx.guild.id == YORU_DUPLICATE_RESTRICTED_GUILD_ID and _is_yoru_duplicate_command(ctx):
            raise FeatureUnavailableOnGuild()

        command_name = ctx.command.qualified_name if ctx.command is not None else None

        if command_name in ADMIN_COMMAND_NAMES:
            if ctx.prefix != ".":
                raise WrongPrefixScope(".")
            return True
        if ctx.prefix in (".", "+"):
            return False
        expected = "$" if (_is_money_command(ctx) and command_name not in NON_MONEY_COMMAND_NAMES) else "!"
        if ctx.prefix != expected:
            raise WrongPrefixScope(expected)
        return True

    @bot.check
    async def enforce_bot_access(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return True
        async with bot.session_factory() as session:
            if await is_blocked(session, ctx.guild.id, ctx.author.id):
                raise UserBlocked()
        return True


    @bot.check
    async def enforce_no_debt_gambling(ctx: commands.Context) -> bool:
        """Bloque les commandes de gambling quand le solde est inferieur a 1."""
        if ctx.guild is None:
            return True
        command_name = ctx.command.qualified_name if ctx.command is not None else None
        if command_name in ADMIN_COMMAND_NAMES:
            return True
        if command_name in NON_MONEY_COMMAND_NAMES:
            return True
        module = type(ctx.cog).__module__ if ctx.cog is not None else ""
        blocked_by_module = any(module.startswith(p) for p in DEBT_BLOCKED_MODULE_PREFIXES)
        blocked_by_name = command_name in DEBT_BLOCKED_COMMAND_NAMES
        if not blocked_by_module and not blocked_by_name:
            return True
        from shared.db import services as shared_services
        async with bot.session_factory() as session:
            balance = await shared_services.get_balance(session, ctx.guild.id, ctx.author.id)
        if balance < 1:
            debt = abs(balance) if balance < 0 else 0
            msg = f"💸 Tu es endetté" + (f" de **{debt}** credits" if debt > 0 else "") + ". Rembourse tes dettes avec `$daily`, `$work` ou `$pay` avant de pouvoir jouer."
            await ctx.send(msg)
            return False
        return True

    @bot.check
    @bot.check
    async def enforce_admin_permission(ctx: commands.Context) -> bool:
        command_name = ctx.command.qualified_name if ctx.command is not None else None
        if command_name not in ADMIN_COMMAND_NAMES:
            return True
        if ctx.guild is None:
            return False
        author_roles = getattr(ctx.author, "roles", [])
        if not any(role.id == ADMIN_PERMISSION_ROLE_ID for role in author_roles):
            raise MissingAdminPermission()
        if command_name in ADMIN_PERMISSION_BOOTSTRAP_COMMANDS:
            return True
        async with bot.session_factory() as session:
            if not await has_permission(session, ctx.guild.id, ctx.author.id):
                raise MissingAdminPermission()
        return True

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            if ctx.prefix == "$":
                name = ctx.invoked_with or ""
                await ctx.send(random.choice(UNKNOWN_DOLLAR_COMMAND_PHRASES).format(name=name))
                return
            return
        if isinstance(error, FeatureUnavailableOnGuild):
            return
        if isinstance(error, UserBlocked):
            return
        if isinstance(error, WrongPrefixScope):
            await ctx.send(f"❌ Cette commande s'utilise avec `{error.expected_prefix}`, pas `{ctx.prefix}`.")
            return
        if isinstance(error, commands.CheckFailure) and ctx.prefix in (".", "+"):
            return
        logger.exception("Erreur sur la commande %s", ctx.command, exc_info=error)

    return bot


async def main() -> None:
    configure_logging(level=settings.log_level)

    redis_client = create_redis_client()
    if not await ping(redis_client):
        logger.error("Redis is not reachable at %s", settings.redis_url)

    bot = create_bot()

    @bot.event
    async def on_ready() -> None:
        logger.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else None)

    failed = await load_all_extensions(bot)
    if failed:
        logger.warning("Extensions failed to load: %s", failed)

    await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
