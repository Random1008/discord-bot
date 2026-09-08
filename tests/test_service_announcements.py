from services.announcements import (
    format_key_drop_message,
    format_level_up_message,
    format_prestige_message,
    format_reward_message,
)
from services.leveling import KeyDrop
from services.rewards import RewardOutcome


def test_format_level_up_message():
    assert format_level_up_message("Ashen", 5) == "🎉 **Ashen** a atteint le niveau **5** !"


def test_format_reward_message_badge():
    outcome = RewardOutcome(reward_type="badge", reward_value="debutant", detail="debutant")
    assert format_reward_message("Ashen", outcome) == "✨ **Ashen** a débloqué le badge : debutant"


def test_format_reward_message_coins():
    outcome = RewardOutcome(reward_type="coins", reward_value="1000", detail="1000 coins")
    assert format_reward_message("Ashen", outcome) == "✨ **Ashen** a reçu : 1000 coins"


def test_format_reward_message_item_includes_key_usage_hint():
    outcome = RewardOutcome(reward_type="item", reward_value="rare", detail="clé rare")
    message = format_reward_message("Ashen", outcome)
    assert message == "✨ **Ashen** a reçu : clé rare Fais `$key` pour l'ouvrir !"


def test_format_prestige_message():
    assert format_prestige_message("Ashen", 2) == "🌟 **Ashen** atteint le **Prestige II** !"


def test_format_key_drop_message_includes_rarity_level_and_usage_hint():
    drop = KeyDrop(level=10, rarity="rare")
    message = format_key_drop_message("Ashen", drop)
    assert message == "🔑 **Ashen** a obtenu une clé **🔵 Rare** (niveau 10) ! Fais `$key` pour l'ouvrir."


def test_format_key_drop_message_falls_back_to_raw_rarity_if_unknown():
    drop = KeyDrop(level=25, rarity="inconnue")
    message = format_key_drop_message("Ashen", drop)
    assert "inconnue" in message
