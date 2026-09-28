"""Applique le verrou du salon VIP à l'étage casino (permissions Discord).

Équivalent hors-bot de la commande admin `.vipguard on` : utile quand le bot
n'est pas lancé, ou pour reposer les surcharges après une recréation du salon.

    python scripts/apply_vip_channel_lock.py [on|off] [--dry-run]

Le token est lu depuis colombina/.env (aucun secret dans ce fichier).
Contrairement aux permissions Discord (que les admins contournent), ce script
ne bloque pas les administrateurs : ce verrou-là est assuré par le bot
(cogs/vip.py), qui supprime leurs messages et refuse leurs commandes.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"

VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
MANAGE_MESSAGES = 1 << 13
EMBED_LINKS = 1 << 14
ATTACH_FILES = 1 << 15
READ_MESSAGE_HISTORY = 1 << 16
ADD_REACTIONS = 1 << 6
USE_EXTERNAL_EMOJIS = 1 << 18
CREATE_PUBLIC_THREADS = 1 << 34
CREATE_PRIVATE_THREADS = 1 << 36
SEND_MESSAGES_IN_THREADS = 1 << 38

EVERYONE_ALLOW = VIEW_CHANNEL
EVERYONE_DENY = (
    SEND_MESSAGES
    | ADD_REACTIONS
    | CREATE_PUBLIC_THREADS
    | CREATE_PRIVATE_THREADS
    | SEND_MESSAGES_IN_THREADS
)
ROLE_ALLOW = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | ADD_REACTIONS
    | READ_MESSAGE_HISTORY
    | CREATE_PUBLIC_THREADS
    | EMBED_LINKS
    | ATTACH_FILES
    | USE_EXTERNAL_EMOJIS
)
BOT_ALLOW = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | READ_MESSAGE_HISTORY
    | MANAGE_MESSAGES
    | EMBED_LINKS
    | ATTACH_FILES
    | ADD_REACTIONS
)


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "colombina-vip-lock/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode() or "{}"
        return json.loads(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verrou du salon VIP du casino")
    parser.add_argument("action", nargs="?", default="on", choices=["on", "off"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--env",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    )
    args = parser.parse_args()

    env = load_env(args.env)
    token = env.get("DISCORD_TOKEN") or env.get("TOKEN")
    channel_id = env.get("VIP_CASINO_CHANNEL_ID")
    role_id = env.get("VIP_CASINO_ROLE_ID")

    missing = [
        name
        for name, value in (
            ("DISCORD_TOKEN", token),
            ("VIP_CASINO_CHANNEL_ID", channel_id),
            ("VIP_CASINO_ROLE_ID", role_id),
        )
        if not value
    ]
    if missing:
        print(f"❌ Valeurs manquantes dans {args.env} : {', '.join(missing)}")
        return 1

    me = api("GET", "/users/@me", token)
    print(f"🤖 Bot : {me['username']}#{me.get('discriminator', '0')} ({me['id']})")

    # Le rôle @everyone porte l'id du serveur : on le lit depuis le salon, ce
    # qui évite de dépendre d'un GUILD_ID dans le .env.
    channel = api("GET", f"/channels/{channel_id}", token)
    guild_id = str(channel["guild_id"])
    print(f"📍 Salon {channel.get('name')} ({channel_id}) — serveur {guild_id}")

    if args.action == "off":
        cibles = [(guild_id, 0, {}), (role_id, 0, {}), (me["id"], 1, {})]
    else:
        cibles = [
            (guild_id, 0, {"allow": str(EVERYONE_ALLOW), "deny": str(EVERYONE_DENY)}),
            (role_id, 0, {"allow": str(ROLE_ALLOW), "deny": "0"}),
            (me["id"], 1, {"allow": str(BOT_ALLOW), "deny": "0"}),
        ]

    for target_id, target_type, payload in cibles:
        if args.dry_run:
            print(f"(dry-run) PUT /channels/{channel_id}/permissions/{target_id} type={target_type} {payload}")
            continue
        try:
            api(
                "PUT",
                f"/channels/{channel_id}/permissions/{target_id}",
                token,
                {"type": target_type, **payload},
            )
        except urllib.error.HTTPError as exc:
            print(f"❌ Échec sur {target_id} : {exc.code} {exc.read().decode()[:200]}")
            return 1
        print(f"✅ Surcharge appliquée : {target_id} (type {target_type})")

    if args.dry_run:
        return 0
    if args.action == "on":
        print(
            "🔒 Salon VIP verrouillé : seul le rôle VIP (et le bot) peut y écrire. "
            "Les admins contournent les permissions Discord — le bot supprime leurs messages."
        )
    else:
        print("🔓 Surcharges retirées : le salon VIP est revenu aux permissions par défaut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
