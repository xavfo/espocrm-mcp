#!/usr/bin/env python3
"""Live acceptance run of the P0 fixes against a real EspoCRM instance.

Calls the actual MCP tool functions (not raw HTTP) so the wire format under test is
the one the server ships. It creates temporary records with a visible marker and
deletes every record it created, in a `finally` block.

Usage (PowerShell):

    $env:ESPO_URL = "https://crm.example.com"
    $env:ESPO_API_KEY = "..."
    python scripts/live_acceptance.py            # create, verify, clean up
    python scripts/live_acceptance.py --keep     # leave records for inspection

Exit code is 0 only when every check passes.
"""
from __future__ import annotations

import base64
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402  (needs ESPO_URL/ESPO_API_KEY set before import)

logging.getLogger("httpx").setLevel(logging.WARNING)

MARKER = f"MCPTEST-{uuid.uuid4().hex[:8]}"
FILE_BODY = f"archivo de prueba {MARKER}".encode()

results: list[tuple[bool, str, str]] = []
created: list[tuple[str, str]] = []


def check(name: str, condition: Any, detail: str = "") -> bool:
    results.append((bool(condition), name, detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    return bool(condition)


def show(payload: Any, limit: int = 400) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return text[:limit]


def create(entity: str, data: dict[str, Any], label: str) -> str | None:
    """Create a record, remembering it for cleanup, and report the error if any."""
    response = server.create_record(entity, data)
    record_id = response.get("id") if isinstance(response, dict) else None
    if record_id:
        created.append((entity, record_id))
        return record_id
    print(f"      {label}: {show(response)}")
    return None


def cleanup(keep: bool) -> None:
    if keep:
        print(f"\n--keep: se dejan {len(created)} registros de prueba.")
        return
    print("\nLimpieza:")
    for entity, record_id in reversed(created):
        response = server.delete_record(entity, record_id)
        print(f"  delete {entity} {record_id}: {show(response, 120)}")


def run_steps() -> None:
    # --- baseline ------------------------------------------------------
    me = server.get_current_user()
    version = (me.get("settings") or {}).get("version", "") if isinstance(me, dict) else ""
    check("version es 7.5.x", str(version).startswith("7.5."), f"version={version}")

    # The instance is customised: Account needs `tipoIdentificacion` (enum 04..08,
    # default 05) and Contact needs `pacienteCedula` (varchar), mandatory in its
    # metadata. Omitting them is a 400 — the case the guide anticipates in P1-2.
    account_id = create(
        "Account", {"name": f"{MARKER} cuenta", "tipoIdentificacion": "05"}, "Account"
    )
    contact_id = create(
        "Contact",
        {
            "firstName": "MCP",
            "lastName": MARKER,
            "pacienteCedula": f"{uuid.uuid4().int % 10**10:010d}",
        },
        "Contact",
    )
    if not check("crear Account y Contact", bool(account_id and contact_id), f"{account_id} {contact_id}"):
        return

    # --- P0-1: unlink with IDs in the body -----------------------------
    check(
        "P0-1 link Account<->Contact",
        server.link_records("Account", account_id, "contacts", [contact_id]) is True,
    )
    linked = server.list_related("Account", account_id, "contacts")
    linked_ids = [record["id"] for record in linked.get("list", [])]
    check("P0-1 vínculo visible", contact_id in linked_ids, f"ids={linked_ids}")

    unlink = server.unlink_records("Account", account_id, "contacts", contact_id)
    check("P0-1 unlink devuelve true", unlink is True, f"respuesta={show(unlink)}")
    linked_after = server.list_related("Account", account_id, "contacts")
    remaining = [record["id"] for record in linked_after.get("list", [])]
    check("P0-1 el contacto ya no aparece", contact_id not in remaining, f"ids={remaining}")

    # --- P0-3: internal note -------------------------------------------
    note = server.create_note("Account", account_id, f"Nota interna {MARKER}", is_internal=True)
    note_id = note.get("id") if isinstance(note, dict) else None
    if note_id:
        created.append(("Note", note_id))
    else:
        print(f"      Note: {show(note)}")
    stored_note = server.get_record("Note", note_id) if note_id else {}
    check(
        "P0-3 isInternal persistido",
        bool(note_id) and stored_note.get("isInternal") is True,
        f"isInternal={stored_note.get('isInternal')} type={stored_note.get('type')}",
    )

    # --- P0-2: attachmentMultiple --------------------------------------
    holder = server.create_note("Account", account_id, f"Nota con adjunto {MARKER}")
    holder_id = holder.get("id") if isinstance(holder, dict) else None
    if holder_id:
        created.append(("Note", holder_id))
    else:
        print(f"      Note: {show(holder)}")

    upload = server.upload_attachment(
        name=f"{MARKER}.txt",
        mime_type="text/plain",
        file_base64=base64.b64encode(FILE_BODY).decode(),
        field="attachments",
        parent_type="Note",
        parent_id=holder_id,
    )
    attachment_id = upload.get("id") if isinstance(upload, dict) else None
    if attachment_id:
        created.append(("Attachment", attachment_id))
    check("P0-2 subida devuelve id", bool(attachment_id), f"respuesta={show(upload)}")

    if attachment_id and holder_id:
        updated = server.update_record("Note", holder_id, {"attachmentsIds": [attachment_id]})
        check("P0-2 PUT attachmentsIds", not (isinstance(updated, dict) and updated.get("error")), show(updated))
        reloaded = server.get_record("Note", holder_id)
        ids = reloaded.get("attachmentsIds") or []
        check("P0-2 adjunto asociado a la nota", attachment_id in ids, f"attachmentsIds={ids}")


def main() -> int:
    keep = "--keep" in sys.argv
    print(f"Instancia: {server.ESPO_URL}\nMarcador: {MARKER}\n")
    try:
        run_steps()
    finally:
        cleanup(keep)

    failed = [name for passed, name, _ in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} verificaciones correctas")
    if failed:
        print("Fallaron: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
