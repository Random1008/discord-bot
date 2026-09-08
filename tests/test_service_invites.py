from services.invites import diff_invite_uses


def test_diff_invite_uses_finds_incremented_code():
    before = {"abc123": 5, "xyz789": 0}
    after = {"abc123": 6, "xyz789": 0}

    assert diff_invite_uses(before, after) == "abc123"


def test_diff_invite_uses_handles_new_code_not_in_before():
    before = {"abc123": 5}
    after = {"abc123": 5, "newcode": 1}

    assert diff_invite_uses(before, after) == "newcode"


def test_diff_invite_uses_returns_none_when_nothing_changed():
    before = {"abc123": 5}
    after = {"abc123": 5}

    assert diff_invite_uses(before, after) is None
