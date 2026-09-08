import asyncio
import logging
import random
import re
import unicodedata

import discord
from discord.ext import commands

from config.settings import settings

import services.rpg_db as db
from services.rpg.achievements import ACHIEVEMENTS, PlayerStats, check_new_achievements
from services.rpg.black_market import generate_black_market
from services.rpg.bosses import BossGimmick, resolve_boss_round
from services.rpg.character import create_player
from services.rpg.classes import (
    CLASS_NAMES,
    CLASS_RARITY,
    CharacterClass,
    apply_class,
    random_class,
    unlocked_classes,
)
from services.rpg.combat import resolve_round
from services.rpg.events import draw_event, resolve_prisonnier, resolve_voix_dans_le_mur
from services.rpg.codex import DISCOVERY_MESSAGE, render_codex
from services.rpg.equipment import ARMORS, WEAPONS, apply_equipment, get_armor, get_weapon
from services.rpg.final_boss import create_final_boss_state, resolve_final_boss_round
from services.rpg.floor import OptionalRoomType, RoomType
from services.rpg.legacy import DeathRecord, apply_legacy_bonus, death_message
from services.rpg.monsters import spawn_monster
from services.rpg.potions import get_potion
from services.rpg.progression import (
    add_xp,
    apply_combat_start_bonus,
    apply_floor_growth,
    xp_reward_for_boss,
    xp_reward_for_monster,
)
from services.rpg.rarity import Rarity, RARITY_NAMES, RARITY_EMOJI, weighted_random_rarity
from services.rpg.render import render_scene
from services.rpg.rooms import (
    resolve_casino,
    resolve_enigme,
    resolve_piege,
    resolve_repos,
    resolve_salle_maudite,
    resolve_treasure,
)
from services.rpg.run import advance_floor, start_run
from services.rpg.shop import SHOP_CATALOG, buy_item, shop_price
from services.rpg.titles import TITLES, TitleProgress, check_new_titles
from services.rpg.tower_level import TOWER_XP_PER_BOSS, TOWER_XP_PER_FLOOR, tower_level_for_xp
from services.rpg.traits import TRAIT_NAMES
from services.rpg.unique_rooms import UNIQUE_ROOMS, draw_unique_room, resolve_room_visit
from services.users import get_or_create_user

from cogs._tour_combat import TourCombatMixin
from cogs import _tour_embeds as embeds
from cogs import _tour_ui as ui
from cogs._tour_ui import RunEnded, RunTimeout

RIDDLES = [
    ("Plus je sèche, plus je deviens mouillée. Que suis-je ?", "serviette"),
    ("Je n'ai pas de voix mais je te parle sans jamais me taire. Que suis-je ?", "livre"),
    ("Plus j'ai de gardiens, moins je suis gardée. Que suis-je ?", "verite"),
    ("On me trouve une fois dans une minute, deux fois dans un moment, jamais dans mille ans. Que suis-je ?", "m"),
]

UNIQUE_ROOM_CHANCE = 0.2
CASINO_BET = 20
MONSTER_DROP_CHANCE = 0.08
TREASURE_CHEST_CHANCE = 0.12
CLASS_CHANGE_INTERVAL = 30
CLASS_CHANGE_CHOOSE_RARITY_CHANCE = 0.40

logger = logging.getLogger(__name__)


class _InteractionContext:
    """Objet minimal compatible avec commands.Context pour lancer un flux de
    run depuis un bouton (interaction) plutôt que depuis une commande texte."""

    def __init__(self, interaction: discord.Interaction, target_channel: discord.abc.Messageable | None = None) -> None:
        self._interaction = interaction
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = target_channel or interaction.channel

    async def send(self, *args, **kwargs):
        return await self.channel.send(*args, **kwargs)


