"""Test harness for `server.py` against a simulated EspoCRM 7.5.6 API.

`server.py` is a single-module script that exits at import time when `ESPO_URL` or
`ESPO_API_KEY` are missing, and talks to EspoCRM through one module-level `httpx`
client. Both facts make it untestable as-is, so the harness does two things:

1. Sets placeholder credentials *before* `server` is imported.
2. Swaps `server._client` for a client backed by `httpx.MockTransport`, which routes
   every request to an in-memory `FakeEspo`.

The fake deliberately reproduces the 7.5.6 quirks documented in
`docs/DESARROLLO-7.5.6.md` — for instance, ignoring a query-string `?id=` on
unlink — so a regression in the client fails a test instead of passing silently
against a permissive mock.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Must happen before `server` is imported: the module exits on missing config.
os.environ.setdefault("ESPO_URL", "https://crm.test")
os.environ.setdefault("ESPO_API_KEY", "test-api-key")

API_PREFIX = "/api/v1"

CASE_TYPES = {"Question", "Incident", "Problem"}

# Trimmed frontend metadata: enough shape to navigate, small enough to read.
METADATA: dict[str, Any] = {
    "scopes": {
        "Account": {"entity": True},
        "Contact": {"entity": True},
        "Note": {"entity": True},
        "AddressCountry": {"entity": False},
    },
    "entityDefs": {
        "Account": {
            "fields": {
                "name": {"type": "varchar", "required": True},
                "tipoIdentificacion": {
                    "type": "enum",
                    "required": True,
                    "default": "05",
                    "options": ["04", "05", "06", "07", "08"],
                },
            }
        },
        "Contact": {"fields": {"pacienteCedula": {"type": "varchar", "required": True}}},
        "Task": {
            "fields": {
                "name": {"type": "varchar", "required": True},
                "assignedUser": {"type": "link", "required": True},
                "parent": {"type": "linkParent", "required": True},
                "status": {
                    "type": "enum",
                    "default": "Not Started",
                    "options": ["Not Started", "Started", "Completed", "Canceled", "Deferred"],
                },
            }
        },
    },
    "clientDefs": {"Account": {}},
}


class FakeEspo:
    """In-memory stand-in for the EspoCRM REST API, faithful to 7.5.6 behaviour."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        # (entity, record_id, link) -> linked record IDs
        self.links: dict[tuple[str, str, str], list[str]] = {}
        # (entity, record_id) -> stored record, as EspoCRM would return it
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.metadata: dict[str, Any] = METADATA
        # Mirrors `GET /Metadata?key=` being admin-only on a stock 7.5.6.
        self.metadata_key_forbidden = False

    # -- routing ----------------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        parts = [p for p in request.url.path.split("/") if p]
        if parts[:2] != ["api", "v1"]:
            return httpx.Response(404, json={"message": f"Unknown prefix: {request.url.path}"})

        segments = parts[2:]
        method = request.method
        if len(segments) == 1:
            if segments[0] == "Metadata":
                return self._metadata(request, method)
            return self._create_record(request, method, segments[0])
        if len(segments) == 2:
            return self._record(request, method, *segments)
        if len(segments) == 3:
            entity, record_id, link = segments
            if method == "DELETE":
                return self._remove_link(request, entity, record_id, link)
            if method == "POST":
                return self._create_link(request, entity, record_id, link)
            if method == "GET":
                return self._list_link(entity, record_id, link)
        return httpx.Response(
            404, json={"message": f"Unhandled {method} {request.url.path}"}
        )

    # -- metadata endpoint ------------------------------------------------
    def _metadata(self, request: httpx.Request, method: str) -> httpx.Response:
        if method != "GET":
            return httpx.Response(405, json={"message": f"{method} /Metadata not simulated"})
        key = request.url.params.get("key")
        if key and self.metadata_key_forbidden:
            # Stock 7.5.6: `getActionGet` requires an administrator.
            return httpx.Response(403, json={"message": "Forbidden"})
        if key:
            return httpx.Response(200, json=_navigate(self.metadata, key))
        return httpx.Response(200, json=self.metadata)

    # -- record endpoints -------------------------------------------------
    def _create_record(
        self, request: httpx.Request, method: str, entity: str
    ) -> httpx.Response:
        if method != "POST":
            return httpx.Response(
                405, json={"message": f"{method} /{entity} is not simulated"}
            )
        body = _body(request)
        if entity == "Case" and "type" in body and body["type"] not in CASE_TYPES:
            # The shape real 7.5.6 returns for an invalid enum value (measured live).
            return httpx.Response(
                400,
                json={
                    "messageTranslation": {
                        "label": "validationFailure",
                        "scope": None,
                        "data": {"field": "type", "type": "valid"},
                    }
                },
            )
        stored = dict(body)
        if entity == "Note":
            # 7.5.6 quirks that P0-3 is about: `type` is readOnly (the server sets it
            # and discards whatever the client sent), and `isInternal` is only read
            # from the top level — nesting it inside `data` has no effect.
            stored.pop("type", None)
            stored["type"] = "Post"
            stored["isInternal"] = bool(stored.get("isInternal", False))
        record_id = f"{entity.lower()}-{len(self.records) + 1}"
        self.records[(entity, record_id)] = {"id": record_id, **stored}
        response: dict[str, Any] = {"id": record_id}
        if "name" in body:
            response["name"] = body["name"]
        return httpx.Response(200, json=response)

    def _record(
        self, request: httpx.Request, method: str, entity: str, record_id: str
    ) -> httpx.Response:
        key = (entity, record_id)
        if method in ("GET", "PUT", "PATCH") and key not in self.records:
            return httpx.Response(404, json={"message": f"{entity} {record_id} not found"})
        if method == "GET":
            return httpx.Response(200, json=self.records[key])
        if method in ("PUT", "PATCH"):
            self.records[key].update(_body(request))
            return httpx.Response(200, json=self.records[key])
        if method == "DELETE":
            self.records.pop(key, None)
            return httpx.Response(200, json=True)
        return httpx.Response(405, json={"message": f"{method} not simulated"})

    # -- relationship endpoints -------------------------------------------
    def _remove_link(
        self, request: httpx.Request, entity: str, record_id: str, link: str
    ) -> httpx.Response:
        """Mirror `Record::deleteActionRemoveLink` — body only, query ignored."""
        body = _body(request)
        ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
        if not ids:
            # The query string is not read by 7.5.6: nothing is removed, `false`.
            return httpx.Response(200, json=False)
        key = (entity, record_id, link)
        current = self.links.get(key, [])
        self.links[key] = [record for record in current if record not in ids]
        return httpx.Response(200, json=True)

    def _create_link(
        self, request: httpx.Request, entity: str, record_id: str, link: str
    ) -> httpx.Response:
        body = _body(request)
        ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
        if not ids:
            return httpx.Response(200, json=False)
        key = (entity, record_id, link)
        current = self.links.setdefault(key, [])
        current.extend(record for record in ids if record not in current)
        return httpx.Response(200, json=True)

    def _list_link(self, entity: str, record_id: str, link: str) -> httpx.Response:
        ids = self.links.get((entity, record_id, link), [])
        return httpx.Response(
            200, json={"list": [{"id": record} for record in ids], "total": len(ids)}
        )


def _body(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    try:
        parsed = json.loads(request.content)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _navigate(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@pytest.fixture
def fake() -> FakeEspo:
    """A fresh simulated EspoCRM instance."""
    return FakeEspo()


@pytest.fixture
def espo(fake: FakeEspo):
    """The `server` module, wired to the simulated instance."""
    server = importlib.import_module("server")
    server._metadata_cache = None  # module-level cache must not leak between tests
    server._client = httpx.Client(
        base_url=f"https://crm.test{API_PREFIX}",
        headers={"X-Api-Key": "test-api-key", "Content-Type": "application/json"},
        transport=httpx.MockTransport(fake.handler),
        timeout=5.0,
    )
    return server
