from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from config.settings import settings
from models.economy import Economy
from services.daily_streak import STREAK_WINDOW, register_daily_claim, streak_bonus
from services.economy import InsufficientBalanceError, add_balance, transfer_balance
from services.admin_permission import can_bypass
from services.effects import consume_one_shot, get_active_multiplier
from services.users import get_or_create_user
from shared.db import services as shared_services

DAILY_COOLDOWN = timedelta(hours=24)
WORK_COOLDOWN = 3600


class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        return self.bot.session_factory()

    def _now(self):
        return datetime.now(timezone.utc)

    @commands.command(name="balance")
    async def balance(self, ctx: commands.Context) -> None:
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            economy = await session.get(Economy, (guild_id, ctx.author.id))
            balance = economy.balance if economy is not None else 0
            await session.commit()

        await ctx.send(f"💰 Tu as **{balance}** coins.")

    @commands.command(name="pay")
    async def pay(self, ctx: commands.Context, member: discord.Member, *args: str) -> None:
        wants_bypass = "bypass" in args
        amount_tokens = [a for a in args if a != "bypass"]
        if not amount_tokens:
            await ctx.send("Montant manquant.")
            return
        try:
            montant = int(amount_tokens[0])
        except ValueError:
            await ctx.send("Montant invalide.")
            return

        if montant <= 0:
            await ctx.send("Le montant doit être positif.")
            return
        if member.id == ctx.author.id:
            await ctx.send("Tu ne peux pas te payer toi-même.")
            return

        guild_id = ctx.guild.id
        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            await get_or_create_user(session, guild_id, member.id, member.display_name)
            if bypass:
                await add_balance(session, guild_id, member.id, montant)
            else:
                try:
                    _new_from, _new_to = await transfer_balance(session, guild_id, ctx.author.id, member.id, montant)
                except InsufficientBalanceError:
                    await ctx.send("Solde insuffisant.")
                    return
            await session.commit()

        if bypass:
            await ctx.send(
                f"💸 [Bypass admin] {member.display_name} a reçu **{montant}** coins, sans débit de {ctx.author.display_name}."
            )
        else:
            await ctx.send(f"💸 {ctx.author.display_name} a payé **{montant}** coins à {member.display_name}.")

    @commands.command(name="daily")
    async def daily(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            economy = await session.get(Economy, (guild_id, ctx.author.id))
            now = self._now()

            previous_claim_at = None
            if economy is not None and economy.last_daily_at is not None:
                previous_claim_at = economy.last_daily_at
                if previous_claim_at.tzinfo is None:
                    previous_claim_at = previous_claim_at.replace(tzinfo=timezone.utc)

            if not bypass and previous_claim_at is not None:
                elapsed = now - previous_claim_at
                if elapsed < DAILY_COOLDOWN:
                    remaining = DAILY_COOLDOWN - elapsed
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int((remaining.total_seconds() % 3600) // 60)
                    await ctx.send(f"⏳ Reviens dans {hours}h{minutes:02d} pour ton prochain daily.")
                    return

            protected = False
            if previous_claim_at is not None and (now - previous_claim_at) >= STREAK_WINDOW:
                protected = await consume_one_shot(session, guild_id, ctx.author.id, "streak_protection")
            streak = await register_daily_claim(session, guild_id, ctx.author.id, previous_claim_at, now, protected)

            coins_boost = await get_active_multiplier(session, guild_id, ctx.author.id, "coins_boost")
            amount = round((settings.daily_amount + streak_bonus(streak.streak_count)) * coins_boost)
            new_balance = await add_balance(session, guild_id, ctx.author.id, amount)
            economy = await session.get(Economy, (guild_id, ctx.author.id))
            economy.last_daily_at = now
            await session.commit()

        suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
        protection_note = " 🛡️ Série protégée !" if protected else ""
        await ctx.send(
            f"🎁 Tu as reçu **{amount}** coins ! Solde : {new_balance}."
            f" Série : **{streak.streak_count}** jour(s).{suffix}{protection_note}"
        )

    @commands.command(name="work")
    async def work(self, ctx: commands.Context, *args: str) -> None:
        wants_bypass = "bypass" in args
        guild_id = ctx.guild.id
        key = f"{ctx.author.id}:{guild_id}"
        earned = settings.work_amount

        async with self._session() as session:
            bypass = wants_bypass and await can_bypass(session, guild_id, ctx.author)
            now = self._now()

            last_work = await shared_services.get_economy_cooldown(session, guild_id, ctx.author.id, "last_work_at")
            if not bypass and last_work is not None:
                elapsed = (now - last_work.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < WORK_COOLDOWN:
                    rem = WORK_COOLDOWN - int(elapsed)
                    h, r = divmod(rem, 3600)
                    m, s = divmod(r, 60)
                    await ctx.send(f"⏳ Tu viens de travailler. Reviens dans **{h}h{m:02d}**.")
                    return
            await shared_services.set_economy_cooldown(session, guild_id, ctx.author.id, "last_work_at", now)

            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            coins_boost = await get_active_multiplier(session, guild_id, ctx.author.id, "coins_boost")
            earned = round(earned * coins_boost)
            new_balance = await add_balance(session, guild_id, ctx.author.id, earned)
            await session.commit()

        suffix = " (bypass admin : cooldown ignoré)" if bypass else ""
        await ctx.send(f"💼 Travail effectué ! +**{earned}** coins → Solde : {new_balance}.{suffix}")

    @commands.group(name="bank", invoke_without_command=True)
    async def bank(self, ctx: commands.Context) -> None:
        """Voir son solde en banque."""
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            economy = await session.get(Economy, (guild_id, ctx.author.id))
            bank = economy.bank_balance if economy is not None else 0
            wallet = economy.balance if economy is not None else 0
            total = wallet + bank
            await session.commit()

        pct = (bank / total * 100) if total > 0 else 0
        await ctx.send(
            f"🏦 **Banque** : {bank:,} / {total:,} credits ({pct:.0f}%)\n"
            f"💰 **Portefeuille** : {wallet:,} credits\n"
            f"📏 Règle : banque ≤ portefeuille (max 50% du capital)"
        )

    @bank.command(name="add")
    async def bank_add(self, ctx: commands.Context, amount: int) -> None:
        """Ajouter des credits du portefeuille vers la banque."""
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            success, new_bank, error = await shared_services.deposit_to_bank(
                session, guild_id, ctx.author.id, amount
            )
            await session.commit()
        if success:
            economy = None
            async with self._session() as session:
                economy = await session.get(Economy, (guild_id, ctx.author.id))
            wallet = economy.balance if economy else 0
            await ctx.send(
                f"🏦 **{amount:,}** credits ajoutés → Banque : **{new_bank:,}** | Portefeuille : **{wallet:,}**"
            )
        else:
            await ctx.send(f"❌ {error}")

    @bank.command(name="remove")
    async def bank_remove(self, ctx: commands.Context, amount: int) -> None:
        """Retirer des credits de la banque vers le portefeuille."""
        guild_id = ctx.guild.id
        async with self._session() as session:
            await get_or_create_user(session, guild_id, ctx.author.id, ctx.author.display_name)
            success, new_bank, error = await shared_services.withdraw_from_bank(
                session, guild_id, ctx.author.id, amount
            )
            await session.commit()
        if success:
            economy = None
            async with self._session() as session:
                economy = await session.get(Economy, (guild_id, ctx.author.id))
            wallet = economy.balance if economy else 0
            await ctx.send(
                f"🏦 **{amount:,}** credits retirés → Banque : **{new_bank:,}** | Portefeuille : **{wallet:,}**"
            )
        else:
            await ctx.send(f"❌ {error}")



async def setup(bot) -> None:
    await bot.add_cog(EconomyCog(bot))
