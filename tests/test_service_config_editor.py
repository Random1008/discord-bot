from types import SimpleNamespace

import pytest

from services.config_editor import (
    InvalidConfigValueError,
    parse_amount_input,
    parse_id_input,
    parse_secret_input,
    set_leaderboard_role,
    set_settings_value,
)


def test_parse_id_input_returns_none_for_blank_input():
    assert parse_id_input("   ") is None


def test_parse_id_input_extracts_digits_from_a_role_mention():
    assert parse_id_input("<@&123456789012345678>") == "123456789012345678"


def test_parse_id_input_extracts_digits_from_a_channel_mention():
    assert parse_id_input("<#123456789012345678>") == "123456789012345678"


def test_parse_id_input_accepts_a_bare_id():
    assert parse_id_input("123456789012345678") == "123456789012345678"


def test_parse_id_input_rejects_text_without_a_long_enough_id():
    with pytest.raises(InvalidConfigValueError):
        parse_id_input("not-an-id")


def test_parse_amount_input_accepts_a_positive_integer():
    assert parse_amount_input("150") == 150


def test_parse_amount_input_accepts_zero():
    assert parse_amount_input("0") == 0


def test_parse_amount_input_rejects_blank_input():
    with pytest.raises(InvalidConfigValueError):
        parse_amount_input("   ")


def test_parse_amount_input_rejects_a_negative_number():
    with pytest.raises(InvalidConfigValueError):
        parse_amount_input("-5")


def test_parse_amount_input_rejects_non_numeric_text():
    with pytest.raises(InvalidConfigValueError):
        parse_amount_input("abc")


def test_parse_secret_input_returns_none_for_blank_input():
    assert parse_secret_input("   ") is None


def test_parse_secret_input_returns_the_raw_stripped_value():
    assert parse_secret_input("  sk-abc123  ") == "sk-abc123"


def test_set_settings_value_persists_an_integer_amount_without_dropping_a_zero(tmp_path):
    settings = SimpleNamespace(work_amount=125)
    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\n", encoding="utf-8")

    set_settings_value(settings, "work_amount", 0, env_path=env_path)

    assert settings.work_amount == 0
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "WORK_AMOUNT=0" in lines


def test_set_settings_value_updates_the_object_and_upserts_the_env_file(tmp_path):
    settings = SimpleNamespace(role_actif_id=None)
    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_TOKEN=x\nLOG_LEVEL=INFO\n", encoding="utf-8")

    set_settings_value(settings, "role_actif_id", "123456789012345678", env_path=env_path)

    assert settings.role_actif_id == "123456789012345678"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "ROLE_ACTIF_ID=123456789012345678" in lines
    assert "DISCORD_TOKEN=x" in lines


def test_set_settings_value_overwrites_an_existing_env_line_in_place(tmp_path):
    settings = SimpleNamespace(role_actif_id="111")
    env_path = tmp_path / ".env"
    env_path.write_text("ROLE_ACTIF_ID=111\nLOG_LEVEL=INFO\n", encoding="utf-8")

    set_settings_value(settings, "role_actif_id", "222", env_path=env_path)

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["ROLE_ACTIF_ID=222", "LOG_LEVEL=INFO"]


def test_set_settings_value_clears_to_empty_when_value_is_none(tmp_path):
    settings = SimpleNamespace(role_actif_id="111")
    env_path = tmp_path / ".env"
    env_path.write_text("ROLE_ACTIF_ID=111\n", encoding="utf-8")

    set_settings_value(settings, "role_actif_id", None, env_path=env_path)

    assert settings.role_actif_id is None
    assert "ROLE_ACTIF_ID=" in env_path.read_text(encoding="utf-8")


def test_set_leaderboard_role_updates_the_matching_line(tmp_path):
    path = tmp_path / "leaderboard_roles.txt"
    path.write_text("roi_du_chat:\nmaitre_vocal:\ntop_10:\n", encoding="utf-8")

    set_leaderboard_role(path, "maitre_vocal", "42")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert "maitre_vocal:42" in lines
    assert "roi_du_chat:" in lines


def test_set_leaderboard_role_clears_when_value_is_none(tmp_path):
    path = tmp_path / "leaderboard_roles.txt"
    path.write_text("roi_du_chat:42\n", encoding="utf-8")

    set_leaderboard_role(path, "roi_du_chat", None)

    assert "roi_du_chat:" in path.read_text(encoding="utf-8")
    assert "roi_du_chat:42" not in path.read_text(encoding="utf-8")
