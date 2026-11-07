"""P1-1 — `MCP_ENTITY_ALLOW` narrows what the server may touch.

The API key's scopes decide the hard limit, but that limit is usually wider than
what a deployment needs: a CRM key with account access also reaches every entity
the instance ships. This allow-list adds a second, explicit boundary, and it fails
*before* any request is sent.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def restricted(espo, monkeypatch):
    monkeypatch.setattr(espo, "ENTITY_ALLOW", frozenset({"Account", "Contact"}))
    return espo


def test_unrestricted_by_default(espo, fake):
    """No MCP_ENTITY_ALLOW means no restriction — the previous behaviour."""
    assert espo.ENTITY_ALLOW == frozenset()

    created = espo.create_record("Lead", {"lastName": "Perez"})

    assert "id" in created


def test_blocked_entity_is_rejected_without_a_request(restricted, fake):
    result = restricted.create_record("Lead", {"lastName": "Perez"})

    assert result["error"] == "entity_not_allowed"
    assert result["entity"] == "Lead"
    assert result["allowed"] == ["Account", "Contact"]
    assert fake.requests == []


def test_allowed_entity_still_works(restricted, fake):
    created = restricted.create_record(
        "Account", {"name": "Acme", "tipoIdentificacion": "05"}
    )

    assert created["id"] == "account-1"


@pytest.mark.parametrize(
    "call",
    [
        lambda espo: espo.list_records("Lead"),
        lambda espo: espo.get_record("Lead", "l-1"),
        lambda espo: espo.update_record("Lead", "l-1", {"lastName": "X"}),
        lambda espo: espo.delete_record("Lead", "l-1"),
        lambda espo: espo.list_related("Lead", "l-1", "contacts"),
        lambda espo: espo.link_records("Lead", "l-1", "contacts", ["c-1"]),
        lambda espo: espo.unlink_records("Lead", "l-1", "contacts", "c-1"),
        lambda espo: espo.get_stream("Lead", "l-1"),
        lambda espo: espo.subscribe("Lead", "l-1"),
        lambda espo: espo.unsubscribe("Lead", "l-1"),
        lambda espo: espo.create_note("Lead", "l-1", "hola"),
        lambda espo: espo.upload_attachment(
            "a.txt", "text/plain", "eA==", field="attachments", parent_type="Lead"
        ),
    ],
)
def test_every_tool_honours_the_list(restricted, fake, call):
    """A read/write path that skips the guard would be a way around the policy."""
    result = call(restricted)

    assert result["error"] == "entity_not_allowed"
    assert fake.requests == []


def test_global_stream_is_not_blocked(restricted, fake):
    """/Stream takes no entity, so the allow-list has nothing to check."""
    result = restricted.get_stream()

    assert not (isinstance(result, dict) and result.get("error") == "entity_not_allowed")
    assert len(fake.requests) == 1


def test_legal_entity_with_illegal_related_type(restricted, fake):
    """Uploading onto a blocked entity is still blocked, even via an allowed field."""
    result = restricted.upload_attachment(
        "a.txt", "text/plain", "eA==", field="file", related_type="Lead", related_id="l-1"
    )

    assert result["error"] == "entity_not_allowed"
    assert fake.requests == []
