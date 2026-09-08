import asyncio
import random

import discord
from discord.ext import commands

from models.economy import Economy
from services.casino import (
    add_to_jackpot,
    blackjack_hand_value,
    calc_blackjack_outcome,
    calc_craps,
    calc_dice,
    calc_highlow,
    calc_poker,
    calc_roulette,
    calc_slots,
    calc_wheel,
    draw_card,
    draw_poker_hand,
    evaluate_poker_hand,
    get_casino_stats,
    get_jackpot_pool,
    record_casino_result,
    reset_jackpot,
    roll_craps_dice,
    roll_highlow_card,
)
from services.admin_permission import can_bypass
from services.economy import add_balance
from services.effects import consume_one_shot, get_active_multiplier
from services.users import get_or_create_user

SYMBOLS = ["🍒", "🍊", "🍋", "💎", "7️⃣"]
WEIGHTS = [35, 30, 25, 7, 3]
JACKPOT_WIN_CHANCE = 0.01

BYPASS_SUFFIX = " (bypass admin : mise non débitée)"
INSURANCE_NOTE = "🔒 Assurance : mise remboursée"
DOUBLE_WIN_NOTE = "✨ Double gain appliqué"
FREE_BET_NOTE = "🎟️ Pari gratuit : mise non débitée"


class CasinoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    async def _get_balance(self, session, guild_id: int, user_id: int) -> int:
        economy = await session.get(Economy, (guild_id, user_id))
        return economy.balance if economy is not None else 0

    async def _settle(
        self, session, guild_id: int, user_id: int, mise: int, gain: int, bypass: bool
    ) -> tuple[int, int, list[str]]:
        notes: list[str] = []
        if not bypass:
            if gain > mise and await consume_one_shot(session, guild_id, user_id, "casino_double_win"):
                gain = mise + (gain - mise) * 2
                notes.append(DOUBLE_WIN_NOTE)
            elif gain < mise and await consume_one_shot(session, guild_id, user_id, "casino_insurance"):
                gain = mise
                notes.append(INSURANCE_NOTE)

        free_bet = not bypass and await consume_one_shot(session, guild_id, user_id, "casino_free_bet")
        if free_bet:
            notes.append(FREE_BET_NOTE)

        if bypass or free_bet:
            new_balance = await add_balance(session, guild_id, user_id, gain)
        else:
            new_balance = await add_balance(session, guild_id, user_id, gain - mise)
        return new_balance, gain, notes

    @staticmethod
    def _effect_suffix(bypass: bool, notes: list[str]) -> str:
        if bypass:
            return BYPASS_SUFFIX
        return "".join(f"\n{note}" for note in notes)

    @commands.command(name="coinflip")
    async def coinflip(self, ctx: commands.Context, mise: int, choix: str = "pile", *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return
        choix = choix.lower()
        if choix not in ("pile", "face"):
            await ctx.send("❌ Choisis `pile` ou `face`.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            result = random.choice(["pile", "face"])
            win = result == choix
            gain = 2 * mise if win else 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title=f"🪙 Coin Flip — {result.capitalize()}",
            description=(
                f"{'✅ Gagné' if win else '❌ Perdu'} **{mise:,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if win else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="slots")
    async def slots(self, ctx: commands.Context, mise: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            s1, s2, s3 = random.choices(SYMBOLS, weights=WEIGHTS, k=3)
            gain, msg = calc_slots(s1, s2, s3, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title=f"🎰 Slots — {s1} {s2} {s3}",
            description=(
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="dice")
    async def dice(self, ctx: commands.Context, mise: int, guess: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return
        if not 1 <= guess <= 6:
            await ctx.send("❌ Choisis un nombre entre 1 et 6.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rolled = random.randint(1, 6)
            gain, msg = calc_dice(guess, rolled, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🎲 Dice",
            description=(
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="roulette")
    async def roulette(self, ctx: commands.Context, mise: int, couleur: str, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return
        couleur = couleur.lower()
        if couleur not in ("rouge", "noir", "vert"):
            await ctx.send("❌ Choisis `rouge`, `noir` ou `vert`.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rolled_number = random.randint(0, 36)
            gain, msg = calc_roulette(couleur, rolled_number, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🎡 Roulette",
            description=(
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="blackjack")
    async def blackjack(self, ctx: commands.Context, mise: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return

            rng = random.Random()
            player_cards = [draw_card(rng), draw_card(rng)]
            dealer_cards = [draw_card(rng), draw_card(rng)]

            def check(m: discord.Message) -> bool:
                return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ("hit", "stand")

            while blackjack_hand_value(player_cards) < 21:
                await ctx.send(
                    f"🃏 Ta main : {player_cards} (total {blackjack_hand_value(player_cards)})."
                    " Réponds `hit` ou `stand`."
                )
                try:
                    reply = await self.bot.wait_for("message", check=check, timeout=30)
                except asyncio.TimeoutError:
                    await ctx.send("⏳ Pas de réponse, tu restes (`stand`).")
                    break
                if reply.content.lower() == "hit":
                    player_cards.append(draw_card(rng))
                else:
                    break

            player_total = blackjack_hand_value(player_cards)
            if player_total <= 21:
                while blackjack_hand_value(dealer_cards) < 17:
                    dealer_cards.append(draw_card(rng))
            dealer_total = blackjack_hand_value(dealer_cards)

            multiplier, msg = calc_blackjack_outcome(player_total, dealer_total)
            gain = int(mise * multiplier)
            is_win = gain > 0 if multiplier != 1.0 else False
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, is_win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🃏 Blackjack",
            description=(
                f"Ta main : {player_cards} (total {player_total})\n"
                f"Main du croupier : {dealer_cards} (total {dealer_total})\n"
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="jackpot")
    async def jackpot(self, ctx: commands.Context, mise: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return

            chance_boost = await get_active_multiplier(session, guild_id, ctx.author.id, "casino_jackpot_chance_boost")
            won = random.random() < JACKPOT_WIN_CHANCE * chance_boost
            if won:
                pool = await get_jackpot_pool(session, guild_id)
                await reset_jackpot(session, guild_id)
                new_bal = await add_balance(session, guild_id, ctx.author.id, pool)
                await record_casino_result(session, guild_id, ctx.author.id, mise, pool, True, True)
                await session.commit()
                embed = discord.Embed(
                    title="🎉 JACKPOT !",
                    description=(
                        f"Tu remportes la cagnotte : **{pool:,} credits** !"
                        f" → Solde : **{new_bal:,}**{BYPASS_SUFFIX if bypass else ''}"
                    ),
                    color=0xF1C40F,
                )
            else:
                new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, 0, bypass)
                pool = await add_to_jackpot(session, guild_id, mise)
                await record_casino_result(session, guild_id, ctx.author.id, mise, gain, False, False)
                await session.commit()
                embed = discord.Embed(
                    title="🎰 Jackpot",
                    description=(
                        f"❌ Perdu. **{mise:,} credits** ajoutés à la cagnotte du serveur"
                        f" (total : **{pool:,}**). → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
                    ),
                    color=0xE74C3C,
                )
        await ctx.send(embed=embed)

    @commands.command(name="highlow")
    async def highlow(self, ctx: commands.Context, mise: int, guess: str, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return
        guess = guess.lower()
        if guess not in ("plus", "moins"):
            await ctx.send("❌ Choisis `plus` ou `moins`.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rng = random.Random()
            first_card = roll_highlow_card(rng)
            next_card = roll_highlow_card(rng)
            gain, msg = calc_highlow(first_card, guess, next_card, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🔀 High-Low",
            description=(
                f"Carte de départ : **{first_card}**, tu paries **{guess}**\n"
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="poker")
    async def poker(self, ctx: commands.Context, mise: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rng = random.Random()
            hand = draw_poker_hand(rng)
            category = evaluate_poker_hand(hand)
            gain, msg = calc_poker(category, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        hand_text = ", ".join(f"{rank}{suit}" for rank, suit in hand)
        embed = discord.Embed(
            title="🂡 Poker",
            description=(
                f"Main : {hand_text}\n"
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="roue")
    async def roue(self, ctx: commands.Context, mise: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rng = random.Random()
            gain, msg = calc_wheel(rng, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🎡 Roue de la Fortune",
            description=(
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="craps")
    async def craps(self, ctx: commands.Context, mise: int, guess: str, *args: str) -> None:
        wants_bypass = "bypass" in args
        if mise <= 0:
            await ctx.send("❌ La mise doit être positive.")
            return
        guess = guess.lower()
        if guess not in ("sept", "plus", "moins"):
            await ctx.send("❌ Choisis `sept`, `plus` ou `moins`.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < mise:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            rng = random.Random()
            d1, d2 = roll_craps_dice(rng)
            gain, msg = calc_craps(d1, d2, guess, mise)
            win = gain > 0
            new_bal, gain, notes = await self._settle(session, guild_id, ctx.author.id, mise, gain, bypass)
            await record_casino_result(session, guild_id, ctx.author.id, mise, gain, win, False)
            await session.commit()

        delta = gain - mise
        embed = discord.Embed(
            title="🎲 Craps",
            description=(
                f"**{msg}**\n"
                f"{'Gain' if delta >= 0 else 'Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{self._effect_suffix(bypass, notes)}"
            ),
            color=0x2ECC71 if delta >= 0 else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="casinostats")
    async def casino_stats(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            stats = await get_casino_stats(session, guild_id, ctx.author.id)
            await session.commit()

        embed = discord.Embed(
            title="🎰 Statistiques casino",
            color=0x5865F2,
        )
        embed.add_field(name="Total misé", value=f"{stats['total_wagered']:,}", inline=True)
        embed.add_field(name="Total gagné", value=f"{stats['total_won']:,}", inline=True)
        embed.add_field(name="Victoires", value=str(stats["wins_count"]), inline=True)
        embed.add_field(name="Jackpots remportés", value=str(stats["jackpots_won"]), inline=True)
        await ctx.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(CasinoCog(bot))