def _sanitize_channel_name(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = re.sub(r"[^a-z0-9 _-]", "", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-_")
    return name[:100] or "joueur"


def _tower_channel_name(member) -> str:
    return f"tower-of-{_sanitize_channel_name(member.display_name)}"


def _tower_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    if not settings.tour_category_id:
        return None
    try:
        category = guild.get_channel(int(settings.tour_category_id))
    except (ValueError, TypeError):
        return None
    return category if isinstance(category, discord.CategoryChannel) else None


def _find_tower_channel(guild: discord.Guild, member) -> discord.TextChannel | None:
    category = _tower_category(guild)
    if category is None:
        return None
    return discord.utils.get(category.text_channels, name=_tower_channel_name(member))


async def _get_or_create_tower_channel(guild: discord.Guild, member) -> discord.TextChannel | None:
    existing = _find_tower_channel(guild, member)
    if existing is not None:
        return existing
    category = _tower_category(guild)
    if category is None:
        return None
    try:
        return await category.create_text_channel(_tower_channel_name(member))
    except discord.Forbidden:
        return None


class TourCog(TourCombatMixin, commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.active_runs: dict[int, object] = {}
        self.tasks: dict[int, asyncio.Task] = {}

    def _session(self):
        return self.bot.session_factory()

    # --- Helpers DB ---

    async def _add_tower_xp(self, guild_id: int, user_id: int, amount: int) -> None:
        if amount <= 0:
            return
        async with self._session() as session:
            await db.increment_player_stat(session, guild_id, user_id, "tower_xp", amount)
            await session.commit()

    async def _get_tower_level(self, guild_id: int, user_id: int) -> int:
        async with self._session() as session:
            xp = await db.get_tower_xp(session, guild_id, user_id)
            await session.commit()
        return tower_level_for_xp(xp)

    async def _track_gold(self, guild_id: int, user_id: int, player, stats: PlayerStats, before_gold: int) -> None:
        if player.gold > before_gold:
            gained = player.gold - before_gold
            stats.gold_earned_total += gained
            async with self._session() as session:
                await db.increment_player_stat(session, guild_id, user_id, "gold_earned_total", gained)
                await session.commit()

    async def _bank_gold_to_or(self, guild_id: int, user_id: int, gold: int) -> None:
        if gold > 0:
            async with self._session() as session:
                await db.add_or_balance(session, guild_id, user_id, gold)
                await session.commit()

    async def _discard_run_banking(self, guild_id: int, user_id: int) -> None:
        run = self.active_runs.pop(user_id, None)
        if run is not None:
            await self._bank_gold_to_or(guild_id, user_id, run.player.gold)

    async def _ask_or_spend(self, ctx: commands.Context, guild_id: int, user_id: int, or_balance: int) -> int:
        def _validator(text: str) -> str | None:
            if not text.isdigit():
                return "Entre un nombre entier."
            amount = int(text)
            if not (0 <= amount <= or_balance):
                return f"Entre un nombre entre 0 et {or_balance}."
            return None

        reply = await ui.ask_text(
            ctx,
            "💰 Définir mon or de départ",
            "Or de départ",
            f"Montant (0-{or_balance})",
            embed=embeds.or_spend_embed(or_balance),
            validator=_validator,
        )
        amount = int(reply)
        if amount == 0:
            return 0
        async with self._session() as session:
            success, _balance = await db.spend_or_balance(session, guild_id, user_id, amount)
            await session.commit()
        return amount if success else 0

    async def _check_achievements(self, ctx: commands.Context, guild_id: int, stats: PlayerStats) -> None:
        async with self._session() as session:
            unlocked = await db.get_unlocked_achievements(session, guild_id, ctx.author.id)
            new_achievements = check_new_achievements(stats, unlocked)
            newly_unlocked_ones = []
            for achievement in new_achievements:
                if await db.unlock_achievement(session, guild_id, ctx.author.id, achievement.key):
                    newly_unlocked_ones.append(achievement)
            await session.commit()
        for achievement in newly_unlocked_ones:
            await ctx.send(embed=embeds.achievement_embed(achievement.name, achievement.description))

    async def _build_title_progress(self, session, guild_id: int, user_id: int, stats: PlayerStats) -> TitleProgress:
        row = await db.get_rpg_stats_row(session, guild_id, user_id)
        codex = await db.get_all_codex_visits(session, guild_id, user_id)
        unlocked_ach = await db.get_unlocked_achievements(session, guild_id, user_id)
        defeated = await db.get_defeated_bosses(session, guild_id, user_id)
        all_bosses = {g.value for g in BossGimmick}
        return TitleProgress(
            floor_reached_max=stats.floor_reached_max,
            monsters_killed=stats.monsters_killed,
            gold_earned_total=stats.gold_earned_total,
            deaths=stats.deaths,
            rooms_discovered=len(codex),
            chests_opened=row.chests_opened,
            casino_wins=row.casino_wins,
            jackpots=row.jackpots,
            boss_kills=row.boss_kills,
            curses_survived=row.curses_survived,
            pacts_used=row.pacts_used,
            runs_completed=row.runs_completed,
            infinite_mode_reached=row.infinite_mode_reached,
            all_rooms_discovered=len(codex) >= len(UNIQUE_ROOMS),
            all_bosses_defeated=defeated >= all_bosses,
            all_achievements=len(unlocked_ach) >= len(ACHIEVEMENTS),
            all_classes_unlocked=len(unlocked_classes(tower_level_for_xp(row.tower_xp))) >= len(CharacterClass),
        )

    async def _check_titles(self, ctx: commands.Context, guild_id: int, stats: PlayerStats) -> None:
        async with self._session() as session:
            progress = await self._build_title_progress(session, guild_id, ctx.author.id, stats)
            unlocked = await db.get_unlocked_titles(session, guild_id, ctx.author.id)
            newly = []
            for title in check_new_titles(progress, unlocked):
                if await db.unlock_title(session, guild_id, ctx.author.id, title.key):
                    newly.append(title)
            await session.commit()
        for title in newly:
            await ctx.send(embed=embeds.title_embed(title))

    async def _increment_counter(self, guild_id: int, user_id: int, field: str, amount: int = 1) -> None:
        async with self._session() as session:
            await db.increment_player_stat(session, guild_id, user_id, field, amount)
            await session.commit()

    # --- Équipement ---

    def _roll_equipment_drop(self, rng) -> tuple[str, str, str]:
        rarity = weighted_random_rarity(rng)
        kind = rng.choice(("weapon", "armor"))
        pool = WEAPONS if kind == "weapon" else ARMORS
        candidates = [item for item in pool if item.rarity == rarity]
        item = rng.choice(candidates)
        return kind, item.key, item.name

    async def _grant_equipment_drop(self, ctx, guild_id: int, user_id: int, kind: str, key: str, name: str) -> None:
        async with self._session() as session:
            await db.add_inventory_item(session, guild_id, user_id, kind, key)
            weapon, armor = await db.get_loadout(session, guild_id, user_id)
            auto = False
            if kind == "weapon" and weapon is None:
                await db.set_loadout(session, guild_id, user_id, key, armor)
                auto = True
            elif kind == "armor" and armor is None:
                await db.set_loadout(session, guild_id, user_id, weapon, key)
                auto = True
            await session.commit()
        msg = f"Tu obtiens **{name}** (équipement persistant) !"
        msg += " Équipé automatiquement." if auto else " Gère-le via le bouton 🗡️ Équipement."
        await ctx.send(embed=embeds.room_embed(emoji="🎁", title="Butin", description=msg, color=embeds.COLOR_TRESOR))

    async def _manage_equipment(self, ctx, guild_id: int, user_id: int) -> None:
        while True:
            async with self._session() as session:
                inv = await db.get_inventory(session, guild_id, user_id)
                weapon_key, armor_key = await db.get_loadout(session, guild_id, user_id)
                await session.commit()

            options: list[tuple[str, str, str | None]] = []
            for key in sorted(inv.get("weapon", {})):
                name = get_weapon(key).name if get_weapon(key) else key
                options.append((f"weapon:{key}", f"🗡️ {name}", None))
            for key in sorted(inv.get("armor", {})):
                name = get_armor(key).name if get_armor(key) else key
                options.append((f"armor:{key}", f"🛡️ {name}", None))
            if weapon_key:
                options.append(("unequip_weapon", "↩️ Retirer l'arme", None))
            if armor_key:
                options.append(("unequip_armor", "↩️ Retirer l'armure", None))
            options.append(("done", "✅ Terminé", None))

            if len(options) > 25:
                options = options[:24] + [("done", "✅ Terminé", None)]

            wname = get_weapon(weapon_key).name if weapon_key and get_weapon(weapon_key) else "Aucune"
            aname = get_armor(armor_key).name if armor_key and get_armor(armor_key) else "Aucune"
            embed = discord.Embed(title="🗡️ Équipement", color=embeds.COLOR_NEUTRAL)
            embed.description = "Choisis un objet à équiper (appliqué à ta prochaine run)."
            embed.add_field(name="Arme équipée", value=wname, inline=True)
            embed.add_field(name="Armure équipée", value=aname, inline=True)
            if not options[:-1]:
                embed.add_field(name="Inventaire", value="Vide. Trouve de l'équipement dans les coffres, sur les ennemis ou au marché noir.", inline=False)

            choice = await ui.ask_select(ctx, embed, options, "Gérer l'équipement")
            if choice == "done":
                await ctx.send("✅ Équipement mis à jour.")
                return
            async with self._session() as session:
                w2, a2 = await db.get_loadout(session, guild_id, user_id)
                if choice == "unequip_weapon":
                    await db.set_loadout(session, guild_id, user_id, None, a2)
                elif choice == "unequip_armor":
                    await db.set_loadout(session, guild_id, user_id, w2, None)
                elif choice.startswith("weapon:"):
                    await db.set_loadout(session, guild_id, user_id, choice.split(":", 1)[1], a2)
                elif choice.startswith("armor:"):
                    await db.set_loadout(session, guild_id, user_id, w2, choice.split(":", 1)[1])
                await session.commit()

    # --- Mort / fin ---

    async def _handle_death(self, ctx: commands.Context, guild_id: int, run, stats: PlayerStats) -> None:
        user_id = ctx.author.id
        record = DeathRecord(
            floor_reached=run.floor.number,
            monsters_killed=stats.monsters_killed,
            gold_earned=run.player.gold,
        )
        async with self._session() as session:
            await db.record_death(
                session, guild_id, user_id, record.floor_reached, record.monsters_killed, record.gold_earned
            )
            stats.deaths += 1
            await db.increment_player_stat(session, guild_id, user_id, "deaths")
            await session.commit()
        if self.active_runs.pop(user_id, None) is not None:
            await self._bank_gold_to_or(guild_id, user_id, run.player.gold)
        await ctx.send(
            embed=embeds.death_embed(
                record.floor_reached, record.monsters_killed, record.gold_earned, death_message(record)
            )
        )
        await self._check_achievements(ctx, guild_id, stats)
        await self._check_titles(ctx, guild_id, stats)

    # --- Flux principal ---

    async def _run_tour_flow(self, ctx, guild_id: int, user_id: int) -> None:
        if user_id in self.tasks:
            await ctx.send("Tu as déjà une run en cours ! Termine-la avant d'en commencer une nouvelle.")
            return
        self.tasks[user_id] = asyncio.current_task()
        try:
            async with self._session() as session:
                await get_or_create_user(session, guild_id, user_id, ctx.author.display_name)
                await session.commit()

            async with self._session() as session:
                ng = await db.get_ng_plus(session, guild_id, user_id)
                or_balance = await db.get_or_balance(session, guild_id, user_id)
                tower_xp = await db.get_tower_xp(session, guild_id, user_id)
                weapon_key, armor_key = await db.get_loadout(session, guild_id, user_id)
                row = await db.get_rpg_stats_row(session, guild_id, user_id)
                permanent_atk = row.permanent_atk
                await session.commit()

            tower_level = tower_level_for_xp(tower_xp)
            available = unlocked_classes(tower_level)
            options = [
                (c.value, f"{RARITY_EMOJI[CLASS_RARITY[c]]} {CLASS_NAMES[c]}", embeds.CLASS_BLURBS.get(c))
                for c in available
            ]
            choice_value = await ui.ask_select(
                ctx,
                embeds.class_select_embed(tower_level, len(available), len(CharacterClass)),
                options,
                "Choisis ta classe...",
            )
            character_class = CharacterClass(choice_value)
            starting_gold = 0
            if or_balance > 0:
                starting_gold = await self._ask_or_spend(ctx, guild_id, user_id, or_balance)
            player, trait = create_player(character_class, random, tower_level=tower_level)
            player.gold = starting_gold
            player.atk += permanent_atk
            apply_equipment(player, weapon_key, armor_key)
            async with self._session() as session:
                legacy = await db.get_legacy(session, guild_id, user_id)
                await session.commit()
            apply_legacy_bonus(player, legacy)
            run = start_run(player, random, ng_plus=ng)
            run.character_class = character_class
            self.active_runs[user_id] = run
            await ctx.send(embed=embeds.run_start_embed(CLASS_NAMES[character_class], TRAIT_NAMES[trait]))
            await self._play_run(ctx, guild_id, run, ng, tower_level)
        except asyncio.CancelledError:
            pass
        except RunTimeout:
            await self._discard_run_banking(guild_id, user_id)
            await ctx.send("⏱️ Temps écoulé, la run est abandonnée.")
        except Exception:
            await self._discard_run_banking(guild_id, user_id)
            await ctx.send("⚠️ Une erreur inattendue est survenue, ta run a été annulée. Réessaie.")
            logger.exception("Erreur dans la run Tour de %s (guild %s)", user_id, guild_id)
        finally:
            self.tasks.pop(user_id, None)

    async def _do_abandon(self, ctx, guild_id: int, user_id: int) -> None:
        task = self.tasks.get(user_id)
        if task is None:
            await ctx.send("Tu n'as pas de run en cours.")
            return
        run = self.active_runs.pop(user_id, None)
        if run is not None:
            await self._bank_gold_to_or(guild_id, user_id, run.player.gold)
        task.cancel()
        await ctx.send("🏳️ Tu abandonnes ta run. La Tour attend ton retour.")

    async def _show_or(self, guild_id: int, user_id: int) -> int:
        async with self._session() as session:
            balance = await db.get_or_balance(session, guild_id, user_id)
            await session.commit()
        return balance

    async def _do_convert(self, guild_id: int, user_id: int, amount: int) -> str:
        async with self._session() as session:
            success, reason = await db.convert_or_to_credits(session, guild_id, user_id, amount)
            await session.commit()
        if not success:
            return "❌ Le montant doit être positif." if reason == "invalid_amount" else "❌ Tu n'as pas assez d'Or."
        return f"💱 {amount} Or converti en {amount} credits sur ce serveur."

    async def _show_codex(self, ctx, guild_id: int, user_id: int) -> None:
        async with self._session() as session:
            discovered = await db.get_all_codex_visits(session, guild_id, user_id)
            await session.commit()
        await ctx.send(render_codex(discovered))

    @commands.command(name="tourpanel")
    @commands.has_permissions(administrator=True)
    async def tourpanel(self, ctx: commands.Context, membre: discord.Member | None = None) -> None:
        embed = embeds.room_embed(
            emoji="🏰",
            title="La Tour",
            description="Choisis une action :",
            color=embeds.COLOR_NEUTRAL,
        )
        if membre is not None:
            channel = await _get_or_create_tower_channel(ctx.guild, membre)
            if channel is None:
                await ctx.send(
                    "❌ Impossible de créer le salon : catégorie de la Tour non configurée "
                    "(via `.config` → Salons) ou permission manquante."
                )
                return
            await channel.send(embed=embed, view=TourPanelView(self))
            await ctx.send(f"✅ Panneau posté dans {channel.mention}.")
            return
        await ctx.send(embed=embed, view=TourPanelView(self))

    @commands.command(name="towerof")
    async def towerof(self, ctx: commands.Context, *, cible: str | None = None) -> None:
        guild_id = ctx.guild.id
        member = ctx.author
        if cible:
            mention = re.match(r"<@!?(\d{15,25})>", cible.strip())
            if mention:
                member = ctx.guild.get_member(int(mention.group(1)))
            elif cible.strip().isdigit():
                member = ctx.guild.get_member(int(cible.strip()))
            else:
                member = discord.utils.find(
                    lambda u: u.name == cible.strip() or u.display_name == cible.strip(),
                    ctx.guild.members,
                )
            if member is None:
                await ctx.send("❌ Membre introuvable sur ce serveur.")
                return

        user_id = member.id
        async with self._session() as session:
            or_balance = await db.get_or_balance(session, guild_id, user_id)
            ng = await db.get_ng_plus(session, guild_id, user_id)
            stats = await db.get_player_stats(session, guild_id, user_id)
            unlocked = await db.get_unlocked_achievements(session, guild_id, user_id)
            codex = await db.get_all_codex_visits(session, guild_id, user_id)
            legacy = await db.get_legacy(session, guild_id, user_id)
            row = await db.get_rpg_stats_row(session, guild_id, user_id)
            weapon_key, armor_key = await db.get_loadout(session, guild_id, user_id)
            titles = await db.get_unlocked_titles(session, guild_id, user_id)
            await session.commit()

        tower_level = tower_level_for_xp(row.tower_xp)
        embed = discord.Embed(title=f"🗼 Tour — {member.display_name}", color=embeds.COLOR_NEUTRAL)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="⭐ Niveau de la Tour", value=str(tower_level), inline=True)
        embed.add_field(name="Étage le plus haut", value=str(stats.floor_reached_max), inline=True)
        embed.add_field(name="New Game+", value=str(ng), inline=True)
        embed.add_field(name="💰 Or", value=str(or_balance), inline=True)
        embed.add_field(name="💀 Morts", value=str(stats.deaths), inline=True)
        embed.add_field(name="⚔️ Monstres vaincus", value=str(stats.monsters_killed), inline=True)
        embed.add_field(name="💵 Or total gagné", value=str(stats.gold_earned_total), inline=True)
        embed.add_field(name="👑 Boss sans dégât", value=str(stats.boss_no_damage_wins), inline=True)
        embed.add_field(name="🏆 Succès", value=f"{len(unlocked)}/{len(ACHIEVEMENTS)}", inline=True)
        embed.add_field(name="🏅 Titres", value=f"{len(titles)}/{len(TITLES)}", inline=True)
        embed.add_field(name="📖 Codex", value=f"{len(codex)}/{len(UNIQUE_ROOMS)}", inline=True)

        wname = get_weapon(weapon_key).name if weapon_key and get_weapon(weapon_key) else "Aucune"
        aname = get_armor(armor_key).name if armor_key and get_armor(armor_key) else "Aucune"
        embed.add_field(name="🗡️ Arme équipée", value=wname, inline=True)
        embed.add_field(name="🛡️ Armure équipée", value=aname, inline=True)

        best_floor = max((r.floor_reached for r in legacy.history), default=0)
        if best_floor:
            embed.add_field(name="🪦 Legacy", value=f"Meilleure ascension : étage {best_floor}", inline=True)

        run = self.active_runs.get(user_id)
        if run is not None:
            embed.add_field(
                name="▶️ Run en cours",
                value=f"Étage {run.floor.number} · {run.player.hp}/{run.player.max_hp} PV · {run.player.gold} or",
                inline=False,
            )
        else:
            embed.add_field(name="▶️ Run en cours", value="Aucune", inline=False)

        await ctx.send(embed=embed)

    # --- Boucle de run ---

    async def _play_run(self, ctx: commands.Context, guild_id: int, run, ng: int, tower_level: int) -> None:
        user_id = ctx.author.id
        async with self._session() as session:
            stats = await db.get_player_stats(session, guild_id, user_id)
            await session.commit()
        try:
            while True:
                floor = run.floor
                await ctx.send(embed=embeds.floor_banner_embed(floor.number, ng))
                stats.floor_reached_max = max(stats.floor_reached_max, floor.number)
                async with self._session() as session:
                    await db.update_floor_reached_max(session, guild_id, user_id, floor.number)
                    await session.commit()
                await self._add_tower_xp(guild_id, user_id, TOWER_XP_PER_FLOOR)

                if floor.boss is not None:
                    if floor.number == 100:
                        await self._fight_final_boss(ctx, guild_id, run, stats, ng)
                    else:
                        await self._fight_boss(ctx, guild_id, run, floor.boss, stats)
                    if floor.number >= 100:
                        keep_going = await self._offer_new_game_plus(ctx, guild_id, ng)
                        if not keep_going:
                            return
                    else:
                        await self._offer_shop_and_black_market(ctx, guild_id, run.player, stats)
                        if floor.number % CLASS_CHANGE_INTERVAL == 0:
                            await self._offer_class_change(ctx, guild_id, run, stats, tower_level)
                else:
                    for room in floor.main_rooms:
                        await self._resolve_main_room(ctx, guild_id, run, room, stats)
                    for room in floor.optional_rooms:
                        await self._resolve_optional_room(ctx, guild_id, run, room, stats)
                advance_floor(run, random, ng_plus=ng)
                apply_floor_growth(run.player, random)
        except RunTimeout:
            await self._discard_run_banking(guild_id, user_id)
            await ctx.send("⏱️ Temps écoulé, la run est abandonnée.")
        except RunEnded:
            pass

    async def _fight_boss(self, ctx: commands.Context, guild_id: int, run, boss, stats: PlayerStats) -> None:
        player = run.player
        took_damage = False

        def _on_round(result) -> None:
            nonlocal took_damage
            if result.monster_damage_dealt > 0:
                took_damage = True

        def _format_round(result) -> list[str]:
            if result.frozen:
                msg = "⏳ Le temps se fige, ton attaque est annulée !"
            else:
                msg = f"Tu infliges {result.player_damage_dealt} dégâts"
                if result.reflected_damage:
                    msg += f" (dont {result.reflected_damage} te sont renvoyés)"
                msg += "."
            msg += f" Riposte : {result.monster_damage_dealt} dégâts"
            if result.healed:
                msg += f" (se soigne de {result.healed})"
            msg += "."
            return [msg]

        outcome = await self._run_combat(
            ctx,
            guild_id,
            run,
            stats,
            target=boss,
            intro_text=f"👑 **{boss.name}** apparaît !",
            resolve_round_fn=resolve_boss_round,
            format_log_fn=_format_round,
            on_round_fn=_on_round,
            color=embeds.COLOR_BOSS,
            victory_emoji="👑",
            can_flee=False,
        )
        if outcome == "victory":
            gained_xp = xp_reward_for_boss(boss)
            levels = add_xp(player, gained_xp)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="👑",
                    title="Boss vaincu",
                    description=f"**{boss.name}** est vaincu ! (+{gained_xp} XP)",
                    color=embeds.COLOR_VICTORY,
                )
            )
            if levels:
                await ctx.send(embed=embeds.level_up_embed(player.level))
            if not took_damage:
                stats.boss_no_damage_wins += 1
                await self._increment_counter(guild_id, ctx.author.id, "boss_no_damage_wins")
            await self._increment_counter(guild_id, ctx.author.id, "boss_kills")
            async with self._session() as session:
                await db.record_boss_defeated(session, guild_id, ctx.author.id, boss.gimmick.value)
                await session.commit()
            await self._add_tower_xp(guild_id, ctx.author.id, TOWER_XP_PER_BOSS)
            await self._apply_kill_rewards(ctx, guild_id, player)
            await self._check_achievements(ctx, guild_id, stats)
            await self._check_titles(ctx, guild_id, stats)

    async def _fight_final_boss(self, ctx: commands.Context, guild_id: int, run, stats: PlayerStats, ng: int) -> None:
        player = run.player
        user_id = ctx.author.id
        async with self._session() as session:
            legacy = await db.get_legacy(session, guild_id, user_id)
            codex_visits = await db.get_all_codex_visits(session, guild_id, user_id)
            await session.commit()
        state = create_final_boss_state(ng_plus=ng)
        boss = state.boss
        took_damage = False

        def _on_round(result) -> None:
            nonlocal took_damage
            if result.monster_damage_dealt > 0 or result.player_dot_damage > 0:
                took_damage = True

        def _format_round(result) -> list[str]:
            lines = []
            if result.phase_intro:
                lines.append(f"💬 {result.phase_intro}")
            if result.player_frozen:
                msg = "⏳ Le temps se fige, ton attaque est annulée !"
            else:
                msg = f"Tu infliges {result.player_damage_dealt} dégâts."
            if result.ability_message:
                msg += f" {result.ability_message}"
            msg += f" Riposte : {result.monster_damage_dealt} dégâts."
            lines.append(msg)
            return lines

        def _resolve(player_, target_, rng_, *, player_attacks=True):
            return resolve_final_boss_round(
                state, player_, stats, legacy, len(codex_visits), rng_, player_attacks=player_attacks
            )

        outcome = await self._run_combat(
            ctx,
            guild_id,
            run,
            stats,
            target=boss,
            intro_text=f"👑 **{boss.name}** se dresse devant toi.",
            resolve_round_fn=_resolve,
            format_log_fn=_format_round,
            on_round_fn=_on_round,
            color=embeds.COLOR_BOSS,
            victory_emoji="👑",
            can_flee=False,
        )
        if outcome == "victory":
            gained_xp = xp_reward_for_boss(boss)
            levels = add_xp(player, gained_xp)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="👑",
                    title="Le Cœur de la Tour s'effondre...",
                    description=f"+{gained_xp} XP",
                    color=embeds.COLOR_VICTORY,
                )
            )
            if levels:
                await ctx.send(embed=embeds.level_up_embed(player.level))
            if not took_damage:
                stats.boss_no_damage_wins += 1
                await self._increment_counter(guild_id, user_id, "boss_no_damage_wins")
            await self._increment_counter(guild_id, user_id, "boss_kills")
            await self._increment_counter(guild_id, user_id, "runs_completed")
            async with self._session() as session:
                await db.record_boss_defeated(session, guild_id, user_id, BossGimmick.LE_COEUR_DE_LA_TOUR.value)
                await session.commit()
            await self._add_tower_xp(guild_id, user_id, TOWER_XP_PER_BOSS)
            await self._apply_kill_rewards(ctx, guild_id, player)
            await self._check_achievements(ctx, guild_id, stats)
            await self._check_titles(ctx, guild_id, stats)

    async def _apply_kill_rewards(self, ctx, guild_id: int, player) -> None:
        """Nécromancien (soin + ATK au kill), régénération post-combat, drop d'équipement."""
        if player.heal_on_kill_ratio:
            healed = player.heal(round(player.max_hp * player.heal_on_kill_ratio))
            if healed:
                await ctx.send(embed=embeds.room_embed(emoji="🩸", title="Nécromancie", description=f"Tu te nourris de la mort : {healed} PV.", color=embeds.COLOR_EVENEMENT))
        if player.atk_on_kill:
            player.atk += player.atk_on_kill
            await ctx.send(embed=embeds.room_embed(emoji="⚡", title="Puissance", description=f"Ton pouvoir grandit : +{player.atk_on_kill} ATK.", color=embeds.COLOR_EVENEMENT))
        if player.regen_ratio:
            healed = player.heal(round(player.max_hp * player.regen_ratio))
            if healed:
                await ctx.send(embed=embeds.room_embed(emoji="💚", title="Régénération", description=f"Tu récupères {healed} PV.", color=embeds.COLOR_REPOS))

    async def _maybe_drop_equipment(self, ctx, guild_id: int, chance: float) -> None:
        if random.random() < chance:
            kind, key, name = self._roll_equipment_drop(random)
            await self._grant_equipment_drop(ctx, guild_id, ctx.author.id, kind, key, name)

    # --- Salles ---

    async def _resolve_main_room(self, ctx: commands.Context, guild_id: int, run, room: RoomType, stats: PlayerStats) -> None:
        player = run.player
        if room == RoomType.COMBAT:
            await self._fight_monster(ctx, guild_id, run, stats)
            return

        before_gold = player.gold
        if room == RoomType.TRESOR:
            gained = resolve_treasure(player, random)
            if player.treasure_multiplier:
                bonus = round(gained * player.treasure_multiplier)
                player.add_gold(bonus, apply_multiplier=False)
                gained += bonus
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="📦", title="Trésor", description=f"Tu trouves {gained} or !", color=embeds.COLOR_TRESOR
                )
            )
            await self._maybe_drop_equipment(ctx, guild_id, TREASURE_CHEST_CHANCE)
        elif room == RoomType.REPOS:
            healed = resolve_repos(player)
            if healed:
                description = f"Tu te reposes et récupères {healed} PV."
            else:
                description = "Ton trait t'empêche de profiter de ce repos."
            await ctx.send(
                embed=embeds.room_embed(emoji="😴", title="Repos", description=description, color=embeds.COLOR_REPOS)
            )
        elif room == RoomType.PIEGE:
            dealt = resolve_piege(player, random)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="🪤",
                    title="Piège",
                    description=f"Un piège se déclenche : {dealt} dégâts !",
                    color=embeds.COLOR_PIEGE,
                )
            )
        elif room == RoomType.ENIGME:
            await self._resolve_enigme_room(ctx, player)
        elif room == RoomType.EVENEMENT:
            await self._resolve_evenement(ctx, guild_id, player, run.floor.number)

        await self._track_gold(guild_id, ctx.author.id, player, stats, before_gold)
        if not player.is_alive():
            await self._handle_death(ctx, guild_id, run, stats)
            raise RunEnded()

    async def _resolve_enigme_room(self, ctx: commands.Context, player) -> None:
        question, answer = random.choice(RIDDLES)
        embed = embeds.room_embed(emoji="🧠", title="Énigme", description=question, color=embeds.COLOR_ENIGME)
        reply = await ui.ask_text(ctx, "🧠 Répondre", "Énigme", "Ta réponse", embed=embed)
        if resolve_enigme(reply, answer):
            gained = random.randint(15, 25)
            player.add_gold(gained)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="✅",
                    title="Bonne réponse !",
                    description=f"Tu gagnes {gained} or.",
                    color=embeds.COLOR_ENIGME,
                )
            )
        else:
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="❌",
                    title="Mauvaise réponse",
                    description=f"C'était « {answer} »... la salle se referme sans récompense.",
                    color=embeds.COLOR_ENIGME,
                )
            )

    async def _resolve_evenement(self, ctx: commands.Context, guild_id: int, player, floor_number: int) -> None:
        chance = UNIQUE_ROOM_CHANCE + player.unique_room_chance_bonus
        if random.random() < chance:
            room = draw_unique_room(random, floor_number)
            async with self._session() as session:
                visit_count = await db.record_codex_visit(session, guild_id, ctx.author.id, room.key)
                await session.commit()
            if room.key == "salle_du_pacte":
                await self._increment_counter(guild_id, ctx.author.id, "pacts_used")
            display_name, message, description = resolve_room_visit(room, visit_count, player, random)
            if visit_count == 1:
                await ctx.send(
                    embed=embeds.room_embed(
                        emoji="📖",
                        title="Nouvelle salle découverte !",
                        description=DISCOVERY_MESSAGE,
                        color=embeds.COLOR_EVENEMENT,
                    )
                )
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="✨",
                    title=display_name,
                    description=f"{description}\n{message}",
                    color=embeds.COLOR_EVENEMENT,
                )
            )
            return

        event = draw_event(random)
        async with self._session() as session:
            await db.record_codex_visit(session, guild_id, ctx.author.id, f"event:{event.key}")
            await session.commit()
        if event.key == "prisonnier":
            embed = embeds.room_embed(
                emoji="🎭", title=event.name, description=event.description, color=embeds.COLOR_EVENEMENT
            )
            choice = await ui.ask_choice(
                ctx,
                embed,
                [
                    ("oui", "✅ Libérer", discord.ButtonStyle.success),
                    ("non", "❌ Laisser", discord.ButtonStyle.secondary),
                ],
            )
            message = resolve_prisonnier(player, choice == "oui", random)
        elif event.key == "voix_dans_le_mur":
            embed = embeds.room_embed(
                emoji="🎭", title=event.name, description=event.description, color=embeds.COLOR_EVENEMENT
            )
            choice = await ui.ask_choice(
                ctx,
                embed,
                [
                    ("oui", "✅ Écouter", discord.ButtonStyle.success),
                    ("non", "❌ Ignorer", discord.ButtonStyle.secondary),
                ],
            )
            message = resolve_voix_dans_le_mur(player, choice == "oui", random)
        else:
            message = event.effect(player, random)
        if event.key == "coffre_piege":
            await self._increment_counter(guild_id, ctx.author.id, "chests_opened")
        await ctx.send(
            embed=embeds.room_embed(emoji="🎭", title=event.name, description=message, color=embeds.COLOR_EVENEMENT)
        )

    async def _resolve_optional_room(self, ctx: commands.Context, guild_id: int, run, room: OptionalRoomType, stats: PlayerStats) -> None:
        player = run.player
        name = "Casino" if room == OptionalRoomType.CASINO else "Salle Maudite"
        embed = embeds.room_embed(
            emoji="➕",
            title=f"Salle optionnelle : {name}",
            description="Veux-tu entrer ?",
            color=embeds.COLOR_EVENEMENT,
        )
        choice = await ui.ask_choice(
            ctx,
            embed,
            [
                ("enter", "➡️ Entrer", discord.ButtonStyle.primary),
                ("skip", "🚪 Ignorer", discord.ButtonStyle.secondary),
            ],
        )
        if choice == "skip":
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="🚪", title="Salle ignorée", description=f"Tu ignores la {name}.", color=embeds.COLOR_EVENEMENT
                )
            )
            return

        before_gold = player.gold
        if room == OptionalRoomType.CASINO:
            bet = min(CASINO_BET, player.gold)
            if bet <= 0:
                await ctx.send(
                    embed=embeds.room_embed(
                        emoji="🎰",
                        title="Casino",
                        description="Tu n'as pas assez d'or pour parier.",
                        color=embeds.COLOR_EVENEMENT,
                    )
                )
            else:
                net = resolve_casino(player, bet, random)
                if net > 0:
                    await self._increment_counter(guild_id, ctx.author.id, "casino_wins")
                    if random.random() < 0.05:
                        await self._increment_counter(guild_id, ctx.author.id, "jackpots")
                        await ctx.send(
                            embed=embeds.room_embed(
                                emoji="🎰", title="JACKPOT !", description=f"Tu gagnes {net} or, et un jackpot retentit !", color=embeds.COLOR_TRESOR
                            )
                        )
                    else:
                        await ctx.send(
                            embed=embeds.room_embed(
                                emoji="🎰", title="Casino", description=f"Tu gagnes {net} or !", color=embeds.COLOR_TRESOR
                            )
                        )
                else:
                    await ctx.send(
                        embed=embeds.room_embed(
                            emoji="🎰", title="Casino", description=f"Tu perds {-net} or...", color=embeds.COLOR_PIEGE
                        )
                    )
        else:
            dealt, gained = resolve_salle_maudite(player, random)
            await self._increment_counter(guild_id, ctx.author.id, "curses_survived")
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="💀",
                    title="Salle Maudite",
                    description=f"Tu subis {dealt} dégâts mais gagnes {gained} or.",
                    color=embeds.COLOR_PIEGE,
                )
            )

        await self._track_gold(guild_id, ctx.author.id, player, stats, before_gold)
        if not player.is_alive():
            await self._handle_death(ctx, guild_id, run, stats)
            raise RunEnded()

    # --- Boutique & marché noir ---

    async def _offer_shop_and_black_market(self, ctx: commands.Context, guild_id: int, player, stats: PlayerStats) -> None:
        options = [(p.key, f"{p.name} — {shop_price(player, p)} or", None) for p in SHOP_CATALOG]
        options.append(("skip", "🚪 Partir", None))
        choice = await ui.ask_select(ctx, embeds.shop_embed(player.gold), options, "Visiter la boutique ?")
        if choice != "skip":
            potion = get_potion(choice)
            before_gold = player.gold
            message = buy_item(player, potion)
            await self._track_gold(guild_id, ctx.author.id, player, stats, before_gold)
            await ctx.send(embed=embeds.room_embed(emoji="🛒", title="Boutique", description=message, color=embeds.COLOR_SHOP))

        offers = generate_black_market(random)
        bm_options = [(str(i), f"{offer.name} — {offer.price} or", None) for i, offer in enumerate(offers)]
        bm_options.append(("skip", "🚪 Partir", None))
        choice = await ui.ask_select(
            ctx, embeds.black_market_embed(player.gold), bm_options, "Visiter le marché noir ?"
        )
        if choice != "skip":
            offer = offers[int(choice)]
            if player.gold < offer.price:
                await ctx.send(
                    embed=embeds.room_embed(emoji="🕶️", title="Marché noir", description="Pas assez d'or.", color=embeds.COLOR_SHOP)
                )
            else:
                player.add_gold(-offer.price)
                if offer.kind == "potion":
                    player.bag.append(offer.key)
                    await ctx.send(
                        embed=embeds.room_embed(emoji="🕶️", title="Marché noir", description=f"{offer.name} rejoint ton sac.", color=embeds.COLOR_SHOP)
                    )
                else:
                    await self._grant_equipment_drop(ctx, guild_id, ctx.author.id, offer.kind, offer.key, offer.name)

    # --- Changement de classe ---

    async def _offer_class_change(self, ctx: commands.Context, guild_id: int, run, stats: PlayerStats, tower_level: int) -> None:
        await ctx.send(
            embed=embeds.room_embed(
                emoji="🌀",
                title="Salle de la Métamorphose",
                description="Une salle grouillant de monstres garde le droit de changer de classe.",
                color=embeds.COLOR_EVENEMENT,
            )
        )
        for _ in range(2):
            await self._fight_monster(ctx, guild_id, run, stats)

        player = run.player
        if random.random() < CLASS_CHANGE_CHOOSE_RARITY_CHANCE:
            available_rarities = sorted(
                {CLASS_RARITY[c] for c in unlocked_classes(tower_level)},
                key=lambda r: list(Rarity).index(r),
            )
            options = [(r.value, RARITY_NAMES[r], None) for r in available_rarities]
            choice = await ui.ask_select(
                ctx,
                embeds.room_embed(emoji="🌀", title="Nouvelle classe", description="Choisis la catégorie de ta nouvelle classe.", color=embeds.COLOR_EVENEMENT),
                options,
                "Choisis une rareté",
            )
            rarity = Rarity(choice)
            candidates = [c for c in unlocked_classes(tower_level) if CLASS_RARITY[c] == rarity]
            new_class = random.choice(candidates)
        else:
            new_class = random_class(random, tower_level=tower_level)

        apply_class(player, new_class)
        run.character_class = new_class
        await ctx.send(
            embed=embeds.room_embed(
                emoji="🌀",
                title="Métamorphose",
                description=f"Tu deviens **{CLASS_NAMES[new_class]}** ! Ses pouvoirs s'ajoutent aux tiens.",
                color=embeds.COLOR_VICTORY,
            )
        )

    async def _offer_new_game_plus(self, ctx: commands.Context, guild_id: int, ng: int) -> bool:
        await ctx.send(embed=embeds.victory_embed())
        user_id = ctx.author.id
        choice = await ui.ask_choice(
            ctx,
            embeds.new_game_plus_embed(),
            [
                ("ngplus", "🔄 New Game+", discord.ButtonStyle.success),
                ("infinite", "♾️ Mode infini", discord.ButtonStyle.primary),
                ("stop", "🏁 Arrêter ici", discord.ButtonStyle.secondary),
            ],
        )
        if choice == "ngplus":
            async with self._session() as session:
                await db.set_ng_plus(session, guild_id, user_id, ng + 1)
                await session.commit()
            run = self.active_runs.pop(user_id, None)
            if run is not None:
                await self._bank_gold_to_or(guild_id, user_id, run.player.gold)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="🔄",
                    title=f"New Game+{ng + 1}",
                    description="Relance la Tour via le bouton 🏰 Entrer pour recommencer, plus fort que jamais.",
                    color=embeds.COLOR_VICTORY,
                )
            )
            return False
        if choice == "infinite":
            async with self._session() as session:
                await db.set_player_flag(session, guild_id, user_id, "infinite_mode_reached", True)
                await session.commit()
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="♾️",
                    title="Mode infini",
                    description="Tu poursuis ton ascension dans les hauteurs infinies de la Tour...",
                    color=embeds.COLOR_VICTORY,
                )
            )
            return True
        run = self.active_runs.pop(user_id, None)
        if run is not None:
            await self._bank_gold_to_or(guild_id, user_id, run.player.gold)
        await ctx.send(
            embed=embeds.room_embed(
                emoji="🏁",
                title="Fin de l'aventure",
                description="Tu poses ton arme, satisfait. La Tour se souvient de ta victoire.",
                color=embeds.COLOR_VICTORY,
            )
        )
        return False


