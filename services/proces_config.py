import json
from pathlib import Path

import discord

DEFAULT_PROCES_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "proces_config.json"

DEFAULT_TITLE = "⚖️ Tribunal — Déposer une plainte"
DEFAULT_TEXT = (
    "Tu veux traduire un membre en justice ? Clique sur le bouton ci-dessous, "
    "indique la raison, puis choisis le suspect dans la liste. Un procès sera ouvert "
    "avec un juge IA neutre qui animera les débats."
)

# Règlement du serveur appliqué par le juge IA. Valeur par défaut (modifiable par
# les admins via `.setup proces` → bouton « Configurer »). Stocké dans le JSON sous
# la clé « reglement » : le juge le reçoit à chaque prise de parole et au verdict.
DEFAULT_REGLEMENT = """RÈGLEMENT DU SERVEUR
1. Respect : respectez tous les membres ; les insultes, provocations, humiliations et conflits volontaires sont interdits ; les débats restent respectueux.
2. Harcèlement : le harcèlement, l'intimidation, les menaces et la traque sont interdits ; ne ciblez pas un membre de façon répétée pour le mettre mal à l'aise ou lui nuire.
3. Discrimination : tout propos ou comportement discriminatoire est interdit (racisme, homophobie, transphobie, sexisme, validisme, etc.) ; les « blagues » discriminatoires ne sont pas une exception.
4. Contenu interdit : tout contenu NSFW, pornographique ou sexuellement explicite est interdit ; les contenus gore, violents ou volontairement choquants sont aussi interdits ; cela concerne aussi les images, vidéos, liens, avatars et bannières.
5. Vie privée : ne divulguez pas les informations personnelles d'un membre sans son consentement ; le doxxing, les menaces de divulgation et la collecte d'informations privées sont interdits.
6. Salons : utilisez chaque salon selon son sujet et respectez ses consignes ; évitez le hors-sujet et le spam ; ces règles s'appliquent aussi aux salons vocaux.
7. Spam et mentions : le spam, le flood et l'utilisation abusive d'emojis, GIFs ou stickers sont interdits ; l'utilisation abusive de « @everyone » et « @here » est interdite ; les nuisances volontaires en vocal sont interdites.
8. Publicité : la publicité, l'auto-promotion et les invitations vers d'autres serveurs sont interdites sans autorisation ; le démarchage des membres en messages privés est interdit.
9. Pseudos et profils : les pseudos, avatars, bannières et statuts doivent respecter le règlement ; l'imitation d'un membre ou d'un modérateur dans le but de tromper est interdite.
10. Contournement : il est interdit de contourner une sanction avec un autre compte ou d'aider quelqu'un à le faire.
11. Modération et sanctions : respectez les décisions de la modération ; en cas de désaccord, contactez la modération en privé ; selon la gravité des faits, les sanctions peuvent aller de l'avertissement au bannissement définitif ; la modération peut adapter la sanction selon le contexte et les antécédents.
12. Règle générale : la modération peut intervenir face à tout comportement nuisible au serveur, même s'il n'est pas explicitement mentionné dans le règlement ; en rejoignant le serveur, vous acceptez ce règlement."""


def _read_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_proces_config(path: Path) -> dict:
    data = _read_raw(path)
    return {
        "title": data.get("title") or DEFAULT_TITLE,
        "text": data.get("text") or DEFAULT_TEXT,
        "reglement": data.get("reglement") or DEFAULT_REGLEMENT,
    }


def save_proces_config(path: Path, title: str, text: str, reglement: str | None = None) -> None:
    """Sauvegarde titre/texte (+ règlement si fourni, sinon conserve la valeur existante)."""
    data = _read_raw(path)
    data["title"] = title
    data["text"] = text
    if reglement is not None:
        data["reglement"] = reglement
    _write_raw(path, data)


def get_proces_reglement(path: Path = DEFAULT_PROCES_CONFIG_PATH) -> str:
    """Règlement à injecter au juge IA (configuré ou valeur par défaut)."""
    return load_proces_config(path)["reglement"]


# --- Persistance des panneaux postés (boutons immortels via custom_id) ---
# `panel_messages` contient les message_id des panneaux « Déposer une plainte »
# postés dans le salon des procès. Au démarrage, ProcesCog ré-attache une vue
# persistante sur chacun (bot.add_view) pour que le bouton survive au redémarrage.


def panel_message_ids(path: Path = DEFAULT_PROCES_CONFIG_PATH) -> list[int]:
    ids = []
    for raw in _read_raw(path).get("panel_messages", []):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def add_panel_message(path: Path, message_id: int) -> None:
    data = _read_raw(path)
    data.setdefault("title", DEFAULT_TITLE)
    data.setdefault("text", DEFAULT_TEXT)
    messages = [m for m in data.get("panel_messages", []) if isinstance(m, int)]
    if message_id not in messages:
        messages.append(message_id)
    data["panel_messages"] = messages
    _write_raw(path, data)


def build_proces_embed(config: dict) -> discord.Embed:
    return discord.Embed(
        title=config["title"],
        description=config["text"],
        color=0x5865F2,
    )
