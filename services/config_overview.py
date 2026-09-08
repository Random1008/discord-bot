from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigEntry:
    label: str
    value: str | int | None
    key: str
    kind: str = "role"
    source: str = "settings"


@dataclass(frozen=True)
class ConfigSection:
    title: str
    entries: list[ConfigEntry]


def build_config_sections(settings, leaderboard_roles: dict[str, int | None]) -> list[ConfigSection]:
    return [
        ConfigSection(
            title="Salons",
            entries=[
                ConfigEntry(
                    "Annonces de niveau & récompenses",
                    settings.level_up_channel_id,
                    key="level_up_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Alertes anti-abus",
                    settings.alt_account_alert_channel_id,
                    key="alt_account_alert_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon de bienvenue",
                    settings.welcome_channel_id,
                    key="welcome_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon de logs admin & modération",
                    settings.admin_log_channel_id,
                    key="admin_log_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon des suggestions (!suggest)",
                    settings.suggestion_channel_id,
                    key="suggestion_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon de validation des suggestions",
                    settings.suggestion_validation_channel_id,
                    key="suggestion_validation_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Catégorie des salons de la Tour RPG (tower-*)",
                    settings.tour_category_id,
                    key="tour_category_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon du marché de la mafia ($mafia)",
                    settings.mafia_channel_id,
                    key="mafia_channel_id",
                    kind="channel",
                ),
                ConfigEntry(
                    "Salon des procès ($proces / .setup proces)",
                    settings.proces_channel_id,
                    key="proces_channel_id",
                    kind="channel",
                ),
            ],
        ),
        ConfigSection(
            title="Intégrations IA",
            entries=[
                ConfigEntry(
                    "Clé API DeepSeek (entretien de suggestions)",
                    settings.deepseek_api_key,
                    key="deepseek_api_key",
                    kind="secret",
                ),
            ],
        ),
        ConfigSection(
            title="Économie",
            entries=[
                ConfigEntry("Montant $daily", settings.daily_amount, key="daily_amount", kind="amount"),
                ConfigEntry("Montant $work", settings.work_amount, key="work_amount", kind="amount"),
            ],
        ),
        ConfigSection(
            title="Rôles de récompense par niveau",
            entries=[
                ConfigEntry("Niveau 5", settings.role_actif_id, key="role_actif_id"),
                ConfigEntry("Niveau 10", settings.role_bronze_id, key="role_bronze_id"),
                ConfigEntry("Niveau 20", settings.role_habitue_id, key="role_habitue_id"),
                ConfigEntry("Niveau 30", settings.role_argent_id, key="role_argent_id"),
                ConfigEntry("Niveau 40", settings.role_veteran_id, key="role_veteran_id"),
                ConfigEntry("Niveau 50", settings.role_or_id, key="role_or_id"),
                ConfigEntry("Niveau 60", settings.role_vip_argent_id, key="role_vip_argent_id"),
                ConfigEntry("Niveau 70", settings.role_platine_id, key="role_platine_id"),
                ConfigEntry("Niveau 80", settings.role_diamant_id, key="role_diamant_id"),
                ConfigEntry("Niveau 90", settings.role_mythique_id, key="role_mythique_id"),
                ConfigEntry("Niveau 100", settings.role_legendaire_id, key="role_legendaire_id"),
            ],
        ),
        ConfigSection(
            title="Accès VIP / Premium",
            entries=[
                ConfigEntry("Premium (niveau 100)", settings.role_premium_id, key="role_premium_id"),
            ],
        ),
        ConfigSection(
            title="Rôles de prestige",
            entries=[
                ConfigEntry("Prestige 1 (niveau 100)", settings.prestige_1_role_id, key="prestige_1_role_id"),
                ConfigEntry("Prestige 2 (niveau 200)", settings.prestige_2_role_id, key="prestige_2_role_id"),
                ConfigEntry("Prestige 3 (niveau 300)", settings.prestige_3_role_id, key="prestige_3_role_id"),
                ConfigEntry("Prestige 4 (niveau 500)", settings.prestige_4_role_id, key="prestige_4_role_id"),
            ],
        ),
        ConfigSection(
            title="Classement hebdomadaire",
            entries=[
                ConfigEntry(
                    "Roi du Chat",
                    leaderboard_roles.get("roi_du_chat"),
                    key="roi_du_chat",
                    source="leaderboard",
                ),
                ConfigEntry(
                    "Maître Vocal",
                    leaderboard_roles.get("maitre_vocal"),
                    key="maitre_vocal",
                    source="leaderboard",
                ),
                ConfigEntry(
                    "Riche (n°1 en argent)",
                    leaderboard_roles.get("riche"),
                    key="riche",
                    source="leaderboard",
                ),
                ConfigEntry(
                    "Top 10 Vocal",
                    leaderboard_roles.get("top_10_vocal"),
                    key="top_10_vocal",
                    source="leaderboard",
                ),
                ConfigEntry(
                    "Top 10 Message",
                    leaderboard_roles.get("top_10_message"),
                    key="top_10_message",
                    source="leaderboard",
                ),
                ConfigEntry(
                    "Top 10 Argent",
                    leaderboard_roles.get("top_10_argent"),
                    key="top_10_argent",
                    source="leaderboard",
                ),
            ],
        ),
    ]
