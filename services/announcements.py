from services.leveling import KeyDrop
from services.rewards import RewardOutcome

_REWARD_LABELS = {
    "badge": "a débloqué le badge",
    "coins": "a reçu",
    "role": "a débloqué le rôle",
    "access": "a débloqué l'accès",
    "item": "a reçu",
    "title": "a débloqué le titre",
}

# Rappel d'usage affiché après le message de récompense, uniquement pour les
# types qui demandent une action du joueur (les autres — rôle, coins,
# badge... — sont déjà utilisables/visibles sans rien faire).
_REWARD_USAGE_HINTS = {
    "item": "Fais `$key` pour l'ouvrir !",
}

_KEY_RARITY_LABELS = {
    "commun": "🟢 Commune",
    "rare": "🔵 Rare",
    "epique": "🟣 Épique",
    "legendaire": "🟠 Légendaire",
    "mythique": "🔴 Mythique",
    "divin": "⚪ Divine",
}

_PRESTIGE_NUMERALS = {1: "I", 2: "II", 3: "III", 4: "IV"}


def format_level_up_message(display_name: str, level: int) -> str:
    return f"🎉 **{display_name}** a atteint le niveau **{level}** !"


def format_reward_message(display_name: str, outcome: RewardOutcome) -> str:
    label = _REWARD_LABELS.get(outcome.reward_type, "a reçu")
    message = f"✨ **{display_name}** {label} : {outcome.detail}"
    hint = _REWARD_USAGE_HINTS.get(outcome.reward_type)
    if hint:
        message += f" {hint}"
    return message


def format_key_drop_message(display_name: str, drop: KeyDrop) -> str:
    rarity_label = _KEY_RARITY_LABELS.get(drop.rarity, drop.rarity)
    return (
        f"🔑 **{display_name}** a obtenu une clé **{rarity_label}** (niveau {drop.level}) ! "
        "Fais `$key` pour l'ouvrir."
    )


def format_prestige_message(display_name: str, prestige: int) -> str:
    numeral = _PRESTIGE_NUMERALS.get(prestige, str(prestige))
    return f"🌟 **{display_name}** atteint le **Prestige {numeral}** !"
