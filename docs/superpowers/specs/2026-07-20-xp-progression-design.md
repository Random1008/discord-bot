# Colombina — Design : Tranche B (XP & Progression)

## Contexte

Tranche A (Fondations) est terminée et mergée sur `main` : structure du projet, Docker, les 12 tables SQLAlchemy, migrations Alembic + seed data, client Redis, logging, bot qui démarre. Aucune logique métier n'existe encore.

Cette tranche implémente le cœur du système de progression : gain d'XP (messages, vocal, réactions, événements, invitations), niveaux, octroi automatique des récompenses de palier, un sous-ensemble des badges, le prestige, et la mécanique de drop de clés de coffre.

Rappel de l'ordre global des tranches (voir le design de la tranche A) : **A** (fait) → **B** (ce document) → C (Économie/Boutique) → D (Profil/Stats/Classements) → E (Anti-abus) → F (Admin). Dashboard FastAPI hors périmètre.

## Décisions structurantes (issues du brainstorming)

- **Le niveau ne redescend jamais.** Le prestige (I à IV) est un simple marqueur atteint aux niveaux 100/200/300/500 — pas un reset. Chaque palier de `rewards` n'est donc franchi qu'une seule fois dans la vie du compte : la détection "niveau X→Y suite à ce gain d'XP" suffit à décider quoi accorder, sans table de suivi séparée.
- **Pas de cooldown sur l'XP de message** (contrairement au brief initial qui mentionnait 60s) — décision explicite de l'utilisateur : chaque message envoyé donne 5-15 XP.
- **Suivi vocal par événements** (`on_voice_state_update`), pas par boucle périodique.
- **Invitation validée** = quand l'invité atteint le **niveau 5** (pas à l'arrivée). L'inviteur reçoit alors +200 XP.
- **Bonus événement** : commande admin dédiée `/event-participation @membre` (+50 XP), indépendante des commandes admin génériques de la tranche F.
- **Badges "classement"** (Roi du Chat, Maître Vocal, Top 10, Ancien) reportés à la tranche D — cette tranche n'implémente que les badges liés à un palier de niveau + Inviteur.
- **Coffre Mystère** : `idea/idea-mysterybox.md` décrit un système complet de loot (6 raretés, ~180 objets) qui dépend de systèmes futurs (boutique, profil, pets...). Cette tranche implémente uniquement la **mécanique de drop de clés** liée à la montée de niveau ; l'ouverture de coffre et la table de loot complète deviendront une tranche dédiée plus tard.

## Schéma : additions à la tranche A

| Changement | Table | Détail |
|---|---|---|
| Nouvelle colonne | `users.invited_by_id` | `BigInteger`, nullable, FK → `users.discord_id`. Renseignée à l'arrivée d'un membre via diff des compteurs d'usage des invitations (cache en mémoire, rafraîchi au démarrage via `guild.invites()` et à chaque `on_invite_create`) |
| Nouvelle colonne | `levels.last_key_drop_level` | `Integer`, `default=0` — niveau auquel la dernière clé de coffre a été obtenue |
| Nouvelle table | `user_keys` | `id` PK, `user_id` FK, `rarity` (String), `count` (Integer, `default=0`), `UniqueConstraint(user_id, rarity)` — inventaire minimal de clés, pas d'ouverture dans cette tranche |

Migration Alembic incrémentale (pas de refonte du schéma existant).

## Gain d'XP

Toute la logique de calcul vit dans `services/xp.py` (pure, testable sans mocker Discord) :

