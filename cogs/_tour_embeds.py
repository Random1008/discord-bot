"""Constructeurs d'embeds pour la Tour RPG (cogs/tour.py).

Préfixé par `_` pour que utils/cog_loader.py ne tente pas de le charger
comme une extension à part.
"""

import discord

from services.rpg.bosses import BossGimmick
from services.rpg.classes import CharacterClass
from services.rpg.status_effects import StatusEffectKind

COLOR_COMBAT = 0xE74C3C
COLOR_BOSS = 0x8B0000
COLOR_TRESOR = 0xF1C40F
COLOR_REPOS = 0x2ECC71
COLOR_PIEGE = 0xE67E22
COLOR_ENIGME = 0x9B59B6
COLOR_EVENEMENT = 0x3498DB
COLOR_SHOP = 0x27AE60
COLOR_DEATH = 0x1C1C1C
COLOR_VICTORY = 0xF1C40F
COLOR_NEUTRAL = 0x5865F2


def hp_bar(hp: int, max_hp: int, width: int = 10) -> str:
    hp = max(0, hp)
    filled = round(width * hp / max_hp) if max_hp else 0
    filled = max(0, min(width, filled))
    return f"{'█' * filled}{'░' * (width - filled)} {hp}/{max_hp}"


CLASS_BLURBS: dict[CharacterClass, str] = {
    CharacterClass.BERSERKER: "Seuil bas PV 30%, +80% dégâts sous ce seuil",
    CharacterClass.GARDIEN: "+8 défense, 1 charge de blocage",
    CharacterClass.ASSASSIN: "+40% critique (x3), +25% esquive",
    CharacterClass.MAGE_INSTABLE: "Attaque instable, ATK de base x1.8",
    CharacterClass.LAME_SANGUINE: "30% vol de vie",
    CharacterClass.AVENTURIER_CHANCEUX: "+15% critique, +10% esquive, x1.3 or",
    CharacterClass.OCCULTISTE: "30% de maudire l'ennemi en frappant",
    CharacterClass.ALCHIMISTE: "Potions 50% plus efficaces",
    CharacterClass.PALADIN: "+5 défense, soins renforcés",
    CharacterClass.CHASSEUR: "+30% dégâts contre les monstres",
    CharacterClass.INVOCATEUR: "+8 dégâts d'invocation par round",
    CharacterClass.DUELISTE: "+40% dégâts contre les boss",
    CharacterClass.MOINE: "Combo : +15% par coup consécutif",
    CharacterClass.NECROMANCIEN: "Soin + ATK à chaque ennemi vaincu",
    CharacterClass.CHRONOMANCIEN: "20% de geler l'ennemi",
    CharacterClass.CHEVALIER_NOIR: "ATK x1.4, HP max -20%",
    CharacterClass.REVENANT: "+1 vie supplémentaire",
    CharacterClass.GARDIEN_DU_NEANT: "Immunité aux effets de statut",
    CharacterClass.HERITIER_DE_LA_TOUR: "Bonus de legacy +50%",
    CharacterClass.ELU_DU_CREATEUR: "Stats qui montent à chaque étage",
}

GIMMICK_BLURBS: dict[BossGimmick, str] = {
    BossGimmick.GARDIEN_MIROIR: "Renvoie 30% des dégâts infligés par le joueur.",
    BossGimmick.BOUCHER_AFFAME: "Se soigne de 40% des dégâts qu'il inflige.",
    BossGimmick.ROI_PARESSEUX: "+3 ATK à chaque tour (monte en puissance).",
    BossGimmick.BETE_INSTABLE: "ATK/défense changent aléatoirement chaque tour.",
    BossGimmick.HORLOGER_DE_LA_TOUR: "50% de chance de figer ton attaque chaque tour.",
    BossGimmick.FAUX_HEROS: "Copie exacte de tes propres statistiques.",
    BossGimmick.LE_COEUR_DE_LA_TOUR: "Combat en 3 phases, capacités évolutives.",
}

STATUS_EMOJI: dict[StatusEffectKind, str] = {
    StatusEffectKind.BRULURE: "🔥",
    StatusEffectKind.SAIGNEMENT: "🩸",
    StatusEffectKind.GEL: "❄️",
    StatusEffectKind.RAGE: "💢",
    StatusEffectKind.MALEDICTION: "🌑",
    StatusEffectKind.GARDE: "🛡️",
    StatusEffectKind.PRECISION: "🎯",
    StatusEffectKind.AGILITE: "💨",
    StatusEffectKind.VAMPIRISME: "🩸",
    StatusEffectKind.BRULURE_ATTAQUE: "🔥",
    StatusEffectKind.GEL_ATTAQUE: "❄️",
}


