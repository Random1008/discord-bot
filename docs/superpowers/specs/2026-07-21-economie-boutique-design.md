# Colombina — Design : Tranche C (Économie & Boutique)

## Contexte

Tranches A (Fondations) et B (XP & Progression) sont terminées et mergées sur `main`. La table `economy` (`user_id`, `balance`, `last_daily_at`) et les tables `quests`/`user_quests` (3 quêtes seedées : `messages_25`, `voice_60min`, `channels_3`) existent depuis la tranche A, mais aucune commande utilisateur ni aucun tracking de progression n'existe encore. `services/economy.py::add_balance` existe depuis la tranche B (utilisé en interne pour les récompenses de palier).

Rappel de l'ordre global des tranches : A (fait) → B (fait) → **C (ce document)** → D (Profil/Stats/Classements) → E (Anti-abus) → F (Admin).

Cette tranche implémente : les commandes économie (`/balance /pay /daily`), la boutique (`/shop`, `$shop`, `/buy`), sa gestion admin (`.add market /.remove market /.edit market`), et le tracking + la complétion automatique des 3 quêtes quotidiennes déjà seedées.

## Décisions structurantes (issues du brainstorming)

- **Catalogue à deux types d'objets** : `key` (clé de coffre — effet automatique, octroie une clé via l'infrastructure de la tranche B) et `generic` (objet cosmétique/flavor — aucun effet automatique, juste une déduction de coins ; le rôle cosmétique correspondant est appliqué manuellement par le staff). Ce découpage vient du fait que `.add market` ne prend que `[nom] [prix] [description]` — pas de paramètre pour lier un rôle Discord précis. Les rôles cosmétiques achetables ne sont donc **pas** automatisés dans cette tranche ; à revisiter dans une tranche future si l'automatisation est souhaitée.
- **Règle des 0 coins** : tout objet dont `price == 0` est **impossible à acheter** (0 n'est pas "gratuit", c'est "pas encore activé"). `/shop` et `$shop` n'affichent que les objets avec `price > 0`.
- **7 objets clés seedés à 0 coins** au démarrage de cette tranche (une clé "aléatoire" + une par rareté : Commune, Rare, Épique, Légendaire, Mythique, Divine, mêmes clés de rareté que `services/keys.py` en tranche B) — un admin doit les repricer via `.edit market` pour les rendre achetables.
- **Commandes admin en texte (préfixe du bot), pas en slash** : `.add market`, `.remove market`, `.edit market` — cohérent avec le support prefix+slash déjà posé en tranche A.
- **`/shop` a un double accès** : slash `/shop` et texte `$shop` (alias texte du même handler, via le préfixe configurable du bot — le caractère exact dépend de `COMMAND_PREFIX`, `$` n'est qu'un exemple donné pendant le brainstorming).
- **Achat via commande dédiée** `/buy [nom]`, pas d'interaction boutons/menu dans `/shop` (`/shop` liste, `/buy` achète).
- **Quêtes quotidiennes automatiques** : complétion et octroi de récompense (XP + coins) déclenchés automatiquement dès que `progress >= target_count`, sans commande de "claim" — cohérent avec la philosophie "pas de gate" déjà adoptée pour l'XP en tranche B.
- **`/daily`** : 100 coins, cooldown 24h glissant (basé sur `economy.last_daily_at`) — valeurs par défaut choisies faute de valeurs précisées dans le brief ; ajustables facilement (ce sont de simples constantes).
- **`/pay`** : transfert P2P direct, refuse montant ≤ 0, self-pay, et solde insuffisant.

## Schéma : additions à la tranche A/B

| Changement | Table | Détail |
|---|---|---|
| Nouvelle table | `market_items` | `id` PK, `key` (String, unique, slug), `name` (String), `description` (String), `price` (Integer, `default=0`), `item_type` (String : `"key"` ou `"generic"`), `item_value` (String nullable — rareté pour `item_type="key"`, `NULL` pour `"generic"`) |

Migration Alembic incrémentale (chaîne après la dernière révision de la tranche B) : création de `market_items` + seed des 7 objets clés (`item_type="key"`, `price=0`).

## Commandes utilisateur

