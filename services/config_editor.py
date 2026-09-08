import re
from pathlib import Path

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

ID_PATTERN = re.compile(r"\d{15,25}")


class InvalidConfigValueError(Exception):
    pass


def parse_id_input(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    match = ID_PATTERN.search(raw)
    if match is None:
        raise InvalidConfigValueError(raw)
    return match.group(0)


def parse_secret_input(raw: str) -> str | None:
    raw = raw.strip()
    return raw or None


def parse_amount_input(raw: str) -> int:
    raw = raw.strip()
    if not raw.isdigit():
        raise InvalidConfigValueError(raw)
    return int(raw)


def set_settings_value(settings_obj, key: str, value: str | int | None, env_path: Path | None = None) -> None:
    setattr(settings_obj, key, value)
    _upsert_env_line(env_path or DEFAULT_ENV_PATH, key.upper(), value)


def set_leaderboard_role(path: Path, key: str, value: str | None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_line = f"{key}:{value or ''}"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == key or stripped.startswith(f"{key}:"):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _upsert_env_line(path: Path, env_key: str, value: str | int | None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_line = f"{env_key}={'' if value is None else value}"
    prefix = f"{env_key}="
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
