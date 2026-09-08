# Colombina — Bot Discord

Bot Discord unifié du serveur de Lia : économie, progression (XP/levels), RPG, casino, modération et assistants IA. Développé en Python avec `discord.py` 2.x, SQLAlchemy 2 (async) et PostgreSQL.

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

Les préfixes sont dispatchés par module : `$` pour l'argent, `.` pour l'admin, `!` pour le reste, `+log` pour le journal.

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
tests/      suite pytest (unitaires + intégration postgres)
scripts/    tâches auxiliaires (ex. file de suggestions)
docs/       plans et specs de conception
```

## Démarrage rapide

Prérequis : Python 3.12, une base PostgreSQL et un Redis accessibles.

```bash
cp .env.example .env      # puis renseigner token, DATABASE_URL, REDIS_URL…
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Au démarrage, le bot exécute les migrations Alembic (voir infra partagée ci-dessous), puis se connecte à Discord.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Conteneurisation

Le dossier contient un `Dockerfile` et un `docker-compose.yml`. En production, colombina est construit depuis le workspace de l'écosystème Discord, dont le contexte parent fournit le dossier partagé `shared/` (migrations Alembic communes à tous les bots — colombina, zero-two, makima, giani, yoru). L'`entrypoint.sh` lance `alembic upgrade head` dans ce dossier partagé avant de démarrer `main.py`.

Ce dépôt ne versionne que le code du bot colombina lui-même ; l'infra partagée (Alembic, schémas multi-bots, Postgres/Redis communs) reste privée.

## Environnement

La configuration se fait exclusivement par variables d'environnement via `.env` (voir `.env.example`) : token Discord, URLs de base de données et Redis, IDs de salons/rôles (récompenses de niveaux, classements, prestige, tour…). Aucun secret n'est versionné.
