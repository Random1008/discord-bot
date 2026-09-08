import importlib
import logging
import pkgutil

from discord.ext import commands

logger = logging.getLogger(__name__)


async def load_all_extensions(bot: commands.Bot, package: str = "cogs") -> list[str]:
    module = importlib.import_module(package)
    failed: list[str] = []

    for _finder, name, is_pkg in pkgutil.iter_modules(module.__path__, prefix=f"{package}."):
        if is_pkg:
            continue
        if name.rsplit(".", 1)[-1].startswith("_"):
            continue
        try:
            await bot.load_extension(name)
        except commands.ExtensionError:
            logger.exception("Failed to load extension %s", name)
            failed.append(name)

    return failed
