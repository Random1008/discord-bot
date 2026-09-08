PRESTIGE_LEVEL_THRESHOLDS = {100: 1, 200: 2, 300: 3, 500: 4}
PRESTIGE_MULTIPLIERS = {0: 1.0, 1: 1.1, 2: 1.2, 3: 1.3, 4: 1.5}


def prestige_for_level(level: int) -> int:
    reached = 0
    for threshold, tier in PRESTIGE_LEVEL_THRESHOLDS.items():
        if level >= threshold:
            reached = max(reached, tier)
    return reached


def multiplier_for_prestige(prestige: int) -> float:
    return PRESTIGE_MULTIPLIERS.get(prestige, 1.0)
