"""P0-4 — metadata must not require an administrator.

`GET /Metadata?key=...` calls `Metadata::getActionGet`, which requires `isAdmin()`
in 7.5.6: a normal API user gets 403 and every metadata-driven tool dies. The
unparameterised `GET /Metadata` is readable by any authenticated user and returns
what the frontend uses, so the client downloads it once and navigates the tree.

Measured on a live 7.5.6 instance: the payload is ~979 KB and `?key=` is not even
honoured there (every key returns the full document), which is a second reason not
to depend on it — hence the one-fetch cache asserted below.
"""
from __future__ import annotations

import httpx
import pytest


def _metadata_requests(fake) -> list[httpx.Request]:
    return [r for r in fake.requests if r.url.path.endswith("/Metadata")]


def test_metadata_is_readable_without_admin(espo, fake):
    """Acceptance criterion: a non-admin user can read `entityDefs.Account.fields`."""
    fake.metadata_key_forbidden = True  # stock 7.5.6 behaviour for `?key=`

    fields = espo.get_metadata("entityDefs.Account.fields")

    assert "name" in fields
    assert all("key" not in request.url.params for request in _metadata_requests(fake))


def test_metadata_is_downloaded_only_once(espo, fake):
    espo.get_metadata("entityDefs.Account.fields")
    espo.get_metadata("scopes")
    espo.list_entity_types()

    assert len(_metadata_requests(fake)) == 1


def test_get_metadata_returns_only_the_requested_subtree(espo, fake):
    value = espo.get_metadata("entityDefs.Account.fields")

    assert value == fake.metadata["entityDefs"]["Account"]["fields"]


def test_get_metadata_without_scope_returns_a_compact_index(espo, fake):
    """The full payload is ~1 MB; sending it to an LLM crowds out the conversation."""
    index = espo.get_metadata()

    assert "entityDefs" in index["keys"]
    assert index["scopes"] == ["Account", "Contact", "Note"]
    assert "hint" in index


def test_unknown_scope_reports_the_available_sections(espo, fake):
    result = espo.get_metadata("entityDefs.NoSuchEntity.fields")

    assert result["error"] == "scope not found"
    assert "entityDefs" in result["keys"]


def test_list_entity_types_returns_only_entity_scopes(espo, fake):
    assert espo.list_entity_types() == ["Account", "Contact", "Note"]


def test_list_entity_types_does_not_use_the_admin_endpoint(espo, fake):
    fake.metadata_key_forbidden = True

    assert espo.list_entity_types() == ["Account", "Contact", "Note"]
    assert all("key" not in request.url.params for request in _metadata_requests(fake))


def test_failed_fetch_is_not_cached(espo, fake):
    """A transient 500 must not poison the cache for the rest of the process."""
    token = {"ok": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Metadata") and not token["ok"]:
            return httpx.Response(500, json={"message": "boom"})
        return fake.handler(request)

    espo._client = httpx.Client(
        base_url="https://crm.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )

    assert espo.get_metadata("scopes").get("error") == 500
    token["ok"] = True
    assert "Account" in espo.get_metadata("scopes")


def test_admin_mode_uses_the_filtered_endpoint(espo, fake, monkeypatch):
    """`ESPO_METADATA_MODE=admin` is the opt-in for instances where it does work."""
    monkeypatch.setattr(espo, "METADATA_MODE", "admin")

    assert espo.get_metadata("scopes")["Account"] == {"entity": True}

    request = _metadata_requests(fake)[-1]
    assert request.url.params["key"] == "scopes"


def test_admin_mode_still_reports_403(espo, fake, monkeypatch):
    monkeypatch.setattr(espo, "METADATA_MODE", "admin")
    fake.metadata_key_forbidden = True

    result = espo.get_metadata("scopes")

    assert result["error"] == 403
