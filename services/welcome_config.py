import json
from pathlib import Path

import discord

DEFAULT_WELCOME_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "welcome_config.json"

DEFAULT_TITLE = "👋 Bienvenue !"
DEFAULT_TEXT = "Bienvenue {membre} sur le serveur !"
MEMBER_PLACEHOLDER = "{membre}"


def load_welcome_config(path: Path) -> dict:
    if not path.exists():
        return {"title": DEFAULT_TITLE, "text": DEFAULT_TEXT, "image_url": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "title": data.get("title") or DEFAULT_TITLE,
        "text": data.get("text") or DEFAULT_TEXT,
        "image_url": data.get("image_url") or None,
    }


def save_welcome_config(path: Path, title: str, text: str, image_url: str | None) -> None:
    path.write_text(
        json.dumps({"title": title, "text": text, "image_url": image_url}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_welcome_text(text: str, member: discord.Member | None) -> str:
    mention = member.mention if member is not None else MEMBER_PLACEHOLDER
    return text.replace(MEMBER_PLACEHOLDER, mention)


def build_welcome_embed(config: dict, member: discord.Member | None = None) -> discord.Embed:
    embed = discord.Embed(title=config["title"], description=render_welcome_text(config["text"], member))
    if config.get("image_url"):
        embed.set_image(url=config["image_url"])
    return embed
