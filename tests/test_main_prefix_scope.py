from main import (
    ADMIN_COMMAND_NAMES,
    YORU_DUPLICATE_RESTRICTED_GUILD_ID,
    _is_money_command,
    _is_yoru_duplicate_command,
)


class FakeCtx:
    def __init__(self, cog):
        self.cog = cog


def _cog_with_module(module: str):
    cls = type("FakeCog", (), {"__module__": module})
    return cls()


def test_is_money_command_true_for_crates_module():
    ctx = FakeCtx(cog=_cog_with_module("cogs.crates"))
    assert _is_money_command(ctx) is True


def test_is_money_command_true_for_economy_and_market():
    assert _is_money_command(FakeCtx(cog=_cog_with_module("cogs.economy"))) is True
    assert _is_money_command(FakeCtx(cog=_cog_with_module("cogs.market"))) is True


def test_is_money_command_false_for_other_modules():
    ctx = FakeCtx(cog=_cog_with_module("cogs.profile"))
    assert _is_money_command(ctx) is False


def test_key_command_not_in_admin_names():
    assert "key" not in ADMIN_COMMAND_NAMES


def test_is_yoru_duplicate_command_true_for_tour_casino_gacha():
    assert _is_yoru_duplicate_command(FakeCtx(cog=_cog_with_module("cogs.tour"))) is True
    assert _is_yoru_duplicate_command(FakeCtx(cog=_cog_with_module("cogs.casino"))) is True
    assert _is_yoru_duplicate_command(FakeCtx(cog=_cog_with_module("cogs.gacha"))) is True


def test_is_yoru_duplicate_command_false_for_other_modules():
    ctx = FakeCtx(cog=_cog_with_module("cogs.crime"))
    assert _is_yoru_duplicate_command(ctx) is False
    ctx = FakeCtx(cog=_cog_with_module("cogs.invest"))
    assert _is_yoru_duplicate_command(ctx) is False


def test_yoru_duplicate_restricted_guild_id_is_serveur_random():
    assert YORU_DUPLICATE_RESTRICTED_GUILD_ID == 1353659915113336832


def test_act_command_is_admin_scoped():
    assert "act" in ADMIN_COMMAND_NAMES
