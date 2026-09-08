# Bot Discord

Bot Discord unifié : économie, progression (XP/levels), RPG, casino, modération et assistants IA. 
Développé en Python, SQLAlchemy 2 (async) et PostgreSQL.

## Fonctionnalités

- **Économie** : `$daily`, `$work`, `$pay`, boutique/marché, coffres, investissements, crime/braquage
- **Casino & jeu** : blackjack, high-low, poker, machine à sous, tournois
- **Progression** : XP et niveaux (`!rank`, `!level`), rôles récompenses par paliers, prestiges, séries quotidiennes (streaks), succès/badges
- **Profil & classements** : cartes de profil, classements hebdomadaires avec rôles (roi du chat, maître du vocal, plus riche…)
- **RPG / Tour** : tour de donjon, équipement, butin, inventaire, objets cosmétiques, gacha
- **Justice IA** : procès animés par un juge IA (DeepSeek), dépôt de plainte, jurés
- **Suggestions IA** : `!suggest` avec entretien de clarification par IA et validation à deux
- **Modération & anti-abus** : garde anti-aliases, anti-spam, journal des commandes, whitelist de permissions admin (`.permadd`)
- **Divers** : suivi des invitations, compteur vocal, messages de bienvenue configurables, panneaux dynamiques

Les préfixes sont codés en dur dans `main.py` (`["!", "$", ".", "+"]`) et dispatchés par module : `$` pour l'argent, `.` pour l'admin, `+` pour le journal (`+log`), `!` pour le reste.

## Stack

