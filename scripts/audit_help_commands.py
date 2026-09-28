"""Audit : toutes les commandes déclarées apparaissent-elles dans !help ou .adminhelp ?

Compare les commandes trouvées dans les sources (cogs/*.py) avec les entrées
déclarées dans cogs/help.py (PLAYER_CATEGORIES = !help, ADMIN_CATEGORIES = .adminhelp).
"""
import os
import re
import sys

os.environ.setdefault("DISCORD_TOKEN", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

ROOT = "/home/random/Document/discord-bot/colombina"
sys.path.insert(0, "/home/random/Document/discord-bot")
sys.path.insert(0, ROOT)

CMD_RE = re.compile(r'^\s*@commands\.command\(\s*name="([^"]+)"')
GROUP_RE = re.compile(r'^\s*@commands\.group\(\s*name="([^"]+)"')
MEMBER_RE = re.compile(r'^\s*@(\w+)\.command\(\s*name="([^"]+)"')

declared: dict[str, set[str]] = {}
for fname in sorted(os.listdir(os.path.join(ROOT, "cogs"))):
    if not fname.endswith(".py") or fname.startswith("_"):
        continue
    path = os.path.join(ROOT, "cogs", fname)
    lines = open(path, encoding="utf-8").read().splitlines()
    # 1er passage : noms de groupes du fichier (pour préfixer les sous-commandes)
    group_names = set()
    for line in lines:
        m = GROUP_RE.match(line)
        if m:
            group_names.add(m.group(1))
    found: set[str] = set()
    for line in lines:
        m = CMD_RE.match(line)
        if m:
            found.add(m.group(1))
            continue
        m = GROUP_RE.match(line)
        if m:
            found.add(m.group(1))
            continue
        m = MEMBER_RE.match(line)
        if m and m.group(1) in group_names:
            found.add(f"{m.group(1)} {m.group(2)}")
    if found:
        declared[fname] = found

from cogs import help as help_module  # noqa: E402

usages = []
for category in list(help_module.PLAYER_CATEGORIES) + list(help_module.ADMIN_CATEGORIES):
    usages.extend(usage for usage, _desc in category["entries"])
help_text = "\n".join(usages)


def is_documented(cmd: str) -> bool:
    parts = cmd.split()
    pattern = r"[.!$+]" + r"\s+".join(re.escape(p) for p in parts) + r"(?![a-zA-Z0-9_-])"
    return bool(re.search(pattern, help_text))


missing = [(f, c) for f, cmds in declared.items() for c in sorted(cmds) if not is_documented(c)]
total = sum(len(c) for c in declared.values())

print("=== commandes déclarées par cog ===")
for f, cmds in sorted(declared.items()):
    print(f"{f:26} {len(cmds):3} : {', '.join(sorted(cmds))}")
print(f"\ntotal déclarées : {total} | usages documentés : {len(usages)}")
print()
if missing:
    print(f"!!! {len(missing)} commande(s) absente(s) de !help/.adminhelp :")
    for f, c in missing:
        print(f"   - {c:24} ({f})")
else:
    print("OK : toutes les commandes déclarées sont documentées.")
