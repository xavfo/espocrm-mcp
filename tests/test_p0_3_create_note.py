"""P0-3 — `create_note` must send `isInternal` as a top-level boolean.

In 7.5.6, `Note.type` is `readOnly` (the server sets it) and `isInternal` is a
first-level `bool`. `Note.data` is a `jsonObject`, so an `isInternal` nested there
is stored as opaque JSON and ignored when the server decides visibility: the note
comes out public while the caller believes it is internal. That is a confidentiality
bug, not a cosmetic one — hence the strict payload assertions below.
"""
from __future__ import annotations

import json

import httpx


def _last_payload(fake) -> dict:
    return json.loads(fake.requests[-1].content)


def test_internal_flag_is_sent_at_top_level(espo, fake):
    espo.create_note("Account", "acc-1", "Nota interna", is_internal=True)

    payload = _last_payload(fake)
    assert payload["isInternal"] is True
    assert "data" not in payload


def test_read_only_type_is_not_sent(espo, fake):
    """`type` is readOnly in 7.5.6, so sending it only invites confusion."""
    espo.create_note("Account", "acc-1", "Hola")

    assert "type" not in _last_payload(fake)


def test_payload_is_exactly_the_note_contract(espo, fake):
    espo.create_note("Account", "acc-1", "Nota interna", is_internal=True)

    assert _last_payload(fake) == {
        "parentType": "Account",
        "parentId": "acc-1",
        "post": "Nota interna",
        "isInternal": True,
    }


def test_acceptance_internal_note_persists_the_flag(espo, fake):
    """Acceptance criterion: `GET /Note/{id}` reports `isInternal: true`."""
    created = espo.create_note(
        "Account", "acc-1", "Solo para el equipo", is_internal=True
    )

    stored = espo.get_record("Note", created["id"])
    assert stored["isInternal"] is True
    assert stored["type"] == "Post"


def test_note_is_public_by_default(espo, fake):
    created = espo.create_note("Account", "acc-1", "Comentario normal")

    assert _last_payload(fake)["isInternal"] is False
    assert espo.get_record("Note", created["id"])["isInternal"] is False


def test_attachment_ids_are_sent_when_provided(espo, fake):
    espo.create_note("Account", "acc-1", "Con adjuntos", attachment_ids=["att-1", "att-2"])

    assert _last_payload(fake)["attachmentsIds"] == ["att-1", "att-2"]


def test_attachment_ids_are_omitted_when_empty(espo, fake):
    espo.create_note("Account", "acc-1", "Sin adjuntos", attachment_ids=[])

    assert "attachmentsIds" not in _last_payload(fake)


def test_simulator_reproduces_the_nested_flag_quirk(fake):
    """Meta-check: `isInternal` inside `data` must NOT make the note internal."""
    response = fake.handler(
        httpx.Request(
            "POST",
            "https://crm.test/api/v1/Note",
            json={
                "parentType": "Account",
                "parentId": "acc-1",
                "post": "Nota",
                "data": {"isInternal": True},
            },
        )
    )

    assert response.json()["id"] == "note-1"
    stored = fake.records[("Note", response.json()["id"])]
    assert stored["isInternal"] is False
