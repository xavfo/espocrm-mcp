"""P1-8 — timeouts, retries and tracing.

A single `httpx` call with a fixed 30 s timeout meant one slow request could stall a
whole conversation, and a `429` from EspoCRM was surfaced as an error instead of being
retried. Tracing is required by the design principles, but on stderr: stdout carries
the MCP protocol, and the API key must never appear in a log line.
"""
from __future__ import annotations

import logging

import httpx


def _client(handler, espo):
    espo._client = httpx.Client(
        base_url="https://crm.test/api/v1",
        transport=httpx.MockTransport(handler),
        timeout=5.0,
    )


def test_timeout_and_retries_have_safe_defaults(espo):
    """The client is built from these at import time; the fixture swaps it out."""
    assert espo.ESPO_TIMEOUT == 30.0
    assert espo.ESPO_MAX_RETRIES == 2


def test_429_is_retried_and_honours_retry_after(espo):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "slow down"})
        return httpx.Response(200, json={"id": "acc-1"})

    _client(handler, espo)

    result = espo.get_record("Account", "acc-1")

    assert result["id"] == "acc-1"
    assert len(calls) == 2


def test_server_error_on_read_is_retried(espo):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 2:
            return httpx.Response(503, text="")
        return httpx.Response(200, json={"id": "acc-1"})

    _client(handler, espo)

    assert espo.get_record("Account", "acc-1")["id"] == "acc-1"
    assert len(calls) == 2


def test_server_error_on_write_is_not_retried(espo):
    """A failed POST may have created the record; duplicating it is worse."""
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(500, json={"message": "boom"})

    _client(handler, espo)

    result = espo.create_record("Account", {"name": "Acme"})

    assert result["error"] == 500
    assert methods.count("POST") == 1


def test_retries_are_capped(espo):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="")

    _client(handler, espo)

    espo.get_record("Account", "acc-1")

    assert len(calls) == espo.ESPO_MAX_RETRIES + 1


def test_transport_error_on_read_is_retried(espo):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"id": "acc-1"})

    _client(handler, espo)

    assert espo.get_record("Account", "acc-1")["id"] == "acc-1"
    assert len(calls) == 2


def test_transport_error_is_reported_when_it_persists(espo):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("no route")

    _client(handler, espo)

    result = espo.get_record("Account", "acc-1")

    assert result["error"] == "transport"
    assert "no route" in result["message"]


def test_requests_are_traced_without_the_api_key(espo, fake, caplog):
    fake.records[("Account", "acc-1")] = {"id": "acc-1"}

    with caplog.at_level(logging.INFO, logger="espocrm"):
        espo.get_record("Account", "acc-1")

    assert "GET /Account/acc-1" in caplog.text
    assert "-> 200" in caplog.text
    assert "test-api-key" not in caplog.text


def test_tracing_can_be_silenced(espo, caplog):
    previous = espo.logger.level
    try:
        espo.logger.setLevel(logging.WARNING)
        with caplog.at_level(logging.WARNING, logger="espocrm"):
            espo.get_record("Account", "acc-1")
        assert "GET /Account/acc-1" not in caplog.text
    finally:
        espo.logger.setLevel(previous)