- Python 3.12, discord.py 2.x
- PostgreSQL 16 (asyncpg) + Alembic (migrations)
- Redis (cache/cooldowns/files d'attente)
- pydantic-settings (configuration via `.env`)

## Structure

```
cogs/       commandes (un cog = un domaine)
services/   logique métier (économie, gacha, procès, suggestions…)
models/     modèles ORM SQLAlchemy
database/   engine async + session
config/     settings pydantic (lecture du .env) + configs JSON
utils/      helpers (logging, redis, cooldowns, chargement des cogs)
scripts/    tâches auxiliaires (ex. file de suggestions)
automation_queue/  file de suggestions (montée en volume Docker)
```

## Démarrage rapide

Prérequis : Python 3.12, une base PostgreSQL et un Redis accessibles.

```bash
cp .env.example .env      # puis remplir — voir « Configuration (.env) » ci-dessous
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Au démarrage, le bot exécute les migrations Alembic (voir infra partagée ci-dessous), puis se connecte à Discord.

## Configuration (.env) — tutoriel

### 1. Créer son fichier .env

Le dépôt contient un fichier `.env.example` : c'est un simple marqueur. Le vrai fichier `.env` n'est **jamais** versionné (il est dans le `.gitignore`) car il contient tes secrets.

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
copy .env.example .env
```

Édite ensuite `.env` et renseigne les variables ci-dessous. Le bot les lit au démarrage via `config/settings.py`.

### 2. Variables essentielles

| Variable | Rôle | Où trouver la valeur |
|---|---|---|
| `DISCORD_TOKEN` | Token du bot (obligatoire) | Portail développeur Discord → Applications → ton app → Bot → *Reset Token* |
| `DATABASE_URL` | Connexion PostgreSQL (obligatoire) | `postgresql+asyncpg://utilisateur:motdepasse@hôte:port/base` |
| `REDIS_URL` | Connexion Redis (obligatoire) | `redis://hôte:6379/0` |
| `LOG_LEVEL` | Niveau de log | `DEBUG`, `INFO`, `WARNING`… |
| `SQL_ECHO` | `true` = affiche les requêtes SQL | `false` en production |
| `GUILD_ID` | Serveur principal du bot | Clic droit sur le serveur → *Copier l'ID* (mode développeur) — optionnel : un défaut est codé dans `config/settings.py` |

### 3. Obtenir le token Discord et inviter le bot

1. Rends-toi sur <https://discord.com/developers/applications> → **New Application** (le nom choisi ici sera le nom du bot).
2. Onglet **Bot** → *Reset Token* → copie-le dans `DISCORD_TOKEN`. Ne le partage jamais, ne le commite jamais.
3. Onglet **OAuth2 → URL Generator** : coche `bot` (+ `applications.commands`), choisis les permissions, puis ouvre l'URL générée pour inviter le bot sur ton serveur.
4. Pour **changer le nom du bot**, ce n'est pas dans le `.env` : renomme l'application dans le portail développeur (ou fais un `/nick` si tu veux juste un surnom sur un serveur).

### 4. Activer le mode développeur (pour récupérer les IDs)

Discord → Paramètres utilisateur → **Avancé** → **Mode développeur** → activé. Tu peux alors faire *clic droit* sur un salon, un rôle ou un serveur et choisir **Copier l'ID**.

Toutes les variables d'IDs ci-dessous sont **optionnelles** : laissées vides, la fonctionnalité associée est simplement inactive.

**Salons**
| Variable | Salon concerné |
|---|---|
| `LEVEL_UP_CHANNEL_ID` | Annonces de montée de niveau |
| `ALT_ACCOUNT_ALERT_CHANNEL_ID` | Alertes anti-abus (comptes récemment créés) |
| `SUGGESTION_CHANNEL_ID` | Commandes `!suggest` |
| `SUGGESTION_VALIDATION_CHANNEL_ID` | Validation à deux des suggestions (accepter/refuser) |
| `TOUR_CATEGORY_ID` | Catégorie des salons Tower RPG créés à la demande |
| `MAFIA_CHANNEL_ID` / `PROCES_CHANNEL_ID` | Salons des procès (juge IA) |
| `WELCOME_CHANNEL_ID` / `ADMIN_LOG_CHANNEL_ID` | Messages de bienvenue / journal `+log` |

**Rôles de récompense (XP/leveling)**
| Variable | Rôle |
|---|---|
| `ROLE_ACTIF_ID`, `ROLE_HABITUE_ID`, `ROLE_VETERAN_ID`, `ROLE_LEGENDAIRE_ID` | Paliers de récompense principaux |
| `ROLE_BRONZE_ID`, `ROLE_ARGENT_ID`, `ROLE_OR_ID`, `ROLE_PLATINE_ID`, `ROLE_DIAMANT_ID`, `ROLE_MYTHIQUE_ID` | Échelons intermédiaires (niveaux 10/30/50/70/80/90) |
| `ROLE_VIP_ARGENT_ID`, `ROLE_PREMIUM_ID` | Rôles boutique/économie |
| `PRESTIGE_1_ROLE_ID` … `PRESTIGE_4_ROLE_ID` | Rôles de prestige |

**Rôles de classement hebdomadaire (rotation auto)**
| Variable | Classement |
|---|---|
| `LEADERBOARD_ROI_DU_CHAT_ID` | N°1 messages |
| `LEADERBOARD_MAITRE_VOCAL_ID` | N°1 vocal |
| `LEADERBOARD_RICHE_ID` | N°1 argent |
| `LEADERBOARD_TOP_10_MESSAGE_ID` / `LEADERBOARD_TOP_10_VOCAL_ID` / `LEADERBOARD_TOP_10_ARGENT_ID` | Top 10 de chaque classement |

### 5. Clé IA DeepSeek

`DEEPSEEK_API_KEY` : crée une clé sur <https://platform.deepseek.com> (section *API Keys*). Elle est utilisée par les fonctionnalités IA : entretien de clarification des suggestions et juge des procès. Sans elle, ces fonctions sont indisponibles.

### 6. Vérifier

```bash
python main.py
```

Le bot applique les migrations Alembic au démarrage puis se connecte à Discord. Tape `!help` sur le serveur pour lister les commandes.

### 7. Changer de serveur / copier le bot ailleurs

- `GUILD_ID` : mets l'ID du nouveau serveur.
- Reconfigure les IDs de salons et de rôles (sections 4) : sans eux, leveling, classements, suggestions et procès n'ont pas d'endroit où écrire.
- Le fichier de config `config/leaderboard_roles.txt` liste aussi les rôles de classement (relu au démarrage).
- Pense à une base PostgreSQL et un Redis dédiés (les schémas de tables sont créés/mis à jour par les migrations Alembic au premier démarrage).

## Conteneurisation

Le dossier contient un `Dockerfile` et un `docker-compose.yml`. En production, le bot est construit depuis le workspace de l'écosystème Discord, dont le contexte parent fournit le dossier partagé `shared/` (migrations Alembic communes à tous les bots — colombina, zero-two, makima, giani, yoru). L'`entrypoint.sh` lance `alembic upgrade head` dans ce dossier partagé avant de démarrer `main.py`.

Ce dépôt ne versionne que le code du bot colombina lui-même ; l'infra partagée (Alembic, schémas multi-bots, Postgres/Redis communs) reste privée.

## Environnement

Toute la configuration passe par des variables d'environnement dans `.env` (voir le tutoriel ci-dessus). Aucun secret ni aucune valeur réelle (IDs de serveur, tokens) n'est versionné : `.env` est ignoré par git et `.env.example` est un marqueur vide.
