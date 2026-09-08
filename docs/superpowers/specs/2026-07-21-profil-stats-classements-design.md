# Colombina — Design : Tranche D (Profil, Stats & Classements)

## Contexte

Tranches A (Fondations), B (XP & Progression) et C (Économie & Boutique, pas encore mergée sur `main` mais présente sur cette branche) sont terminées. Cette tranche implémente `/profile` (carte image + stats détaillées), `/leaderboard` (3 classements), et octroie enfin les 4 badges "classement" seedés en tranche A mais jamais accordés faute de système de classement (Roi du Chat, Maître Vocal, Top 10, Ancien). Elle ajoute aussi 3 rôles Discord hebdomadaires transférables pour le n°1 de chaque classement.

Rappel de l'ordre global : A (fait) → B (fait) → C (fait, pas mergée) → **D (ce document)** → E (Anti-abus) → F (Admin).

## Décisions structurantes (issues du brainstorming)

- **Pas de `/stats` séparé** : ses données (messages, temps vocal, quêtes du jour, clés) sont fusionnées dans `/profile`, en embed texte sous la carte image, dans le même message.
- **Carte `/profile` volontairement simple** : avatar, pseudo, niveau + barre XP, prestige, solde de coins, badges débloqués — pas de cosmétiques achetables (couleurs/fonds de la boutique, hors périmètre), pas d'émojis graphiques pour les badges (Pillow pur ne rend pas bien les emojis couleur ; les badges sont listés en texte).
- **Police Pillow par défaut** (`ImageFont.load_default()`) — pas de fichier de police externe à embarquer pour cette tranche, améliorable plus tard.
- **`/leaderboard type:xp|messages|vocal`** : 3 classements top 10, calculés respectivement sur `levels.xp`, `SUM(message_stats.count)`, `SUM(voice_stats.seconds)` par utilisateur.
- **Badges permanents, jamais révoqués** (cohérent avec le reste du système de badges) :
  - Roi du Chat → a été n°1 messages au moins une fois
  - Maître Vocal → a été n°1 vocal au moins une fois
  - Top 10 → a atteint le top 10 XP au moins une fois (cumulatif : plusieurs personnes différentes peuvent le débloquer au fil des semaines)
  - Ancien → compte connu du bot (`users.created_at`) depuis ≥ **365 jours**
- **3 rôles Discord hebdomadaires, transférables** (distincts des badges permanents) : donnés au n°1 actuel de chaque classement (messages/vocal/XP), retirés à l'ancien détenteur quand le n°1 change. Pas de nouvel état en base pour savoir qui détient le rôle — interrogé directement sur Discord (`role.members`) à chaque passage.
- **Configuration des rôles hebdomadaires via un fichier dédié** (pas `.env`/`settings.py` comme les autres rôles du bot — choix explicite de l'utilisateur) : `colombina/config/leaderboard_roles.txt`, format `clé: id_role_discord` (une ligne par classement : `roi_du_chat`, `maitre_vocal`, `top_10`), relu à chaque passage (pas de redémarrage nécessaire pour changer un ID). Fichier déjà créé avec les 3 clés vides, à remplir par l'utilisateur.
- **Tâche périodique unique** (`discord.py` `tasks.loop(hours=168)`, démarre au chargement du cog, pas d'heure calendaire précise) qui, à chaque passage : recalcule les 3 classements, octroie les 4 badges aux utilisateurs qualifiés (idempotent, réutilise `services/rewards.py`'s badge-grant existant de la tranche B), et fait tourner les 3 rôles hebdomadaires.
- **Tracking quotidien `message_stats`/`voice_stats`** : rien ne les alimente actuellement. Ajout d'un incrément dans les mêmes points d'accroche déjà utilisés pour l'XP/les quêtes (`cogs/leveling.py::on_message`, `cogs/voice.py::on_voice_state_update`) — même schéma que le tracking de quêtes de la tranche C.
- **`server_stats` reste hors périmètre** : rien dans cette tranche ne le lit ni ne l'alimente (aucune commande n'en a besoin).

## Schéma

Aucune nouvelle table. `message_stats`/`voice_stats`/`badges`/`user_badges`/`users.created_at` existent déjà depuis la tranche A.

## Commandes utilisateur

| Commande | Effet |
|---|---|
| `/profile [@membre]` | Génère et envoie la carte image (avatar, pseudo, niveau, barre XP, prestige, coins, badges) du membre ciblé (soi-même par défaut), accompagnée d'un embed texte (messages envoyés, temps vocal total, progression des 3 quêtes du jour, clés par rareté) |
| `/leaderboard type:xp\|messages\|vocal` | Top 10 du classement demandé (embed texte, pas d'image) |

## Tracking quotidien

Dans `cogs/leveling.py::on_message` (après le tracking de quêtes existant) : incrémente `message_stats` (get-or-create la ligne du jour, `count += 1`).
Dans `cogs/voice.py::on_voice_state_update` (au même point que le paiement XP/quête vocale) : incrémente `voice_stats` (get-or-create la ligne du jour, `seconds += payable_seconds`).

## Badges et rôles de classement

Nouveau cog avec une tâche périodique (`tasks.loop(hours=168)`) :

1. Calcule les 3 classements (XP desc, messages desc, vocal desc).
2. Octroie (idempotent) : Roi du Chat au n°1 messages, Maître Vocal au n°1 vocal, Top 10 à chacun du top 10 XP, Ancien à tout utilisateur avec `now - users.created_at >= 365 jours`.
3. Lit `config/leaderboard_roles.txt`, pour chaque classement avec un ID de rôle configuré : retire le rôle à tous ses détenteurs actuels (`role.members`) sauf le n°1 actuel, puis l'assigne au n°1 s'il ne l'a pas déjà.

## Tests & architecture

- Logique de classement (agrégation, calcul des qualifiés aux badges), parsing du fichier de config des rôles, et génération de la carte Pillow dans `services/`, testables sans mocker Discord (la génération d'image accepte les bytes d'avatar déjà récupérés en paramètre, pas d'appel réseau dans le service).
- Les cogs restent de fins adaptateurs (fetch avatar/membres Discord, appels aux services, envoi des messages).

## Hors périmètre de cette tranche

- Cosmétiques achetables (couleurs/fonds de profil) sur la carte `/profile` — dépend d'un système de boutique cosmétique non construit.
- Police/emojis graphiques personnalisés sur la carte.
- `server_stats` (ni lu ni alimenté).
- Historique/pagination du classement au-delà du top 10.
- Persistance de qui détient un rôle hebdomadaire (interrogé en direct sur Discord à chaque passage).
