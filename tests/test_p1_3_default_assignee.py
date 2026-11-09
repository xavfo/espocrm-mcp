"""P1-3 — `Meeting`, `Call` and `Task` need an assignee on 7.5.6.

Measured live: creating a `Meeting` without `assignedUserId` answers
400 `{"messageTranslation": {"label": "validationFailure",
"data": {"field": "assignedUser", "type": "required"}}}`.

7.5.6 only fills the field by itself when the role forbids assigning; when the role
allows it, the value has to come from the caller. So the server injects the API user
and keeps a fallback for the opposite role configuration.
"""
from __future__ import annotations

import json

import httpx
import pytest


def _payloads(fake) -> list[dict]:
    return [
        json.loads(r.content)
        for r in fake.requests
        if r.method == "POST" and not r.url.path.endswith("/Metadata")
    ]


@pytest.mark.parametrize(
    "entity,data",
    [
        ("Meeting", {"name": "Kickoff", "dateStart": "2026-12-01 10:00:00",
                     "dateEnd": "2026-12-01 11:00:00"}),
        ("Call", {"name": "Llamada", "dateStart": "2026-12-01 10:00:00",
                  "dateEnd": "2026-12-01 10:30:00"}),
        ("Task", {"name": "Llamar", "parentId": "acc-1", "parentType": "Account"}),
    ],
)
def test_missing_assignee_is_filled_with_the_api_user(espo, fake, entity, data):
    created = espo.create_record(entity, data)

    assert "id" in created
    assert _payloads(fake)[-1]["assignedUserId"] == "user-1"


def test_entities_without_the_requirement_are_untouched(espo, fake):
    espo.create_record("Account", {"name": "Acme"})

    assert "assignedUserId" not in _payloads(fake)[-1]


def test_explicit_assignee_is_respected(espo, fake):
    espo.create_record(
        "Meeting",
        {
            "name": "Kickoff",
            "dateStart": "2026-12-01 10:00:00",
            "dateEnd": "2026-12-01 11:00:00",
            "assignedUserId": "someone-else",
        },
    )

    assert _payloads(fake)[-1]["assignedUserId"] == "someone-else"


def test_current_user_is_fetched_once(espo, fake):
    for _ in range(2):
        espo.create_record(
            "Task", {"name": "Llamar", "parentId": "acc-1", "parentType": "Account"}
        )

    user_calls = [r for r in fake.requests if r.url.path.endswith("/App/user")]
    assert len(user_calls) == 1


def test_injection_can_be_disabled(espo, fake, monkeypatch):
    """For a role that forbids the field, the server does the assigning itself."""
    monkeypatch.setattr(espo, "AUTO_ASSIGN", False)

    espo.create_record(
        "Meeting",
        {"name": "Kickoff", "dateStart": "2026-12-01 10:00:00",
         "dateEnd": "2026-12-01 11:00:00"},
    )

    assert "assignedUserId" not in _payloads(fake)[-1]


def test_forbidden_field_falls_back_to_a_payload_without_it(espo, fake):
    """A 403 on the injected field is retried once without it (nothing was created)."""
    fake.forbid_assignment = True

    created = espo.create_record(
        "Meeting",
        {"name": "Kickoff", "dateStart": "2026-12-01 10:00:00",
         "dateEnd": "2026-12-01 11:00:00"},
    )

    assert "id" in created
    attempts = _payloads(fake)
    assert attempts[0]["assignedUserId"] == "user-1"
    assert "assignedUserId" not in attempts[-1]


def test_unrelated_403_is_not_retried(espo, fake):
    """Only the assignee may be dropped; any other 403 must surface as it is."""
    attempts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/Meeting"):
            attempts.append(request)
            return httpx.Response(403, json={"message": "Forbidden"})
        return fake.handler(request)

    espo._client = httpx.Client(
        base_url="https://crm.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )

    result = espo.create_record(
        "Meeting",
        {"name": "Kickoff", "dateStart": "2026-12-01 10:00:00",
         "dateEnd": "2026-12-01 11:00:00"},
    )

    assert result["error"] == 403
    assert len(attempts) == 1


def test_unreadable_profile_still_creates_the_record(espo, fake, monkeypatch):
    monkeypatch.setattr(espo, "_current_user", lambda: {})

    created = espo.create_record(
        "Meeting",
        {"name": "Kickoff", "dateStart": "2026-12-01 10:00:00",
         "dateEnd": "2026-12-01 11:00:00"},
    )

    assert "id" in created
    assert "assignedUserId" not in _payloads(fake)[-1]
