"""Rendu visuel façon Undertale pour les scènes de combat de la Tour RPG.

Composition (640x480, fond noir) :
  - zone ennemie en haut (grille verte + nom de l'ennemi),
  - boîte de dialogue au centre (bordure blanche, texte),
  - ligne de stats "NOM  LV X  HP [barre] hp/max  OR or" en bas,
  - 4 boutons d'action orange (COMBAT / ACTE / OBJET / PITIÉ).

L'interaction reste 100% boutons Discord : cette image est un habillage
visuel envoyé en pièce jointe, elle ne remplace aucun bouton.
"""

import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

W, H = 640, 480
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (200, 20, 20)
DARKRED = (60, 10, 10)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 65)
ORANGE = (255, 102, 0)

_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "fonts", "DeterminationMonoWeb-Regular.ttf")

DEFAULT_BUTTONS = ["COMBAT", "ACTE", "OBJET", "PITIÉ"]


def _font(size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(_FONT_PATH):
        return ImageFont.truetype(_FONT_PATH, size)
    return ImageFont.load_default()


def _draw_grid(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, step: int = 24) -> None:
    x = x0
    while x <= x1:
        d.line([(x, y0), (x, y1)], fill=GREEN, width=1)
        x += step
    y = y0
    while y <= y1:
        d.line([(x0, y), (x1, y)], fill=GREEN, width=1)
        y += step


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if font.getlength(candidate) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def render_scene(
    *,
    player_name: str,
    level: int,
    hp: int,
    max_hp: int,
    gold: int,
    enemy_name: str,
    dialogue: str | None = None,
    buttons: list[str] | None = None,
) -> BytesIO:
    img = Image.new("RGB", (W, H), BLACK)
    d = ImageDraw.Draw(img)

    # --- Zone ennemie : grille verte + nom de l'ennemi ---
    _draw_grid(d, 0, 0, W - 1, 180)
    ef = _font(30)
    d.text((18, 16), (enemy_name or "").upper(), font=ef, fill=WHITE)

    # --- Boîte de dialogue ---
    d.rectangle((24, 196, W - 24, 304), outline=WHITE, width=4)
    df = _font(20)
    ty = 210
    for line in _wrap(dialogue or "", df, (W - 24) - 36 - 16)[:4]:
        d.text((36, ty), line, font=df, fill=WHITE)
        ty += 24

    # --- Ligne de stats ---
    sf = _font(24)
    x = 24.0
    y = 318
    name_txt = (player_name or "PLAYER").upper()[:12]
    d.text((x, y), name_txt, font=sf, fill=WHITE)
    x += d.textlength(name_txt + "  ", font=sf)
    lv_txt = f"LV {level}"
    d.text((x, y), lv_txt, font=sf, fill=WHITE)
    x += d.textlength(lv_txt + "   ", font=sf)
    d.text((x, y), "HP", font=sf, fill=WHITE)
    x += d.textlength("HP ", font=sf)
    bar_w, bar_h = 120, 22
    d.rectangle((x, y + 2, x + bar_w, y + 2 + bar_h), fill=DARKRED)
    fill_w = int(bar_w * max(0, hp) / max_hp) if max_hp else 0
    if fill_w > 0:
        d.rectangle((x, y + 2, x + fill_w, y + 2 + bar_h), fill=YELLOW)
    x += bar_w + 10
    hp_txt = f"{max(0, hp)}/{max_hp}"
    d.text((x, y), hp_txt, font=sf, fill=WHITE)
    x += d.textlength(hp_txt + "   ", font=sf)
    d.text((x, y), f"OR {gold}", font=sf, fill=YELLOW)

    # --- Boutons d'action ---
    labels = buttons or DEFAULT_BUTTONS
    n = len(labels)
    margin = 24
    gap = 10
    box_w = (W - 2 * margin - gap * (n - 1)) // n
    box_y0, box_y1 = 388, 456
    bf = _font(22)
    for i, label in enumerate(labels):
        bx0 = margin + i * (box_w + gap)
        bx1 = bx0 + box_w
        d.rectangle((bx0, box_y0, bx1, box_y1), outline=ORANGE, width=3)
        lw = d.textlength(label, font=bf)
        d.text((bx0 + (box_w - lw) / 2, box_y0 + (box_y1 - box_y0 - 26) / 2), label, font=bf, fill=ORANGE)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
