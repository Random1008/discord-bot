from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str
    database_url: str
    redis_url: str
    guild_id: int = 1353659915113336832
    sql_echo: bool = False
    log_level: str = "INFO"

    level_up_channel_id: str | None = None
    alt_account_alert_channel_id: str | None = None
    welcome_channel_id: str | None = None
    admin_log_channel_id: str | None = None
    role_actif_id: str | None = None
    role_habitue_id: str | None = None
    role_veteran_id: str | None = None
    role_legendaire_id: str | None = None
    role_bronze_id: str | None = None
    role_argent_id: str | None = None
    role_or_id: str | None = None
    role_platine_id: str | None = None
    role_diamant_id: str | None = None
    role_mythique_id: str | None = None
    role_vip_argent_id: str | None = None
    role_premium_id: str | None = None
    prestige_1_role_id: str | None = None
    prestige_2_role_id: str | None = None
    prestige_3_role_id: str | None = None
    prestige_4_role_id: str | None = None

    leaderboard_roi_du_chat_id: str | None = None
    leaderboard_maitre_vocal_id: str | None = None
    leaderboard_riche_id: str | None = None
    leaderboard_top_10_vocal_id: str | None = None
    leaderboard_top_10_message_id: str | None = None
    leaderboard_top_10_argent_id: str | None = None

    daily_amount: int = 100
    work_amount: int = 125

    suggestion_channel_id: str | None = None
    suggestion_validation_channel_id: str | None = None
    tour_category_id: str | None = None
    mafia_channel_id: str | None = None
    proces_channel_id: str | None = None
    deepseek_api_key: str | None = None


settings = Settings()

# Sur ce serveur, yoru tourne avec ses propres versions (ville) de la Tour RPG,
# du casino et du gacha — colombina désactive les siennes ici (cf. main.py et
# cogs/help.py) pour laisser yoru y répondre seul.
YORU_DUPLICATE_RESTRICTED_GUILD_ID = 1353659915113336832

# Commandes admin (ADMIN_COMMAND_NAMES, cf. main.py) : il faut à la fois ce
# rôle ET une entrée dans admin_permissions (accordée via .permadd) pour les
# exécuter. .permadd lui-même n'est utilisable que par ADMIN_PERMISSION_OWNER_ID
# (bootstrap de la whitelist, cf. cogs/admin.py).
ADMIN_PERMISSION_ROLE_ID = 1536371678962126868
ADMIN_PERMISSION_OWNER_ID = 1173059024661532703
