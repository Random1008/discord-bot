import asyncio
import random

import discord
from discord.ext import commands

import services.gacha_db as db
from models.economy import Economy
from services.admin_actions import reset_gacha
from services.admin_permission import can_bypass
from services.economy import add_balance
from services.gacha_actions import perform_pulls
from services.gacha_logic import CHARACTERS_BY_RARITY, PullResult, RARITY_ORDER, RATES
from services.users import get_or_create_user

GACHA_PULL_COST = 100
GACHA_MULTI_COST = 900
GACHA_MULTI_COUNT = 10

GACHA_RARITY_EMOJI = {
    "Commun": "🟢",
    "Rare": "🔵",
    "Épique": "🟣",
    "Légendaire": "🟠",
    "Mythique": "🔴",
    "Secret": "🌑",
}

_CANONICAL_CHARACTER_NAMES = {
    name.lower(): name for names in CHARACTERS_BY_RARITY.values() for name in names
}


def resolve_character_name(raw: str) -> str | None:
    return _CANONICAL_CHARACTER_NAMES.get(raw.strip().lower())


def build_character_list_embed() -> discord.Embed:
    embed = discord.Embed(title="🎲 Personnages du Gacha", color=discord.Color.blurple())
    for rarity in RARITY_ORDER:
        characters = CHARACTERS_BY_RARITY[rarity]
        emoji = GACHA_RARITY_EMOJI.get(rarity, "")
        value = "\n".join(f"• {name}" for name in characters) if characters else "*Aucun personnage pour l'instant.*"
        embed.add_field(name=f"{emoji} {rarity} ({RATES[rarity] * 100:.1f}%)", value=value, inline=False)
    return embed


