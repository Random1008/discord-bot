import discord
from discord.ext import commands

from utils.cog_loader import load_all_extensions


async def test_load_all_extensions_is_tolerant_of_failures(tmp_path, monkeypatch):
    package_dir = tmp_path / "fixture_cogs"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    (package_dir / "good_cog.py").write_text(
        "from discord.ext import commands\n\n"
        "class GoodCog(commands.Cog):\n"
        "    pass\n\n"
        "async def setup(bot):\n"
        "    await bot.add_cog(GoodCog())\n"
    )
    (package_dir / "bad_cog.py").write_text(
        "async def setup(bot):\n"
        "    raise RuntimeError('boom')\n"
    )

    monkeypatch.syspath_prepend(str(tmp_path))

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)

    failed = await load_all_extensions(bot, package="fixture_cogs")

    assert failed == ["fixture_cogs.bad_cog"]
    assert bot.get_cog("GoodCog") is not None

    await bot.close()
