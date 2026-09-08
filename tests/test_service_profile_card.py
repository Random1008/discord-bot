import io

from PIL import Image

from services.profile_card import CARD_HEIGHT, CARD_WIDTH, ProfileCardData, render_profile_card


def _fake_avatar_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), (200, 100, 50))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_render_profile_card_produces_correctly_sized_png():
    data = ProfileCardData(
        username="Ashen",
        level=5,
        current_level_xp=150,
        xp_needed_for_next_level=400,
        rank=3,
        key_count=7,
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.format == "PNG"
    assert image.size == (CARD_WIDTH, CARD_HEIGHT)


def test_render_profile_card_handles_no_keys_or_rank_one():
    data = ProfileCardData(
        username="Newcomer", level=0, current_level_xp=0, xp_needed_for_next_level=100, rank=1, key_count=0
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.size == (CARD_WIDTH, CARD_HEIGHT)


def test_render_profile_card_handles_max_level_zero_xp_needed():
    data = ProfileCardData(
        username="MaxLevel", level=999, current_level_xp=0, xp_needed_for_next_level=0, rank=1, key_count=42
    )

    result = render_profile_card(data, _fake_avatar_bytes())

    image = Image.open(io.BytesIO(result))
    assert image.size == (CARD_WIDTH, CARD_HEIGHT)


def test_render_profile_card_handles_unreadable_avatar_bytes():
    data = ProfileCardData(
        username="Broken", level=1, current_level_xp=10, xp_needed_for_next_level=100, rank=5, key_count=1
    )

    result = render_profile_card(data, b"not-an-image")

    image = Image.open(io.BytesIO(result))
    assert image.size == (CARD_WIDTH, CARD_HEIGHT)
