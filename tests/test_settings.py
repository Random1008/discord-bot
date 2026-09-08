from config.settings import Settings


def test_settings_loads_required_fields_from_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc123")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/colombina")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    settings = Settings(_env_file=None)

    assert settings.discord_token == "abc123"
    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/colombina"
    assert settings.redis_url == "redis://localhost:6379/0"


def test_settings_defaults():
    settings = Settings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.sql_echo is False


def test_progression_role_and_channel_settings_default_to_none():
    settings = Settings(_env_file=None)

    assert settings.level_up_channel_id is None
    assert settings.role_actif_id is None
    assert settings.role_habitue_id is None
    assert settings.role_veteran_id is None
    assert settings.role_legendaire_id is None
    assert settings.role_bronze_id is None
    assert settings.role_argent_id is None
    assert settings.role_or_id is None
    assert settings.role_platine_id is None
    assert settings.role_diamant_id is None
    assert settings.role_mythique_id is None
    assert settings.role_vip_argent_id is None
    assert settings.role_premium_id is None
    assert settings.prestige_1_role_id is None
    assert settings.prestige_2_role_id is None
    assert settings.prestige_3_role_id is None
    assert settings.prestige_4_role_id is None
    assert settings.alt_account_alert_channel_id is None
    assert settings.welcome_channel_id is None
    assert settings.admin_log_channel_id is None


def test_progression_role_setting_reads_from_env(monkeypatch):
    monkeypatch.setenv("LEVEL_UP_CHANNEL_ID", "123456789")
    monkeypatch.setenv("PRESTIGE_1_ROLE_ID", "987654321")

    settings = Settings(_env_file=None)

    assert settings.level_up_channel_id == "123456789"
    assert settings.prestige_1_role_id == "987654321"
