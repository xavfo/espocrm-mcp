"""P0-5 — errors must give the caller something to act on.

The old `_req` returned `{"error": status, "body": "<raw text>"}`. For an LLM that
is nearly useless: the reason is buried in a string it has to parse, and 7.5.6 does
not even always provide a `message`.

Measured on a live 7.5.6 instance, an invalid enum value answers:

    {"messageTranslation": {"label": "validationFailure", "scope": null,
                            "data": {"field": "pacienteCedula", "type": "required"}}}

so the label must be unpacked and `data` promoted to the top level.
"""
from __future__ import annotations

import httpx


def _transport(espo, handler):
    espo._client = httpx.Client(
        base_url="https://crm.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )


def test_acceptance_case_type_validation_is_actionable(espo, fake):
    """Acceptance criterion: an invalid `Case.type` names the offending field.

    This goes through `_req` on purpose. The pre-flight layer added in P1-2 catches
    a known-invalid enum before a request is made, so the only way to pin what
    happens when the *server* rejects is to bypass that layer.
    """
    result = espo._req("POST", "/Case", json={"name": "Prueba", "type": "Feature Request"})

    assert result["error"] == 400
    assert result["message"] == "validationFailure"
    assert result["data"] == {"field": "type", "type": "valid"}


def test_error_keeps_the_raw_body(espo, fake):
    result = espo._req("POST", "/Case", json={"name": "Prueba", "type": "Nope"})

    assert result["body"]["messageTranslation"]["scope"] is None


def test_plain_message_and_data_are_promoted(espo, fake):
    """The `message`/`data` shape is used by other 7.5.6 errors (403s, for example)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "Forbidden", "data": {"field": "assignedUserId"}},
        )

    _transport(espo, handler)

    result = espo.get_record("Account", "acc-1")

    assert result["error"] == 403
    assert result["message"] == "Forbidden"
    assert result["data"] == {"field": "assignedUserId"}


def test_non_json_error_falls_back_to_text(espo, fake):
    """A proxy or a PHP fatal error answers HTML; the caller still gets the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html><body>Bad Gateway</body></html>")

    _transport(espo, handler)

    result = espo.get_record("Account", "acc-1")

    assert result["error"] == 502
    assert "Bad Gateway" in result["body"]
    assert result["message"]


def test_conflict_suggests_skipping_the_duplicate_check(espo, fake):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409, json={"messageTranslation": {"label": "duplicate"}, "data": {"id": "acc-9"}}
        )

    _transport(espo, handler)

    result = espo.create_record("Account", {"name": "Acme"})

    assert result["error"] == 409
    assert result["data"] == {"id": "acc-9"}
    assert "X-Skip-Duplicate-Check" in result["hint"]


def test_empty_success_body_is_reported_as_ok(espo, fake):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    _transport(espo, handler)

    assert espo.subscribe("Account", "acc-1") == {"ok": True}


def test_success_payload_is_returned_untouched(espo, fake):
    """No error keys may leak into successful responses."""
    created = espo.create_record("Account", {"name": "Acme", "tipoIdentificacion": "05"})

    assert set(created) == {"id", "name"}
