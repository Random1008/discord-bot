# Colombina — Design : Tranche F (Commandes admin)

## Contexte

Tranches A à E sont terminées. Cette tranche implémente les 7 commandes admin annoncées dans la vue
d'ensemble du projet : `/setlevel /addxp /removexp /resetuser /addcoins /removecoins /givereward`.
C'est la dernière tranche de fonctionnalités prévue avant la tranche G (dashboard, hors périmètre).

## Décisions structurantes (validées avec l'utilisateur avant implémentation)

- **`/resetuser` — portée du wipe : tout, y compris badges et clés.** XP, niveau, prestige, solde de coins,
  badges et clés de coffre sont tous remis à zéro/supprimés. Les quêtes du jour et les stats de messages/vocal
  (`MessageStat`/`VoiceStat`) ne sont **pas** touchées — elles sont déjà scopées par date et se réinitialisent
  naturellement, elles ne font pas partie de la "progression" d'un compte au même titre.
- **`/givereward` — accepte badge OU niveau, exactement un des deux.** `badge:[clé]` réutilise
  `services/rewards.py::grant_badge_by_key` (idempotent). `niveau:[N]` rejoue **toutes** les récompenses
  définies pour ce niveau dans la table `rewards` (mêmes lignes que celles que `add_xp` aurait accordées en
  franchissant ce niveau), via la nouvelle fonction `services/admin_actions.py::grant_reward_by_level`.
- **Style des commandes : slash, admin-only.** Cohérent avec `/event-participation` (tranche B) — pas de
  commandes texte comme la boutique (tranche C), qui elles utilisent un préfixe verbe-first pour des raisons de
  compatibilité avec du texte déjà établi. Ici on suit plutôt le précédent `/event-participation`, une commande
  slash unique et ponctuelle, pas une famille de sous-commandes texte.
- **`/setlevel` ne rejoue pas les récompenses ni le prestige.** Un outil brut de correction de niveau
  (`level` + `xp` au plancher de ce niveau), pas une simulation de montée en niveau. Si un admin veut aussi
  accorder la récompense du niveau atteint, il combine avec `/givereward niveau:N`.
- **`/addxp` doit ignorer la pénalité anti-alt de la tranche E.** Un gain d'XP accordé manuellement par un admin
  est un acte délibéré, pas un signal de farm passif — il ne doit pas être silencieusement réduit à 20% parce
  que la cible a un compte Discord récent.

## Bug découvert et corrigé en marge de cette tranche

En implémentant `/addxp`, réutilisation du point d'entrée central `cogs/xp_common.py::award_xp` (tranche B,
étendu en tranche E avec la pénalité anti-alt). Ce même point d'entrée est aussi utilisé par
`/event-participation` (tranche B) — qui, depuis l'ajout de la pénalité anti-alt en tranche E, réduisait
silencieusement son bonus de +50 XP à 20% pour tout membre ayant un compte Discord récent. Aucun test ne
l'aurait révélé (les fakes de test utilisaient un compte "ancien" par défaut). Corrigé en même temps que
l'ajout de `/addxp` :

- `cogs/xp_common.py::award_xp` accepte maintenant un paramètre `bypass_alt_guard: bool = False`.
- `/event-participation` et `/addxp` passent tous les deux `bypass_alt_guard=True` — tout octroi d'XP déclenché
  par un admin contourne la pénalité. Les sources passives (message, vocal, réaction) restent inchangées.
- `services/leveling.py::_get_or_create_level` renommé en `get_or_create_level` (public) pour être réutilisable
  depuis `services/admin_actions.py::set_level` sans dupliquer sa logique de création.

## Implémentation

- `services/admin_actions.py` (nouveau, pur/testable sans Discord) : `set_level`, `reset_user`,
  `grant_reward_by_level`.
- `cogs/admin.py` (nouveau cog) : les 7 commandes slash, toutes `@app_commands.checks.has_permissions
  (administrator=True)`, réponses éphémères. Réutilise `services/economy.py::add_balance/subtract_balance`
  (avec `InsufficientBalanceError` déjà géré ailleurs pour `/pay`) et `services/leveling.py::subtract_xp` déjà
  existants — aucune nouvelle logique de calcul d'XP/coins, uniquement l'exposition admin de mécanismes déjà en
  place.
- `/givereward badge:[clé inconnue]` renvoie un message d'erreur clair (`NoResultFound` de
  `grant_badge_by_key` catché dans le cog) plutôt que de crasher.

## Non couvert par cette tranche

- Pas de confirmation interactive (bouton) avant `/resetuser` — la vérification de permission admin est la
  seule barrière, cohérent avec le reste du projet (`.remove market` n'a pas non plus de confirmation).
- `/addxp`/`/removexp`/`/addcoins`/`/removecoins` n'écrivent pas de journal d'audit (qui a exécuté quoi, quand)
  — à envisager si le besoin de traçabilité admin se fait sentir en pratique.