class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._pull_locks: dict[str, asyncio.Lock] = {}

    def _session(self):
        return self.bot.session_factory()

    def _lock_for(self, key: str) -> asyncio.Lock:
        return self._pull_locks.setdefault(key, asyncio.Lock())

    async def _get_balance(self, session, guild_id: int, user_id: int) -> int:
        economy = await session.get(Economy, (guild_id, user_id))
        return economy.balance if economy is not None else 0

    @commands.group(name="gacha", invoke_without_command=True)
    async def gacha(self, ctx: commands.Context) -> None:
        await ctx.send(
            "Sous-commandes : `$gacha pull`, `$gacha multi`, `$gacha pity`,"
            " `$gacha rates`, `$gacha list`, `$gacha inventory`, `$gacha history`, `$gacha wishlist`"
        )

    @gacha.command(name="list")
    async def gacha_list(self, ctx: commands.Context) -> None:
        await ctx.send(embed=build_character_list_embed())

    @gacha.command(name="rates")
    async def gacha_rates(self, ctx: commands.Context) -> None:
        lines = [f"{rarity} : {RATES[rarity] * 100:.1f}%" for rarity in RARITY_ORDER]
        await ctx.send(
            f"🎲 Taux de pull (coût : {GACHA_PULL_COST} credits,"
            f" multi x{GACHA_MULTI_COUNT} : {GACHA_MULTI_COST} credits)\n"
            + "\n".join(lines)
        )

    @gacha.command(name="pity")
    async def gacha_pity(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            state = await db.get_gacha_state(session, guild_id, ctx.author.id)
            await session.commit()
        await ctx.send(
            "🎯 Pity actuel :\n"
            f"Épique dans {max(0, 10 - state['pulls_since_epique'])} pulls\n"
            f"Légendaire dans {max(0, 30 - state['pulls_since_legendaire'])} pulls\n"
            f"Mythique dans {max(0, 100 - state['pulls_since_mythique'])} pulls\n"
            f"Fragments : {state['fragments']}"
        )

    @gacha.command(name="inventory")
    async def gacha_inventory(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            characters = await db.get_characters(session, guild_id, ctx.author.id)
            state = await db.get_gacha_state(session, guild_id, ctx.author.id)
            await session.commit()
        if not characters:
            await ctx.send(f"Aucun personnage. Fragments : {state['fragments']}. Utilise `$gacha pull`.")
            return
        lines = [f"- {c['character_name']} x{c['count']}" for c in characters]
        await ctx.send("\n".join(lines) + f"\n\nFragments : {state['fragments']}")

    async def _do_pull(self, session, guild_id: int, user_id: int, rng) -> PullResult:
        results = await perform_pulls(session, guild_id, user_id, 1, rng)
        return results[0]

    async def _format_result(self, session, guild_id: int, user_id: int, result: PullResult) -> str:
        if result.character is not None:
            msg = f"🎉 {result.rarity} : **{result.character}**"
        else:
            msg = f"🌑 {result.rarity} !"
        if result.bonus_fragments > 0:
            msg += f" (+{result.bonus_fragments} fragments)"
        wishlist = await db.get_wishlist_character(session, guild_id, user_id)
        if wishlist is not None and result.character == wishlist:
            msg += " 🌟 C'était ton personnage de wishlist !"
        return msg

    @gacha.command(name="pull")
    async def gacha_pull_cmd(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        async with self._lock_for(f"{guild_id}:{ctx.author.id}"):
            async with self._session() as session:
                bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
                await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
                bal = await self._get_balance(session, guild_id, ctx.author.id)
                if not bypass and bal < GACHA_PULL_COST:
                    await ctx.send(f"❌ Pas assez de credits ({bal}/{GACHA_PULL_COST}).")
                    return
                if not bypass:
                    await add_balance(session, guild_id, ctx.author.id, -GACHA_PULL_COST)
                result = await self._do_pull(session, guild_id, ctx.author.id, random.Random())
                message = await self._format_result(session, guild_id, ctx.author.id, result)
                await session.commit()
            if bypass:
                message += " 🔓 [bypass admin : coût non débité]"
            await ctx.send(message)

    @gacha.command(name="multi")
    async def gacha_multi(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        async with self._lock_for(f"{guild_id}:{ctx.author.id}"):
            async with self._session() as session:
                bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
                await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
                bal = await self._get_balance(session, guild_id, ctx.author.id)
                if not bypass and bal < GACHA_MULTI_COST:
                    await ctx.send(f"❌ Pas assez de credits ({bal}/{GACHA_MULTI_COST}).")
                    return
                if not bypass:
                    await add_balance(session, guild_id, ctx.author.id, -GACHA_MULTI_COST)
                rng = random.Random()
                messages = []
                for _ in range(GACHA_MULTI_COUNT):
                    result = await self._do_pull(session, guild_id, ctx.author.id, rng)
                    messages.append(await self._format_result(session, guild_id, ctx.author.id, result))
                await session.commit()
            if bypass:
                messages.append("🔓 [bypass admin : coût non débité]")
            await ctx.send("\n".join(messages))

    @gacha.command(name="history")
    async def gacha_history(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            history = await db.get_gacha_history(session, guild_id, ctx.author.id)
            await session.commit()
        if not history:
            await ctx.send("Aucun historique. Utilise `$gacha pull`.")
            return
        lines = [
            f"- {h['rarity']}" + (f" : **{h['character_name']}**" if h["character_name"] else "")
            for h in history
        ]
        await ctx.send("📜 Historique des derniers tirages :\n" + "\n".join(lines))

    @gacha.group(name="wishlist", invoke_without_command=True)
    async def gacha_wishlist(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            wishlist = await db.get_wishlist_character(session, guild_id, ctx.author.id)
            await session.commit()
        if wishlist is None:
            await ctx.send("Aucun personnage en wishlist. Utilise `$gacha wishlist set <nom>`.")
            return
        await ctx.send(f"🌟 Personnage en wishlist : **{wishlist}**.")

    @gacha_wishlist.command(name="set")
    async def gacha_wishlist_set(self, ctx: commands.Context, *, character_name: str) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            await db.set_wishlist_character(session, guild_id, ctx.author.id, character_name)
            await session.commit()
        await ctx.send(f"🌟 Wishlist mise à jour : **{character_name}**.")

    @gacha_wishlist.command(name="clear")
    async def gacha_wishlist_clear(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await db.set_wishlist_character(session, guild_id, ctx.author.id, None)
            await session.commit()
        await ctx.send("Wishlist vidée.")

    @gacha.command(name="add")
    @commands.has_permissions(administrator=True)
    async def gacha_add(self, ctx: commands.Context, membre: discord.Member, *, nom: str) -> None:
        character_name = resolve_character_name(nom)
        if character_name is None:
            await ctx.send(f"Aucun personnage nommé **{nom}** (voir `$gacha list`).")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await db.add_character(session, guild_id, membre.id, character_name)
            await session.commit()

        await ctx.send(f"🛠️ **{character_name}** ajouté à la collection de {membre.display_name}.")

    @gacha.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def gacha_remove(self, ctx: commands.Context, membre: discord.Member, *, nom: str) -> None:
        character_name = resolve_character_name(nom) or nom.strip()

        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            removed = await db.remove_character(session, guild_id, membre.id, character_name)
            await session.commit()

        if removed:
            await ctx.send(f"🛠️ Une copie de **{character_name}** retirée à {membre.display_name}.")
        else:
            await ctx.send(f"{membre.display_name} ne possède pas **{character_name}**.")

    @gacha.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def gacha_reset(self, ctx: commands.Context, membre: discord.Member) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, membre.id, membre.display_name)
            await reset_gacha(session, guild_id, membre.id)
            await session.commit()

        await ctx.send(
            f"🛠️ Collection gacha de {membre.display_name} entièrement réinitialisée "
            "(personnages, pity, fragments, historique, wishlist, boost de taux)."
        )


async def setup(bot) -> None:
    await bot.add_cog(GachaCog(bot))