class _ConvertModal(discord.ui.Modal):
    def __init__(self, cog: "TourCog", guild_id: int, user_id: int) -> None:
        super().__init__(title="Convertir Or → credits")
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.amount = discord.ui.TextInput(
            label="Montant à convertir", style=discord.TextStyle.short, placeholder="0"
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.amount.value.strip()
        if not text.isdigit():
            await interaction.response.send_message("❌ Montant invalide.", ephemeral=True)
            return
        amount = int(text)
        msg = await self.cog._do_convert(self.guild_id, self.user_id, amount)
        await interaction.response.send_message(msg, ephemeral=True)


class _OrView(discord.ui.View):
    def __init__(self, cog: "TourCog", guild_id: int, user_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="Convertir", emoji="💱", style=discord.ButtonStyle.success)
    async def _convert(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(_ConvertModal(self.cog, self.guild_id, self.user_id))

    @discord.ui.button(label="Fermer", emoji="❌", style=discord.ButtonStyle.secondary)
    async def _close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass


class TourPanelView(discord.ui.View):
    """Panneau de la Tour : remplace les commandes !tour/!abandon/!or/!codex."""

    def __init__(self, cog: "TourCog") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Entrer", emoji="🏰", style=discord.ButtonStyle.primary)
    async def _enter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        if user_id in self.cog.tasks:
            await interaction.response.send_message("Tu as déjà une run en cours !", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        channel = await _get_or_create_tower_channel(interaction.guild, interaction.user)
        ctx = _InteractionContext(interaction, target_channel=channel)
        asyncio.create_task(self.cog._run_tour_flow(ctx, guild_id, user_id))

    @discord.ui.button(label="Abandonner", emoji="🏳️", style=discord.ButtonStyle.danger)
    async def _abandon(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = _find_tower_channel(interaction.guild, interaction.user)
        ctx = _InteractionContext(interaction, target_channel=channel)
        await self.cog._do_abandon(ctx, interaction.guild.id, interaction.user.id)

    @discord.ui.button(label="Or", emoji="💰", style=discord.ButtonStyle.secondary)
    async def _or(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        balance = await self.cog._show_or(guild_id, user_id)
        await interaction.response.send_message(
            f"💰 Tu as **{balance}** Or.", ephemeral=True, view=_OrView(self.cog, guild_id, user_id)
        )

    @discord.ui.button(label="Codex", emoji="📖", style=discord.ButtonStyle.secondary)
    async def _codex(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = _find_tower_channel(interaction.guild, interaction.user)
        ctx = _InteractionContext(interaction, target_channel=channel)
        await self.cog._show_codex(ctx, interaction.guild.id, interaction.user.id)

    @discord.ui.button(label="Équipement", emoji="🗡️", style=discord.ButtonStyle.secondary)
    async def _equip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = _find_tower_channel(interaction.guild, interaction.user)
        ctx = _InteractionContext(interaction, target_channel=channel)
        await self.cog._manage_equipment(ctx, interaction.guild.id, interaction.user.id)


async def setup(bot) -> None:
    await bot.add_cog(TourCog(bot))
