# Colombina — Design : Tranche A (Fondations)

## Contexte du projet

**Colombina** est un nouveau bot Discord communautaire, indépendant des projets précédents du repo
(bot-haimiya-mio, bot-ville, bot-economie, bot-rpg — tous en SQLite). Stack demandée : Python 3.12+,
discord.py 2.x, PostgreSQL, SQLAlchemy, Redis, Docker, Pillow, Matplotlib/Plotly. Objectif final :
système communautaire complet (XP/niveaux, économie, badges, prestige, quêtes, profil, stats,
classements), scalable à 100 000+ utilisateurs.

Le projet est trop large pour un seul cycle spec→plan→implémentation. Il est découpé en tranches
indépendantes, dans l'ordre de dépendance :

| # | Tranche | Contenu |
|---|---------|---------|
| **A** | **Fondations** *(ce document)* | Structure projet, Docker, modèles SQLAlchemy, config, Redis, bot qui démarre |
| B | XP & Progression | Gain XP (messages/vocal/réactions/events/invites), niveaux, récompenses auto, badges, prestige I-IV |
| C | Économie & Boutique | `/balance /pay /daily /shop`, objets, quêtes quotidiennes |
| D | Profil, Stats & Classements | `/profile` (image Pillow), `/stats`, `/leaderboard` |
| E | Anti-abus | Détection spam/farm XP/vocal/multi-comptes |
| F | Commandes admin | `/setlevel /addxp /removexp /resetuser /addcoins /removecoins /givereward` |

Le dashboard web FastAPI (demandé dans le brief initial) est **retiré du périmètre** pour l'instant —
décision explicite de l'utilisateur, à reprendre plus tard si besoin.

Le bot est **single-guild** (un seul serveur cible, pas de `guild_id` dans les tables) — décision
explicite de l'utilisateur.

Le bot doit supporter des **commandes slash ET des commandes texte** (préfixe configurable). Les
commandes texte précises seront données par l'utilisateur plus tard ; cette tranche pose seulement
l'infrastructure (`commands.Bot` avec préfixe, pas un `discord.Client` pur) pour que les deux
cohabitent sans refonte.

## Portée de cette tranche

Poser le socle sur lequel toutes les tranches suivantes s'appuient : un bot qui démarre, se connecte
à Postgres et Redis, et expose un schéma de données complet mais sans aucune logique métier
(pas de gain d'XP, pas de commandes fonctionnelles — juste l'infrastructure et les modèles).

## Stack & choix techniques

- **discord.py 2.x**, `commands.Bot` (pas `discord.Client`) avec préfixe configurable via `.env`,
  pour permettre l'ajout ultérieur de commandes texte à côté des slash commands (`app_commands`).
- **SQLAlchemy 2.0 en mode async** (driver `asyncpg`). Discord.py tourne sur asyncio ; des requêtes
  DB bloquantes gèleraient le bot dès que la charge augmente — seul choix cohérent avec l'objectif
  de scalabilité à 100k utilisateurs.
- **Alembic** pour les migrations dès le départ (pas de `Base.metadata.create_all()` en prod).
- **Redis** (`redis.asyncio`) : connexion et health-check posés dans cette tranche ; l'usage réel
  (cooldowns XP, cache leaderboard) arrive en tranche B.
- **pydantic-settings** + `.env` pour la config (token, DB URL, Redis URL, préfixe, IDs de rôles/
  salons de récompense en placeholders). Cohérent avec le choix single-guild : pas besoin d'un
  système de config par serveur en DB.
- Pas de dossier `commands/` séparé des `cogs/` — avec discord.py les commandes vivent naturellement
  dans les cogs, un dossier vide en plus n'apporterait rien.

## Structure du projet

```
colombina/
├── main.py                  # point d'entrée : crée le bot, charge cogs, lance
├── config/
│   └── settings.py           # pydantic-settings : token, DB_URL, REDIS_URL, prefix, IDs rôles/salons
├── database/
│   ├── engine.py             # engine async SQLAlchemy + session factory
│   └── base.py                # Base declarative
├── models/                   # un fichier par table (users.py, levels.py, badges.py, ...)
├── services/                  # logique métier réutilisable par les cogs (vide pour l'instant)
├── cogs/                       # commandes slash + texte, un cog par domaine (vide pour l'instant)
├── utils/                      # helpers (logging, embeds communs)
├── assets/                     # fonts/images pour Pillow (rempli en tranche D)
├── alembic/                    # migrations
├── tests/
├── docker-compose.yml           # bot + postgres + redis
├── Dockerfile
├── .env.example
└── requirements.txt
```

## Schéma de base de données

Tables posées dans cette tranche (structure seule, aucune logique de lecture/écriture applicative) :

| Table | Rôle |
|---|---|
| `users` | Identité de base (discord_id PK, username en cache, dates de création/mise à jour) |
| `levels` | XP, niveau actuel, prestige actuel, compteurs cumulés messages/vocal |
| `prestiges` | Historique des passages de prestige (log, pour badges/stats futurs) |
| `badges` + `user_badges` | Définitions statiques des 14 badges (les 10 nommés + argent/or/platine/diamant utilisés par les paliers de récompense) + table de jonction utilisateur↔badge |
| `economy` | Solde de coins, date du dernier `/daily` |
| `voice_stats` | Agrégat journalier temps vocal par utilisateur (unique par user+date) |
| `message_stats` | Agrégat journalier nb messages par utilisateur (unique par user+date) |
| `quests` + `user_quests` | Définitions des quêtes quotidiennes + progression par utilisateur/jour |
| `rewards` | Config statique : quel niveau donne quel badge/rôle/coins (paliers 1→100 du brief) |
| `server_stats` | Snapshot journalier serveur (membres totaux, actifs, messages, vocal) |

`badges`, `quests` et `rewards` seront **seedées** via une migration Alembic de données (les 14
badges — les 10 nommés dans le brief + argent/or/platine/diamant — les paliers de récompense
niveau 1→100, quelques quêtes types) plutôt que codées en dur dans le code Python applicatif.

## Docker & infra

- `docker-compose.yml` : 3 services — `bot` (build local via Dockerfile), `postgres` (image
  officielle, volume persistant), `redis` (image officielle, volume si persistance AOF utile).
- `Dockerfile` : Python 3.12-slim, install des dépendances, `CMD python main.py`.
- Les migrations Alembic sont lancées automatiquement au démarrage du conteneur `bot` (script
  d'entrypoint) avant `main.py`, pour que `docker compose up` suffise à tout provisionner.
- `.env.example` avec toutes les variables nécessaires (`DISCORD_TOKEN`, `DATABASE_URL`,
  `REDIS_URL`, `COMMAND_PREFIX`, IDs de rôles de récompense en placeholders).

## Tests & logging

- `pytest` + `pytest-asyncio`. Le choix de la DB de test (Postgres éphémère vs. autre) sera tranché
  pendant l'implémentation, sans impact sur ce design.
- Logging via le module `logging` standard, configuré dans `utils/logging.py` — sortie console +
  fichier rotatif, niveau configurable via `.env`.

## Hors périmètre de cette tranche

- Toute logique de gain d'XP, économie, quêtes, anti-abus (tranches B-F).
- Dashboard FastAPI (retiré du périmètre global pour l'instant).
- Support multi-guild.
