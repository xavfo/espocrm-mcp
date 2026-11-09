#!/usr/bin/env python3
"""Measure how this EspoCRM instance parses the datetime formats callers send.

Creates one `Meeting` per format, reads it back and deletes it, so the stored value
shows how the server interpreted each input. This is the evidence behind the date
normalisation rules; rerun it after an EspoCRM upgrade.

Usage (PowerShell):

    $env:ESPO_URL = "https://crm.example.com"
    $env:ESPO_API_KEY = "..."
    python scripts/probe_dates.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

CASES = [
    "2026-12-01 10:00:00",
    "2026-12-01T10:00:00",
    "2026-12-01T10:00:00Z",
    "2026-12-01T10:00:00-05:00",
    "2026-12-01T10:00:00+00:00",
]


def main() -> int:
    prefs = server._req("GET", "/App/user").get("preferences", {})
    print(
        f"timeZone={prefs.get('timeZone')!r} "
        f"dateFormat={prefs.get('dateFormat')!r} "
        f"timeFormat={prefs.get('timeFormat')!r}\n"
    )

    user_id = server._current_user().get("id")
    for value in CASES:
        created = server._req(
            "POST",
            "/Meeting",
            json={
                "name": "MCPTEST date probe",
                "dateStart": value,
                "dateEnd": "2026-12-31 23:00:00",
                "assignedUserId": user_id,
            },
        )
        if not created.get("id"):
            print(f"{value!r:30} -> {created.get('error')} {json.dumps(created.get('data'), ensure_ascii=False)}")
            continue
        try:
            stored = server._req("GET", f"/Meeting/{created['id']}")
            print(f"{value!r:30} -> guardado como {stored.get('dateStart')!r}")
        finally:
            server._req("DELETE", f"/Meeting/{created['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