| Commande | Effet |
|---|---|
| `/balance` | Affiche le solde de coins de l'utilisateur |
| `/pay @membre [montant]` | Transfère `montant` coins de l'appelant vers `@membre`. Refuse si `montant <= 0`, `membre == auteur`, ou solde insuffisant |
| `/daily` | Crédite 100 coins si `now - economy.last_daily_at >= 24h` (ou si `last_daily_at` est `NULL`) ; sinon message d'erreur indiquant le temps restant. Met à jour `last_daily_at` |
| `/shop` et `$shop` | Liste les `market_items` avec `price > 0`, triés par prix croissant (nom, prix, description) |
| `/buy [nom]` | Achète l'objet `nom` : refuse si l'objet n'existe pas, si `price == 0` (non activé), ou si solde insuffisant. Déduit le prix. Si `item_type == "key"` : octroie la clé correspondante (`item_value == "aleatoire"` → rareté tirée via `services/keys.py::roll_key_rarity`, sinon rareté fixe = `item_value`). Si `item_type == "generic"` : aucun effet automatique au-delà de la déduction, confirmation textuelle à l'acheteur |

## Commandes admin (texte, préfixe du bot)

| Commande | Effet |
|---|---|
| `.add market [nom] [prix] [description]` | Crée un nouvel objet `item_type="generic"` (pas de lien Discord automatique) |
| `.remove market [nom]` | Supprime l'objet du catalogue (par nom) |
| `.edit market [nom] [prix] [description]` | Remplace le prix et la description de l'objet existant (nom identifie l'objet, ne change pas) |

Toutes trois réservées aux administrateurs (même vérification de permission que `/event-participation` en tranche B).

## Quêtes quotidiennes (tracking + complétion)

Logique dans `services/quests.py` (pure autant que possible, testable sans mocker Discord) :

| Quête | Déclencheur | Incrément |
|---|---|---|
| `messages_25` | Chaque message non-bot (`on_message`, même hook que le gain d'XP) | +1 |
| `voice_60min` | Paiement de minutes vocales (même mécanisme que le paiement XP vocal de la tranche B, `VoiceTracker`) | +minutes payées |
| `channels_3` | Chaque message non-bot dans un salon **pas encore utilisé aujourd'hui** par cet utilisateur | +1 (tracking des salons déjà vus aujourd'hui en mémoire, remis à zéro naturellement au changement de date — même profil de simplicité/limite que le cache d'invitations de la tranche B) |

Pour chaque incrément : `get_or_create` la ligne `user_quests` du jour (`UniqueConstraint(user_id, quest_id, date)`), incrémente `progress`, et si `progress >= target_count` et `completed == False` : marque `completed = True`, crédite `xp_reward` (via l'adaptateur `cogs/xp_common.py::award_xp` de la tranche B, pour que les annonces/rôles de palier continuent de fonctionner si la quête fait franchir un niveau) et `coins_reward` (via `services/economy.py::add_balance`).

## Configuration additionnelle (`.env` / `config/settings.py`)

Aucune nouvelle variable requise — les objets `generic` n'ont pas de rôle Discord automatisé dans cette tranche, donc pas de nouvel ID de rôle à configurer.

## Tests & architecture

- Logique d'achat, de transfert, de daily, et de progression de quête dans `services/` (market, economy, quests), pure et testable sans mocker Discord — même approche que les tranches A et B.
- Les cogs (`cogs/economy.py`, `cogs/market.py`, `cogs/quests.py` ou équivalent regroupement) restent de fins adaptateurs événements/commandes Discord → appels aux services.

## Hors périmètre de cette tranche

- Automatisation des rôles cosmétiques (octroi Discord automatique à l'achat) — les objets `generic` sont à fulfillment manuel par le staff dans cette tranche.
- Interaction boutons/menu déroulant dans `/shop` (liste texte uniquement, achat via `/buy` séparé).
- Inventaire d'objets généraux au-delà des clés (`user_keys`, déjà existant) — les objets `generic` n'ont pas de représentation en base au-delà de la transaction de coins.
- Ouverture de coffre et table de loot complète (`idea/idea-mysterybox.md`) — toujours hors périmètre, tranche dédiée future.
- Nouvelles quêtes au-delà des 3 déjà seedées, ou système de rotation quotidienne des quêtes — cette tranche ne fait que tracker/compléter les 3 quêtes fixes existantes.
- Historique des transactions `/pay` (pas de table de log dédiée).
