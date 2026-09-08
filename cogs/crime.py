from datetime import datetime, timezone, timedelta
import random

import discord
from discord.ext import commands

from models.economy import Economy
from services.admin_permission import can_bypass
from services.economy import add_balance
from shared.db import services as shared_services
from services.users import get_or_create_user

CRIME_ACTIONS = [
    "pickpocketing",
    "cambriolage",
    "arnaque téléphonique",
    "vol de voiture",
    "vente de contrefaçons",
]

CRIME_COOLDOWN = 3600
ROB_COOLDOWN = 3600
ROB_TARGET_MIN_BALANCE = 100
PRISON_DURATION = 1800
CRIME_SUCCESS_CHANCE = 0.6
CRIME_FINE = 50
ROB_SUCCESS_CHANCE = 0.5

def _fmt_duration(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}min"
    if m:
        return f"{m}min {s}s"
    return f"{s}s"

class CrimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    async def _get_balance(self, session, guild_id: int, user_id: int) -> int:
        economy = await session.get(Economy, (guild_id, user_id))
        return economy.balance if economy is not None else 0

    @commands.command(name="crime")
    async def crime(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        key = f"{ctx.author.id}:{guild_id}"

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            prison_until = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "prison_until")
            if not bypass and prison_until is not None:
                prison_until = prison_until.replace(tzinfo=timezone.utc) if prison_until.tzinfo is None else prison_until
                if datetime.now(timezone.utc) < prison_until:
                    rem = int((prison_until - datetime.now(timezone.utc)).total_seconds())
                    await ctx.send(f"🔒 Tu es en prison. Libéré dans **{_fmt_duration(rem)}**.")
                    return
            last_crime = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_crime_at")
            if not bypass and last_crime is not None:
                elapsed = (datetime.now(timezone.utc) - last_crime.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < CRIME_COOLDOWN:
                    rem = CRIME_COOLDOWN - int(elapsed)
                    await ctx.send(f"⏳ Cooldown crime. Reviens dans **{_fmt_duration(rem)}**.")
                    return
            await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "last_crime_at", datetime.now(timezone.utc))

            suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            if random.random() < CRIME_SUCCESS_CHANCE:
                earned = random.randint(10, 200)
                new_bal = await add_balance(session, guild_id, ctx.author.id, earned)
                await session.commit()
                action = random.choice(CRIME_ACTIONS)
                embed = discord.Embed(
                    title="🦹 Crime réussi !",
                    description=(
                        f"Tu as réussi un **{action}** et gagné **{earned} credits**.\n"
                        f"Solde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0x2ECC71,
                )
            else:
                new_bal = await add_balance(session, guild_id, ctx.author.id, -CRIME_FINE)
                await session.commit()
                embed = discord.Embed(
                    title="🚔 Crime raté !",
                    description=(
                        f"Tu t'es fait attraper. Amende : **{CRIME_FINE} credits**.\n"
                        f"Solde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0xE74C3C,
                )
        await ctx.send(embed=embed)

    @commands.command(name="rob")
    async def rob(self, ctx: commands.Context, target: discord.Member, *args: str) -> None:
        wants_bypass = "bypass" in args
        if target.bot or target.id == ctx.author.id:
            await ctx.send("❌ Cible invalide.")
            return
        guild_id = ctx.guild.id
        key = f"{ctx.author.id}:{guild_id}"

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            prison_until = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "prison_until")
            if not bypass and prison_until is not None:
                prison_until = prison_until.replace(tzinfo=timezone.utc) if prison_until.tzinfo is None else prison_until
                if datetime.now(timezone.utc) < prison_until:
                    rem = int((prison_until - datetime.now(timezone.utc)).total_seconds())
                    await ctx.send(f"🔒 Tu es en prison. Libéré dans **{_fmt_duration(rem)}**.")
                    return
            last_rob = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_rob_at")
            if not bypass and last_rob is not None:
                elapsed = (datetime.now(timezone.utc) - last_rob.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < ROB_COOLDOWN:
                    rem = ROB_COOLDOWN - int(elapsed)
                    await ctx.send(f"⏳ Cooldown vol. Reviens dans **{_fmt_duration(rem)}**.")
                    return

            suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            await get_or_create_user(session, guild_id, target.id, target.display_name)
            target_bal = await self._get_balance(session, guild_id, target.id)
            if target_bal < ROB_TARGET_MIN_BALANCE:
                await ctx.send(
                    f"❌ {target.display_name} n'a pas assez de credits"
                    f" ({target_bal:,} < {ROB_TARGET_MIN_BALANCE})."
                )
                return

            await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "last_rob_at", datetime.now(timezone.utc))
            if random.random() < ROB_SUCCESS_CHANCE:
                pct = random.uniform(0.10, 0.30)
                stolen = max(1, int(target_bal * pct))
                await add_balance(session, guild_id, target.id, -stolen)
                new_bal = await add_balance(session, guild_id, ctx.author.id, stolen)
                await session.commit()
                embed = discord.Embed(
                    title="💰 Vol réussi !",
                    description=(
                        f"Tu as volé **{stolen} credits** à {target.display_name}"
                        f" ({pct * 100:.0f}%).\nSolde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0x2ECC71,
                )
            else:
                # Amende : 5% de l'argent total (portefeuille + banque)
                economy = await session.get(Economy, (guild_id, ctx.author.id))
                total_money = (economy.balance if economy else 0) + (economy.bank_balance if economy else 0)
                fine = max(10, int(total_money * 0.05))
                new_bal = await add_balance(session, guild_id, ctx.author.id, -fine)
                await session.commit()
                await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "prison_until", datetime.now(timezone.utc) + timedelta(seconds=PRISON_DURATION))
                prison_str = _fmt_duration(PRISON_DURATION)
                embed = discord.Embed(
                    title="🚔 Vol raté — en prison !",
                    description=(
                        f"Tu t'es fait attraper. Amende : **{fine:,} credits** (5% de {total_money:,})."
                        f" prison : **{prison_str}**.\nSolde : **{new_bal:,} credits**{suffix}"
                    ),
                    color=0xE74C3C,
                )
        await ctx.send(embed=embed)

async def setup(bot) -> None:
    await bot.add_cog(CrimeCog(bot))
