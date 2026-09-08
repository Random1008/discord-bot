import random

MESSAGE_XP_RANGE = (5, 15)
VOICE_XP_PER_INTERVAL = 10
VOICE_XP_INTERVAL_SECONDS = 600
REACTION_XP = 2
EVENT_PARTICIPATION_XP = 50
INVITE_VALIDATION_XP = 200


def roll_message_xp(rng=random) -> int:
    low, high = MESSAGE_XP_RANGE
    return rng.randint(low, high)


def voice_xp_for_seconds(seconds: int) -> int:
    intervals = seconds // VOICE_XP_INTERVAL_SECONDS
    return intervals * VOICE_XP_PER_INTERVAL
