from types import SimpleNamespace

from services.config_overview import build_config_sections

EMPTY_SETTINGS = SimpleNamespace(
    level_up_channel_id=None,
    alt_account_alert_channel_id=None,
    welcome_channel_id=None,
    admin_log_channel_id=None,
    suggestion_channel_id=None,
    suggestion_validation_channel_id=None,
    tour_category_id=None,
    mafia_channel_id=None,
    proces_channel_id=None,
    deepseek_api_key=None,
    daily_amount=100,
    work_amount=125,
    role_actif_id=None,
    role_bronze_id=None,
    role_habitue_id=None,
    role_argent_id=None,
    role_veteran_id=None,
    role_or_id=None,
    role_platine_id=None,
    role_diamant_id=None,
    role_mythique_id=None,
    role_legendaire_id=None,
    role_vip_argent_id=None,
    role_premium_id=None,
    prestige_1_role_id=None,
    prestige_2_role_id=None,
    prestige_3_role_id=None,
    prestige_4_role_id=None,
)


def test_build_config_sections_covers_every_configurable_setting():
    sections = build_config_sections(EMPTY_SETTINGS, {})

    all_labels = {entry.label for section in sections for entry in section.entries}
    assert "Niveau 5" in all_labels
    assert "Niveau 60" in all_labels
    assert "Niveau 100" in all_labels
    assert "Prestige 4 (niveau 500)" in all_labels
    assert "Roi du Chat" in all_labels
    assert "Catégorie des salons de la Tour RPG (tower-*)" in all_labels


def test_build_config_sections_level_60_sits_between_50_and_70_with_no_duplicate_key():
    sections = build_config_sections(EMPTY_SETTINGS, {})

    roles_section = next(s for s in sections if s.title == "Rôles de récompense par niveau")
    labels_in_order = [entry.label for entry in roles_section.entries]
    assert labels_in_order.index("Niveau 50") < labels_in_order.index("Niveau 60") < labels_in_order.index("Niveau 70")

    all_keys = [entry.key for section in sections for entry in section.entries]
    assert all_keys.count("role_vip_argent_id") == 1


def test_build_config_sections_reflects_configured_values():
    settings = SimpleNamespace(**{**vars(EMPTY_SETTINGS), "role_actif_id": "111", "level_up_channel_id": "222"})

    sections = build_config_sections(settings, {"roi_du_chat": 333})

    channels_section = next(s for s in sections if s.title == "Salons")
    assert channels_section.entries[0].value == "222"
    assert channels_section.entries[0].kind == "channel"

    roles_section = next(s for s in sections if s.title == "Rôles de récompense par niveau")
    assert roles_section.entries[0].value == "111"
    assert roles_section.entries[0].kind == "role"

    leaderboard_section = next(s for s in sections if s.title == "Classement hebdomadaire")
    assert leaderboard_section.entries[0].value == 333


def test_build_config_sections_defaults_missing_leaderboard_roles_to_none():
    sections = build_config_sections(EMPTY_SETTINGS, {})

    leaderboard_section = next(s for s in sections if s.title == "Classement hebdomadaire")
    assert all(entry.value is None for entry in leaderboard_section.entries)


def test_build_config_sections_exposes_daily_and_work_amounts_as_amount_kind():
    sections = build_config_sections(EMPTY_SETTINGS, {})

    economie_section = next(s for s in sections if s.title == "Économie")
    entries_by_key = {entry.key: entry for entry in economie_section.entries}

    assert entries_by_key["daily_amount"].value == 100
    assert entries_by_key["daily_amount"].kind == "amount"
    assert entries_by_key["work_amount"].value == 125
    assert entries_by_key["work_amount"].kind == "amount"
