import io
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont, ImageOps

CARD_WIDTH = 900
CARD_HEIGHT = 460

BACKGROUND_COLOR = (110, 15, 20)
FRAME_OUTER_COLOR = (54, 32, 18)
FRAME_TRIM_COLOR = (150, 100, 50)
TEXT_COLOR = (240, 232, 220)
BAR_BACKGROUND_COLOR = (54, 32, 18)
BAR_FILL_COLOR = (150, 100, 50)
AVATAR_PLACEHOLDER_COLOR = (190, 190, 190)
AVATAR_DIAMETER = 220

_FRAME_MARGIN = 16
_FRAME_WIDTH = 14
_TRIM_MARGIN = _FRAME_MARGIN + _FRAME_WIDTH + 8
_TRIM_WIDTH = 3
_CORNER_RADIUS = 24
_CORNER_ORNAMENT_RADIUS = 26

_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "rpg", "assets", "fonts", "DeterminationMonoWeb-Regular.ttf"
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(_FONT_PATH):
        return ImageFont.truetype(_FONT_PATH, size)
    return ImageFont.load_default()


@dataclass
class ProfileCardData:
    username: str
    level: int
    current_level_xp: int
    xp_needed_for_next_level: int
    rank: int
    key_count: int


def _draw_frame(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(
        [_FRAME_MARGIN, _FRAME_MARGIN, CARD_WIDTH - _FRAME_MARGIN, CARD_HEIGHT - _FRAME_MARGIN],
        radius=_CORNER_RADIUS,
        outline=FRAME_OUTER_COLOR,
        width=_FRAME_WIDTH,
    )
    draw.rounded_rectangle(
        [_TRIM_MARGIN, _TRIM_MARGIN, CARD_WIDTH - _TRIM_MARGIN, CARD_HEIGHT - _TRIM_MARGIN],
        radius=_CORNER_RADIUS - 8,
        outline=FRAME_TRIM_COLOR,
        width=_TRIM_WIDTH,
    )
    corners = [
        (_FRAME_MARGIN, _FRAME_MARGIN),
        (CARD_WIDTH - _FRAME_MARGIN, _FRAME_MARGIN),
        (_FRAME_MARGIN, CARD_HEIGHT - _FRAME_MARGIN),
        (CARD_WIDTH - _FRAME_MARGIN, CARD_HEIGHT - _FRAME_MARGIN),
    ]
    for cx, cy in corners:
        draw.ellipse(
            [cx - _CORNER_ORNAMENT_RADIUS, cy - _CORNER_ORNAMENT_RADIUS, cx + _CORNER_ORNAMENT_RADIUS, cy + _CORNER_ORNAMENT_RADIUS],
            fill=FRAME_OUTER_COLOR,
            outline=FRAME_TRIM_COLOR,
            width=_TRIM_WIDTH,
        )


def _paste_circular_avatar(card: Image.Image, avatar_bytes: bytes, center: tuple[int, int]) -> None:
    cx, cy = center
    radius = AVATAR_DIAMETER // 2
    border_width = 8

    draw = ImageDraw.Draw(card)
    draw.ellipse(
        [cx - radius - border_width, cy - radius - border_width, cx + radius + border_width, cy + radius + border_width],
        fill=FRAME_OUTER_COLOR,
        outline=FRAME_TRIM_COLOR,
        width=_TRIM_WIDTH,
    )

    try:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        avatar = ImageOps.fit(avatar, (AVATAR_DIAMETER, AVATAR_DIAMETER))
    except Exception:
        avatar = Image.new("RGB", (AVATAR_DIAMETER, AVATAR_DIAMETER), AVATAR_PLACEHOLDER_COLOR)

    mask = Image.new("L", (AVATAR_DIAMETER, AVATAR_DIAMETER), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, AVATAR_DIAMETER, AVATAR_DIAMETER], fill=255)
    card.paste(avatar, (cx - radius, cy - radius), mask)


def _draw_xp_bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, height: int, fill_ratio: float) -> None:
    draw.rounded_rectangle([x, y, x + width, y + height], radius=height // 2, fill=BAR_BACKGROUND_COLOR)
    filled_width = max(height, int(width * fill_ratio)) if fill_ratio > 0 else 0
    if filled_width > 0:
        draw.rounded_rectangle([x, y, x + filled_width, y + height], radius=height // 2, fill=BAR_FILL_COLOR)


def render_profile_card(data: ProfileCardData, avatar_bytes: bytes) -> bytes:
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(card)

    _draw_frame(draw)

    avatar_center = (_TRIM_MARGIN + 30 + AVATAR_DIAMETER // 2, CARD_HEIGHT // 2)
    _paste_circular_avatar(card, avatar_bytes, avatar_center)

    text_x = avatar_center[0] + AVATAR_DIAMETER // 2 + 50
    text_width = CARD_WIDTH - _TRIM_MARGIN - 30 - text_x

    name_font = _font(40)
    draw.text((text_x, 60), data.username, fill=TEXT_COLOR, font=name_font)

    bar_y = 130
    bar_height = 40
    fill_ratio = 1.0
    if data.xp_needed_for_next_level > 0:
        fill_ratio = min(1.0, data.current_level_xp / data.xp_needed_for_next_level)
    _draw_xp_bar(draw, text_x, bar_y, text_width, bar_height, fill_ratio)

    info_font = _font(26)
    line_y = bar_y + bar_height + 30
    line_spacing = 40
    draw.text((text_x, line_y), f"Niveau : {data.level}", fill=TEXT_COLOR, font=info_font)
    draw.text((text_x, line_y + line_spacing), f"Classement : N°{data.rank}", fill=TEXT_COLOR, font=info_font)
    draw.text((text_x, line_y + 2 * line_spacing), f"Key : {data.key_count}", fill=TEXT_COLOR, font=info_font)

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    return buffer.getvalue()