def floor_banner_embed(floor_number: int, ng_plus: int) -> discord.Embed:
    title = f"🏰 Étage {floor_number}"
    embed = discord.Embed(title=title, color=COLOR_NEUTRAL)
    if ng_plus > 0:
        embed.set_footer(text=f"New Game+{ng_plus}")
    return embed


def class_select_embed(tower_level: int, available: int, total: int) -> discord.Embed:
    return discord.Embed(
        title="🧙 Choisis ta classe",
        description=(
            f"⭐ Niveau de la Tour : **{tower_level}** — {available}/{total} classes débloquées.\n"
            "Un trait aléatoire sera aussi tiré, cumulatif avec ta classe."
        ),
        color=COLOR_NEUTRAL,
    )


def or_spend_embed(or_balance: int) -> discord.Embed:
    return discord.Embed(
        title="💰 Or de départ",
        description=f"Tu as **{or_balance}** Or en banque. Choisis combien en emporter pour cette run (0-{or_balance}).",
        color=COLOR_NEUTRAL,
    )


def run_start_embed(class_name: str, trait_name: str) -> discord.Embed:
    return discord.Embed(
        title="🚪 La Tour t'attend...",
        description=f"Tu incarnes un **{class_name}** avec le trait **{trait_name}**.",
        color=COLOR_NEUTRAL,
    )


def combat_embed(
    *,
    title: str,
    player_name: str,
    player_hp: int,
    player_max_hp: int,
    target_name: str,
    target_hp: int,
    target_max_hp: int,
    gold: int,
    log_lines: list[str],
    color: int = COLOR_COMBAT,
    flavor: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    if flavor:
        embed.description = flavor
    embed.add_field(name=player_name, value=hp_bar(player_hp, player_max_hp), inline=True)
    embed.add_field(name=target_name, value=hp_bar(target_hp, target_max_hp), inline=True)
    if log_lines:
        embed.add_field(name="Journal", value="\n".join(log_lines[-4:]), inline=False)
    embed.set_footer(text=f"💰 {gold} or")
    embed.set_image(url="attachment://scene.png")
    return embed


def room_embed(*, emoji: str, title: str, description: str, color: int) -> discord.Embed:
    return discord.Embed(title=f"{emoji} {title}", description=description, color=color)


def death_embed(floor_reached: int, monsters_killed: int, gold_earned: int, message: str) -> discord.Embed:
    embed = discord.Embed(title="💀 Tu es tombé...", description=message, color=COLOR_DEATH)
    embed.add_field(name="Étage atteint", value=str(floor_reached), inline=True)
    embed.add_field(name="Monstres vaincus", value=str(monsters_killed), inline=True)
    embed.add_field(name="Or récolté", value=str(gold_earned), inline=True)
    return embed


def victory_embed() -> discord.Embed:
    return discord.Embed(
        title="🎉 Tu as vaincu la Tour !",
        description="Étage 100 franchi. La Tour se souviendra de toi.",
        color=COLOR_VICTORY,
    )


def level_up_embed(level: int) -> discord.Embed:
    return discord.Embed(title=f"🎉 Niveau {level} !", color=COLOR_VICTORY)


def achievement_embed(name: str, description: str) -> discord.Embed:
    return discord.Embed(
        title="🏆 Succès débloqué",
        description=f"**{name}** — {description}",
        color=COLOR_VICTORY,
    )


def title_embed(title) -> discord.Embed:
    from services.rpg.rarity import RARITY_COLORS
    return discord.Embed(
        title="🏅 Titre débloqué",
        description=f"**{title.name}** — {title.description}",
        color=RARITY_COLORS.get(title.rarity, COLOR_VICTORY),
    )


def shop_embed(gold: int) -> discord.Embed:
    return discord.Embed(
        title="🛒 Boutique",
        description=f"Tu as **{gold}** or.",
        color=COLOR_SHOP,
    )


def black_market_embed(gold: int) -> discord.Embed:
    return discord.Embed(
        title="🕶️ Marché noir",
        description=f"Tu as **{gold}** or. Objets rares, prix variables.",
        color=COLOR_SHOP,
    )


def new_game_plus_embed() -> discord.Embed:
    return discord.Embed(
        title="🏁 Que fais-tu maintenant ?",
        description="1 vie de plus dans la légende de la Tour t'attend...",
        color=COLOR_VICTORY,
    )