| Source | Règle | Déclencheur |
|---|---|---|
| Message | 5-15 XP aléatoire, **sans cooldown** | `on_message` (ignore les bots) |
| Vocal | 10 XP / 10 min, 0 si seul dans le salon | `on_voice_state_update` : accumulation continue du temps où ≥2 membres humains étaient présents, XP calculée à la sortie/au changement de salon |
| Réaction reçue | +2 XP à l'auteur du message | `on_reaction_add` ; l'auto-réaction ne compte pas. Symétrique côté retrait : `on_reaction_remove` retire les 2 XP correspondants (`on_reaction_remove` ignore aussi l'auto-réaction). Anti-farm : un cycle ajout/retrait est neutre en XP net, empêchant de faire gagner de l'XP en boucle via ajout/retrait répété. La XP totale d'un utilisateur ne descend jamais sous le seuil de son niveau actuel (le niveau, une fois atteint, ne redescend jamais — voir décisions structurantes) |
| Participation événement | +50 XP | Commande admin `/event-participation @membre` |
| Invitation validée | +200 XP à l'inviteur | Déclenché quand l'invité atteint le **niveau 5** (vérifie `invited_by_id` au moment de ce level-up précis) |

Le multiplicateur de prestige (voir plus bas) s'applique à **tous** les gains d'XP ci-dessus.

## Niveau, level-up & récompenses de palier

- Formule (vérifiée contre tous les exemples du brief) : XP totale requise pour le niveau N = `100 × N²`. Niveau courant = `floor(sqrt(xp_totale / 100))`.
- `services/leveling.py::add_xp(session, user_id, amount)` : ajoute l'XP (après application du multiplicateur de prestige), recalcule le niveau, et si le niveau a augmenté — potentiellement de plusieurs paliers d'un coup (ex. +200 XP d'invitation) — **itère chaque niveau franchi dans l'ordre** pour déclencher ses effets (récompenses de palier + jet de clé de coffre, voir plus bas).
- Octroi des récompenses (table `rewards`, déjà seedée en tranche A) selon `reward_type` :
  - `badge` → insertion `user_badges` (uniquement pour les badges en périmètre, voir section Badges)
  - `role` / `access` → attribution d'un rôle Discord (ID configuré via `.env`, mappé par `reward_value`)
  - `coins` → crédite `economy.balance` via une nouvelle fonction minimale `services/economy.py::add_balance(session, user_id, amount)` (juste la mutation ; les commandes `/balance /pay /daily /shop` restent tranche C)
  - `item` (Coffre Mystère, niveau 90) → octroie une clé de coffre de rareté aléatoire, tirée avec la même distribution que le drop de clé par niveau (voir section Clés de coffre), en attendant le vrai système d'inventaire/coffres
  - `title` (Titre Exclusif, niveau 70) → aucun système de titre de profil pour l'instant (tranche D) ; l'annonce du level-up le mentionne textuellement, rien n'est stocké mécaniquement
- Annonce dans un salon configuré (`LEVEL_UP_CHANNEL_ID`) à chaque level-up et à chaque récompense de palier obtenue.

## Clés de coffre (mécanique de drop uniquement)

À chaque niveau franchi (dans la même boucle que l'octroi des récompenses) :

1. Calcule `niveaux_ecoules = niveau_actuel - levels.last_key_drop_level`.
2. Si `niveaux_ecoules` ∈ {5, 10, 15, 20, 25} → jet avec la probabilité correspondante :

   | Niveaux écoulés depuis la dernière clé | Chance |
   |---|---|
   | 5 | 15% |
   | 10 | 25% |
   | 15 | 50% |
   | 20 | 75% |
   | 25 | 100% (garanti) |

3. En cas de succès : tire une rareté selon la distribution globale de `idea-mysterybox.md` (Commun 60% / Rare 25% / Épique 10% / Légendaire 3.5% / Mythique 1% / Divin 0.5%), incrémente `user_keys` pour cette rareté, remet `levels.last_key_drop_level = niveau_actuel`.
4. Aucune commande pour dépenser/ouvrir une clé dans cette tranche.

## Badges (périmètre limité)

Implémentés dans cette tranche (tous déjà seedés en tranche A) : Débutant, Actif, Habitué, Vétéran, Légendaire, Argent, Or, Platine, Diamant (tous octroyés via la table `rewards` à leur palier de niveau respectif) + Inviteur (octroyé au moment où l'invitation est validée, niveau 5 de l'invité).

Reportés à la tranche D (nécessitent un système de classement) : Roi du Chat, Maître Vocal, Top 10, Ancien.

## Prestige

- Détecté quand le niveau atteint 100 (Prestige I), 200 (II), 300 (III), 500 (IV) — pas de reset, conforme à la clarification de l'utilisateur.
- Implémenté dans cette tranche :
  - **Multiplicateur d'XP** appliqué à tous les gains futurs : +10% (I), +20% (II), +30% (III), +50% (IV), stocké/dérivé de `levels.prestige`.
  - **Rôle Discord** attribué par palier, configuré via `.env` (`PRESTIGE_1_ROLE_ID` … `PRESTIGE_4_ROLE_ID`).
- Reportés (nécessitent des systèmes qui n'existent pas encore) : couleurs exclusives et fond de profil (tranche D), salons exclusifs et emotes personnalisées (à évaluer plus tard).

## Configuration additionnelle (`.env` / `config/settings.py`)

Nouvelles variables (rôles/salon), en plus de celles déjà posées en tranche A :
`LEVEL_UP_CHANNEL_ID`, `ROLE_VIP_BRONZE_ID`, `ROLE_VIP_ARGENT_ID`, `ROLE_PREMIUM_ID`, `PRESTIGE_1_ROLE_ID`, `PRESTIGE_2_ROLE_ID`, `PRESTIGE_3_ROLE_ID`, `PRESTIGE_4_ROLE_ID`.

## Tests & architecture

- Toute la logique (formule de niveau, calcul XP, octroi de récompenses, jet de clé) vit dans `services/` — pure, testée sans mocker Discord (même approche que la tranche A pour `utils/`).
- Les cogs (`cogs/leveling.py`, `cogs/invites.py`, etc.) restent de fins adaptateurs événements Discord → appels aux services.
- Persistance des relations « qui a invité qui » via cache en mémoire pour le diff des invitations (pas de table dédiée aux invitations elles-mêmes, seulement `users.invited_by_id`).

## Hors périmètre de cette tranche

- Ouverture de coffre et table de loot complète de `idea-mysterybox.md` (tranche dédiée future).
- Badges liés à un classement (tranche D).
- Cosmétiques de prestige (couleurs, fond de profil — tranche D ; salons/emotes exclusifs — à évaluer).
- Commandes `/balance /pay /daily /shop` (tranche C) — seule la mutation de solde nécessaire à l'octroi des récompenses est ajoutée ici.
- Détection d'abus sur les gains d'XP (tranche E).
- Commandes admin génériques `/setlevel /addxp` etc. (tranche F) — seule `/event-participation` est ajoutée ici, car elle correspond directement à un bonus d'XP du brief.
