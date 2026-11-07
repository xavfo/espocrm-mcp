"""P0-2 — `upload_attachment` must distinguish `file` from `attachmentMultiple`.

On EspoCRM 7.5.6 the attachment payload depends on the target field's type:

- `file` (e.g. `Document.file`) → `relatedType` + `relatedId` + `field`.
- `attachmentMultiple` (e.g. `Note.attachments`) → `parentType` (+ `parentId`) +
  `field`, then a separate `update_record` with `attachmentsIds`.

The old implementation only ever sent `relatedType`, so an upload destined for an
`attachmentMultiple` field succeeded as an orphan Attachment: HTTP 200, file
stored, never bound to the record. These tests pin each payload shape.
"""
from __future__ import annotations

import json

import pytest

BASE64 = "JVBERi0xLjQK"


def _last_payload(fake) -> dict:
    return json.loads(fake.requests[-1].content)


def test_attachment_multiple_uses_parent_type(espo, fake):
    espo.upload_attachment(
        "acta.pdf",
        "application/pdf",
        BASE64,
        field="attachments",
        parent_type="Note",
    )

    payload = _last_payload(fake)
    assert fake.requests[-1].url.path == "/api/v1/Attachment"
    assert payload["field"] == "attachments"
    assert payload["parentType"] == "Note"
    assert "relatedType" not in payload
    assert "relatedId" not in payload


def test_file_field_uses_related_type(espo, fake):
    espo.upload_attachment(
        "contrato.pdf",
        "application/pdf",
        BASE64,
        field="file",
        related_type="Document",
        related_id="doc-1",
    )

    payload = _last_payload(fake)
    assert payload["field"] == "file"
    assert payload["relatedType"] == "Document"
    assert payload["relatedId"] == "doc-1"
    assert "parentType" not in payload
    assert "parentId" not in payload


def test_payload_is_exactly_the_attachment_multiple_contract(espo, fake):
    """Strict check: no stray keys leak into the request EspoCRM receives."""
    espo.upload_attachment(
        "acta.pdf",
        "application/pdf",
        BASE64,
        field="attachments",
        parent_type="Note",
    )

    assert _last_payload(fake) == {
        "name": "acta.pdf",
        "type": "application/pdf",
        "role": "Attachment",
        "field": "attachments",
        "file": f"data:application/pdf;base64,{BASE64}",
        "parentType": "Note",
    }


def test_parent_id_is_sent_when_provided(espo, fake):
    espo.upload_attachment(
        "acta.pdf",
        "application/pdf",
        BASE64,
        field="attachments",
        parent_type="Note",
        parent_id="note-9",
    )

    assert _last_payload(fake)["parentId"] == "note-9"


def test_acceptance_upload_then_attach_to_note(espo, fake):
    """Acceptance criterion: the returned ID is accepted in `attachmentsIds`.

    The stored attachment is also checked, because a Note update alone would pass
    even with the bug: EspoCRM happily stores an orphan Attachment.
    """
    note = espo.create_record(
        "Note", {"parentType": "Account", "parentId": "acc-1", "post": "Acta"}
    )
    uploaded = espo.upload_attachment(
        "acta.pdf",
        "application/pdf",
        BASE64,
        field="attachments",
        parent_type="Note",
    )
    attachment_id = uploaded["id"]
    assert attachment_id
    assert fake.records[("Attachment", attachment_id)]["parentType"] == "Note"

    espo.update_record("Note", note["id"], {"attachmentsIds": [attachment_id]})

    stored = espo.get_record("Note", note["id"])
    assert stored["attachmentsIds"] == [attachment_id]


def test_field_is_required(espo):
    """`field` decides which payload mode applies, so it cannot be optional."""
    with pytest.raises(TypeError):
        espo.upload_attachment("acta.pdf", "application/pdf", BASE64)
