"""Combat methods for TourCog - extracted from tour.py (mixin pattern)."""
import random

import discord
from discord.ext import commands

from cogs import _tour_embeds as embeds
from cogs import _tour_ui as ui
from cogs._tour_ui import RunEnded
import services.rpg_db as db
from services.rpg.achievements import PlayerStats
from services.rpg.combat import resolve_round
from services.rpg.monsters import spawn_monster
from services.rpg.potions import get_potion
from services.rpg.progression import add_xp, apply_combat_start_bonus, xp_reward_for_monster
from services.rpg.render import render_scene
from services.rpg.shop import use_item

MONSTER_DROP_CHANCE = 0.08


class TourCombatMixin:
    """Combat methods mixed into TourCog."""

    @staticmethod
    def _combat_button_labels(can_flee: bool) -> list[str]:
        labels = ["COMBAT", "ACTE", "OBJET"]
        if can_flee:
            labels.append("PITIÉ")
        return labels

    @staticmethod
    def _default_act_text(target) -> str:
        lines = [
            f"{target.name}",
            f"PV : {max(0, target.hp)}/{target.max_hp}",
            f"ATK : {target.atk}",
            f"DEF : {target.defense}",
        ]
        gimmick = getattr(target, "gimmick", None)
        if gimmick is not None:
            blurb = embeds.GIMMICK_BLURBS.get(gimmick)
            if blurb:
                lines.append(blurb)
        return "\n".join(lines)

    @staticmethod
    def _bag_name(key: str) -> str:
        potion = get_potion(key)
        return potion.name if potion is not None else key

    async def _run_combat(
        self,
        ctx: commands.Context,
        guild_id: int,
        run,
        stats: PlayerStats,
        *,
        target,
        intro_text: str,
        resolve_round_fn,
        format_log_fn,
        on_round_fn=None,
        color: int = embeds.COLOR_COMBAT,
        victory_emoji: str = "🎉",
        can_flee: bool = True,
        act_text: str | None = None,
    ) -> str:
        """Boucle de combat façon Undertale : un seul message (image de scène
        + boutons COMBAT/ACTE/OBJET/PITIÉ) édité à chaque round. Retourne
        "victory" ou "fled". En cas de mort, gère _handle_death et lève
        RunEnded."""
        player = run.player
        log_lines: list[str] = [intro_text]

        # Effets de début de combat.
        if player.copy_enemy_stats_ratio:
            copied = round(target.atk * player.copy_enemy_stats_ratio)
            player.atk += copied
            log_lines.append(f"🗡️ Tu copies une part de la puissance de {target.name} (+{copied} ATK).")
        bonus = apply_combat_start_bonus(player, random)
        if bonus:
            log_lines.append(f"✨ {bonus}")

        def _dialogue() -> str:
            return log_lines[-1] if log_lines else intro_text

        def _scene_file() -> discord.File:
            buf = render_scene(
                player_name=ctx.author.display_name,
                level=player.level,
                hp=player.hp,
                max_hp=player.max_hp,
                gold=player.gold,
                enemy_name=target.name,
                dialogue=_dialogue(),
                buttons=self._combat_button_labels(can_flee),
            )
            return discord.File(buf, "scene.png")

        message = await ctx.send(file=_scene_file())

        while True:
            options = [
                ("combat", "⚔️ COMBAT", discord.ButtonStyle.danger),
                ("acte", "👁️ ACTE", discord.ButtonStyle.primary),
                ("objet", "🎒 OBJET", discord.ButtonStyle.secondary),
            ]
            if can_flee:
                options.append(("pitie", "🕊️ PITIÉ", discord.ButtonStyle.secondary))
            choice = await ui.attach_choice(
                message, ctx.author.id, options, attachments=[_scene_file()]
            )

            if choice == "pitie":
                log_lines.append(f"🕊️ Tu épargnes **{target.name}** et t'éloignes.")
                await message.edit(view=None, attachments=[_scene_file()])
                return "fled"

            if choice == "acte":
                info = act_text or self._default_act_text(target)
                log_lines.append(f"👁️ {info}")
                result = resolve_round_fn(player, target, random, player_attacks=False)
                if on_round_fn is not None:
                    on_round_fn(result)
                log_lines.append(f"Riposte : {result.monster_damage_dealt} dégâts.")
            elif choice == "objet":
                if not player.bag:
                    log_lines.append("🎒 Ton sac est vide.")
                    continue
                bag_items = sorted(set(player.bag))
                bag_options = [(key, self._bag_name(key), None) for key in bag_items]
                bag_options.append(("cancel", "↩️ Retour", None))
                pick = await ui.ask_select(
                    ctx,
                    embeds.room_embed(
                        emoji="🎒",
                        title="Sac",
                        description="Choisis un objet à utiliser.",
                        color=embeds.COLOR_SHOP,
                    ),
                    bag_options,
                    "Choisis un objet",
                )
                if pick == "cancel":
                    continue
                effect_msg = use_item(player, pick)
                log_lines.append(f"🎒 {effect_msg}")
                result = resolve_round_fn(player, target, random, player_attacks=False)
                if on_round_fn is not None:
                    on_round_fn(result)
                log_lines.append(f"Riposte : {result.monster_damage_dealt} dégâts.")
            else:  # combat
                result = resolve_round_fn(player, target, random)
                if on_round_fn is not None:
                    on_round_fn(result)
                log_lines.extend(format_log_fn(result))

            if not target.is_alive():
                log_lines.append(f"{victory_emoji} **{target.name}** est vaincu !")
                await message.edit(view=None, attachments=[_scene_file()])
                return "victory"

            if not player.is_alive():
                await message.edit(view=None, attachments=[_scene_file()])
                await self._handle_death(ctx, guild_id, run, stats)
                raise RunEnded()

    async def _fight_monster(self, ctx: commands.Context, guild_id: int, run, stats: PlayerStats) -> None:
        player = run.player
        async with self._session() as session:
            ng = await db.get_ng_plus(session, guild_id, ctx.author.id)
            await session.commit()
        monster = spawn_monster(run.floor.number, random, ng_plus=ng)

        def _format_round(result) -> list[str]:
            return [f"Tu infliges {result.player_damage_dealt} dégâts. Riposte : {result.monster_damage_dealt} dégâts."]

        outcome = await self._run_combat(
            ctx,
            guild_id,
            run,
            stats,
            target=monster,
            intro_text=f"⚔️ Un **{monster.name}** apparaît !",
            resolve_round_fn=resolve_round,
            format_log_fn=_format_round,
            color=embeds.COLOR_COMBAT,
            victory_emoji="🎉",
        )
        if outcome == "victory":
            gained_xp = xp_reward_for_monster(monster)
            levels = add_xp(player, gained_xp)
            stats.monsters_killed += 1
            async with self._session() as session:
                await db.increment_player_stat(session, guild_id, ctx.author.id, "monsters_killed")
                await session.commit()
            await self._add_tower_xp(guild_id, ctx.author.id, gained_xp)
            await ctx.send(
                embed=embeds.room_embed(
                    emoji="🎉",
                    title="Victoire",
                    description=f"Le **{monster.name}** est vaincu ! (+{gained_xp} XP)",
                    color=embeds.COLOR_VICTORY,
                )
            )
            if levels:
                await ctx.send(embed=embeds.level_up_embed(player.level))
            await self._apply_kill_rewards(ctx, guild_id, player)
            await self._maybe_drop_equipment(ctx, guild_id, MONSTER_DROP_CHANCE)
            await self._check_achievements(ctx, guild_id, stats)
            await self._check_titles(ctx, guild_id, stats)
