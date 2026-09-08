"""Boutique de la Tour RPG : vend des potions (communes et peu communes),
rangées dans le sac et utilisées en combat via le bouton OBJET."""

from typing import TYPE_CHECKING

from services.rpg.potions import POTIONS, get_potion
from services.rpg.rarity import Rarity

if TYPE_CHECKING:
    from services.rpg.player import PlayerState

# Potions disponibles en boutique (communes + peu communes). Les rares et plus
# s'obtiennent au marché noir, dans les coffres ou sur les ennemis.
SHOP_CATALOG = [p for p in POTIONS if p.rarity in (Rarity.COMMUNE, Rarity.PEU_COMMUNE)]


def shop_price(player: "PlayerState", potion) -> int:
    """Prix d'une potion après éventuelle réduction (trait Économe)."""
    return max(1, round(potion.price * (1 - player.shop_discount)))


def buy_item(player: "PlayerState", potion) -> str:
    price = shop_price(player, potion)
    if player.gold < price:
        return f"Vous n'avez pas assez d'or pour {potion.name} ({price} or requis)."
    player.add_gold(-price)
    player.bag.append(potion.key)
    return f"{potion.name} rejoint ton sac. Utilise-le en combat via OBJET."


def use_item(player: "PlayerState", key: str) -> str:
    """Consomme une potion du sac."""
    potion = get_potion(key)
    if potion is None:
        return "Objet inconnu."
    if key not in player.bag:
        return "Tu n'as pas cet objet dans ton sac."
    player.bag.remove(key)
    return potion.effect(player)
