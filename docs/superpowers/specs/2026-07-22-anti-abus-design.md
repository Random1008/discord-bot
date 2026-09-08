# Colombina — Design : Tranche E (Anti-abus)

## Contexte

Tranches A à D sont terminées. Cette tranche couvre la détection spam/farm XP/vocal/multi-comptes annoncée dans
la vue d'ensemble du projet. Une partie existait déjà avant que cette tranche soit formellement cadrée (ajoutée
de façon ad hoc, sans spec) :

- `services/spam_guard.py::MessageSpamGuard` — coupe l'XP de message au-delà de 5 messages consécutifs envoyés
  à moins de 2s d'intervalle, branché dans `cogs/leveling.py::on_message`.
- `services/no_xp_channels.py` + `.unxp [id]` / `.xp [id]` (commandes admin texte) — exclusion de salons de
  l'XP vocal, branchée dans `cogs/voice.py`.
- Le farm vocal était déjà couvert depuis la tranche B (paiement XP conditionné à ≥2 humains présents dans le
  salon).

Ce document couvre ce qui manquait : la cohérence de l'exclusion de salons pour l'XP de message, et la
détection multi-comptes.

## Décisions structurantes (validées avec l'utilisateur avant implémentation)

- **Multi-comptes — signal retenu : âge du compte Discord.** L'API Discord ne donne accès à aucune IP ; le seul
  signal exploitable côté bot est `member.created_at` (dérivé du snowflake, toujours disponible). Un compte créé
  il y a moins de `ALT_ACCOUNT_THRESHOLD_DAYS` (7 jours, `services/alt_account_guard.py`) est traité comme un alt
  potentiel.
- **Effet sur un compte flaggé : réduction forte du gain d'XP (×0.2), pas un blocage total.** Choix explicite de
  l'utilisateur — moins punitif qu'un blocage complet pour un vrai nouveau membre légitime, tout en cassant
  l'intérêt de créer un alt pour farmer. `apply_alt_penalty` arrondit et garantit un minimum de 1 XP tant que le
  montant de base est positif (jamais un vrai zéro silencieux).
- **Alerte staff au moment du join**, pas à chaque gain d'XP — un seul message dans un salon dédié
  (`ALT_ACCOUNT_ALERT_CHANNEL_ID`, nouveau salon `.env`, vide par défaut comme tous les autres IDs de rôle/salon
  du projet) quand un compte récent rejoint. Évite le bruit d'une alerte répétée à chaque message/vocal du même
  compte.
- **Portée : XP uniquement, pas les coins.** Les coins gagnés via `/daily` et les récompenses de quêtes
  (`add_balance`) ne passent pas par le point d'entrée central `award_xp` et ne sont donc pas réduits par cette
  tranche. Limitation connue, pas un oubli — à étendre dans une tranche future si le farm de coins par alt
  s'avère un problème réel en pratique.
- **Le bonus XP d'inviteur (`LevelUpResult.inviter_bonus`, tranche B) n'est pas non plus soumis à la pénalité** :
  il est accordé via un appel interne à `services/leveling.py::add_xp`, pas via `cogs/xp_common.py::award_xp`
  (le point d'entrée où la pénalité est appliquée). Un inviteur dont le compte est lui-même récent n'est donc pas
  pénalisé sur son bonus d'invitation. Même limitation de portée que ci-dessus.
- **Salons exclus d'XP : cohérence message/vocal.** `no_xp_channels` s'appliquait déjà au vocal (tranche
  ad hoc) mais pas aux messages, incohérence corrigée dans `cogs/leveling.py::on_message` (même liste de salons
  exclus, même commandes admin `.unxp`/`.xp` qui pilotaient déjà le vocal).

## Implémentation

- `services/alt_account_guard.py` (pur, testable sans Discord) : `is_recent_account(created_at, now,
  threshold_days=7)`, `apply_alt_penalty(amount, flagged, multiplier=0.2)`.
- `cogs/xp_common.py::award_xp` — point d'entrée unique de toutes les sources d'XP (cf. tranche B) : calcule le
  flag à partir de `member.created_at` et applique la pénalité avant `add_xp`. Un seul point de câblage suffit à
  couvrir message, vocal, réaction, événement admin, récompense de quête.
- `cogs/anti_abuse.py` (nouveau cog) : listener `on_member_join`, envoie l'alerte si le compte est récent et
  qu'un salon d'alerte est configuré. Silencieux si aucun salon n'est configuré (mêmes conventions que
  `LEVEL_UP_CHANNEL_ID`).
- `cogs/leveling.py::on_message` : vérifie `is_no_xp_channel` avant d'accorder l'XP de message (la progression
  de quête et les stats de message restent trackées, seule l'XP est coupée — même comportement que le
  spam-guard déjà en place dans la même fonction).
- `config/settings.py` / `.env.example` : nouveau champ optionnel `alt_account_alert_channel_id`.

## Non couvert par cette tranche

- Réduction des coins (voir plus haut).
- Détection de multi-comptes au-delà de l'âge du compte (ex. corrélation de comportement, réutilisation de
  pseudo/avatar) — hors de portée de l'API Discord standard.
- Pas de commande admin de whitelist/override manuelle pour un faux positif (compte légitime mais récent) —
  l'effet actuel est une réduction, pas un blocage, ce qui limite l'impact d'un faux positif sans nécessiter
  d'override dans un premier temps.
