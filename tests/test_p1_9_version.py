"""P1-9 — say out loud when the instance is not 7.5.x.

Every fix in this server was written against 7.5.6 behaviour. An instance on another
line will still be used (nothing is blocked), but `get_current_user` now reports a
`compatibility` block and a warning is logged once, so a wrong assumption is visible
instead of becoming a mystery 400.
"""
from __future__ import annotations

import logging


def test_matching_version_is_reported(espo, fake):
    data = espo.get_current_user()

    assert data["compatibility"] == {
        "version": "7.5.6",
        "expected": "7.5.x",
        "compatible": True,
    }


def test_other_version_is_flagged(espo, fake):
    fake.current_user["settings"]["version"] = "8.2.0"

    data = espo.get_current_user()

    assert data["compatibility"]["compatible"] is False
    assert data["compatibility"]["version"] == "8.2.0"


def test_missing_version_does_not_claim_compatibility(espo, fake):
    fake.current_user["settings"].pop("version")

    data = espo.get_current_user()

    assert data["compatibility"] == {"version": None, "expected": "7.5.x", "compatible": False}


def test_mismatch_is_warned_only_once(espo, fake, caplog):
    fake.current_user["settings"]["version"] = "8.2.0"

    with caplog.at_level(logging.WARNING, logger="espocrm"):
        espo.get_current_user()
        espo.get_current_user()

    warnings = [record for record in caplog.records if "8.2.0" in record.getMessage()]
    assert len(warnings) == 1


def test_the_payload_is_still_returned_untouched(espo, fake):
    """Compatibility is added, not substituted for the profile."""
    data = espo.get_current_user()

    assert data["user"]["id"] == "user-1"
    assert data["settings"]["version"] == "7.5.6"
