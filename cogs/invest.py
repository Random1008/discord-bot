import random
from datetime import datetime, timezone

import discord
from discord.ext import commands

from models.economy import Economy
from services.admin_permission import can_bypass
from services.economy import add_balance
from services.effects import get_active_multiplier
from shared.db import services as shared_services
from services.invest import (
    INVEST_DAILY_LIMIT,
    INVEST_MAX_AMOUNT,
    calculate_return,
    get_invest_usage,
    get_market_index,
    get_market_history,
    purge_old_market_history,
    record_market_history,
    register_invest,
    set_market_index,
    update_market_index,
)
from services.users import get_or_create_user

WEEKLY_AMOUNT = 2000
WEEKLY_COOLDOWN = 604800
MONTHLY_AMOUNT = 8000
MONTHLY_COOLDOWN = 2592000


class InvestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    @staticmethod
    def _now():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)

    async def _get_balance(self, session, guild_id: int, user_id: int) -> int:
        economy = await session.get(Economy, (guild_id, user_id))
        return economy.balance if economy is not None else 0

    @commands.command(name="weekly")
    async def weekly(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        key = f"{ctx.author.id}:{guild_id}"

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            last_w = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_weekly_at")
            if not bypass and last_w is not None:
                elapsed = (self._now() - last_w.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < WEEKLY_COOLDOWN:
                    rem = WEEKLY_COOLDOWN - int(elapsed)
                    d, r = divmod(rem, 86400)
                    h, r2 = divmod(r, 3600)
                    await ctx.send(f"⏳ Weekly déjà récupéré. Reviens dans **{d}j{h}h**.")
                    return
            await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "last_weekly_at", self._now())

            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            coins_boost = await get_active_multiplier(session, guild_id, ctx.author.id, "coins_boost")
            amount = round(WEEKLY_AMOUNT * coins_boost)
            new_bal = await add_balance(session, guild_id, ctx.author.id, amount)
            await session.commit()

        suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
        embed = discord.Embed(
            title="📅 Weekly récupéré !",
            description=f"+**{amount} credits** → Solde : **{new_bal:,} credits**{suffix}",
            color=0xF1C40F,
        )
        await ctx.send(embed=embed)

    @commands.command(name="monthly")
    async def monthly(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        key = f"{ctx.author.id}:{guild_id}"

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            last_m = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_monthly_at")
            if not bypass and last_m is not None:
                elapsed = (self._now() - last_m.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < MONTHLY_COOLDOWN:
                    rem = MONTHLY_COOLDOWN - int(elapsed)
                    d, r = divmod(rem, 86400)
                    await ctx.send(f"⏳ Monthly déjà récupéré. Reviens dans **{d}j**.")
                    return
            await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "last_monthly_at", self._now())

            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            coins_boost = await get_active_multiplier(session, guild_id, ctx.author.id, "coins_boost")
            amount = round(MONTHLY_AMOUNT * coins_boost)
            new_bal = await add_balance(session, guild_id, ctx.author.id, amount)
            await session.commit()

        suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
        embed = discord.Embed(
            title="🗓️ Monthly récupéré !",
            description=f"+**{amount} credits** → Solde : **{new_bal:,} credits**{suffix}",
            color=0xF1C40F,
        )
        await ctx.send(embed=embed)

    @commands.command(name="invest")
    async def invest(self, ctx: commands.Context, amount: int, *args: str) -> None:
        wants_bypass = "bypass" in args
        if amount <= 0:
            await ctx.send("❌ Le montant doit être positif.")
            return
        if amount > INVEST_MAX_AMOUNT:
            await ctx.send(f"❌ L'investissement est plafonné à **{INVEST_MAX_AMOUNT:,} credits**.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            bal = await self._get_balance(session, guild_id, ctx.author.id)
            if not bypass and bal < amount:
                await ctx.send(f"❌ Solde insuffisant ({bal:,} credits).")
                return
            if not bypass:
                used = await get_invest_usage(session, guild_id, ctx.author.id)
                if used >= INVEST_DAILY_LIMIT:
                    await ctx.send(
                        f"❌ Tu as atteint la limite de **{INVEST_DAILY_LIMIT} investissements** aujourd'hui. Reviens demain !"
                    )
                    return
            market_index = await get_market_index(session, guild_id)
            rng = random.Random()
            proceeds = calculate_return(amount, rng, market_index)
            delta = proceeds - amount
            new_bal = await add_balance(session, guild_id, ctx.author.id, proceeds if bypass else delta)
            if not bypass:
                await register_invest(session, guild_id, ctx.author.id)
            new_index = update_market_index(market_index, rng)
            await set_market_index(session, guild_id, new_index)
            await session.commit()

        suffix = " (bypass admin : mise non débitée)" if bypass else ""
        won = delta > 0
        embed = discord.Embed(
            title="📈 Investissement",
            description=(
                f"Mise : {amount:,} credits → retour : **{proceeds:,} credits**\n"
                f"{'💥 Gain' if won else '💸 Perte'} net : **{delta:+,} credits**"
                f" → Solde : **{new_bal:,}**{suffix}"
            ),
            color=0x2ECC71 if won else 0xE74C3C,
        )
        await ctx.send(embed=embed)

    @commands.command(name="stocks")
    async def stocks(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        rng = __import__("random")

        async with self._session() as session:
            index = await get_market_index(session, guild_id)

            # 30% de chance d"erreur
            display_index = index
            accurate = True
            if rng.random() < 0.30:
                accurate = False
                offset = rng.uniform(-0.30, 0.30)
                display_index = round(max(0.50, min(1.50, index + offset)), 2)

            # Enregistrer dans l"historique
            await record_market_history(session, guild_id, display_index, accurate)
            await purge_old_market_history(session, guild_id, keep=100)

            # Récupérer l"historique pour le graphique
            history = await get_market_history(session, guild_id, limit=25)
            await session.commit()

        # Construire la courbe : interpolation sur 40 colonnes pour
        # donner l'illusion d'un marche continu.
        CHARS = ["▁","▂","▃","▄","▅","▆","▇","█"]
        WIDTH = 40
        real_line = ""
        est_line = ""
        if history:
            for j in range(WIDTH):
                src_idx = (j / (WIDTH - 1)) * (len(history) - 1) if len(history) > 1 else 0
                lo = int(src_idx)
                hi = min(lo + 1, len(history) - 1)
                frac = src_idx - lo
                val = history[lo]["index_value"] * (1 - frac) + history[hi]["index_value"] * frac
                accurate = history[lo]["is_accurate"] if frac < 0.5 else history[hi]["is_accurate"]
                idx = max(0, min(7, int((val - 0.5) / (1.5 - 0.5) * 7)))
                char = CHARS[idx]
                if accurate:
                    real_line += char
                    est_line += " "
                else:
                    real_line += " "
                    est_line += "·"

        legend = "█ reel  · estime"
        chart = f"```\n{real_line}\n{est_line}\n{legend}```" if any(ch != " " for ch in est_line) else f"```\n{real_line}\n```"
        trend = "📈 en hausse" if display_index > 1.0 else ("📉 en baisse" if display_index < 1.0 else "➡️ stable")
        warning = "\n⚠️ *Estimation incertaine (±30%)*" if not accurate else ""
        label = "Indice de marché" if accurate else "Indice estimé"

        embed = __import__("discord").Embed(
            title="📊 Indice de marché",
            description=f"**{label}** : {display_index:.2f} ({trend}){warning}\n{chart}",
            color=0xF1C40F if display_index > 1.0 else (0xE74C3C if display_index < 1.0 else 0x95A5A6),
        )
        await ctx.send(embed=embed)


async def setup(bot) -> None:
    await bot.add_cog(InvestCog(bot))
