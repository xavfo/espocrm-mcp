"""P0-1 — `unlink_records` must send the target ID in the JSON body.

EspoCRM 7.5.6's `Record::deleteActionRemoveLink` reads `id`/`ids` from the parsed
body. A query-string `?id=` is ignored, so the call answers `false` and the
relationship survives without any error — the worst kind of failure for an LLM
caller. These tests pin the wire format *and* the observable effect, so reverting
to `params={"id": ...}` fails loudly.
"""
from __future__ import annotations

import json

import httpx


def test_unlink_sends_ids_in_json_body(espo, fake):
    fake.links[("Account", "acc-1", "contacts")] = ["con-1", "con-2"]

    result = espo.unlink_records("Account", "acc-1", "contacts", "con-1")

    request = fake.requests[-1]
    assert request.method == "DELETE"
    assert request.url.path == "/api/v1/Account/acc-1/contacts"
    assert json.loads(request.content) == {"ids": ["con-1"]}
    assert result is True


def test_unlink_keeps_id_out_of_the_query_string(espo, fake):
    fake.links[("Account", "acc-1", "contacts")] = ["con-1"]

    espo.unlink_records("Account", "acc-1", "contacts", "con-1")

    assert "id" not in fake.requests[-1].url.params


def test_unlinked_record_disappears_from_the_link_list(espo, fake):
    """Acceptance criterion: it returns `true` and the record is no longer listed."""
    fake.links[("Account", "acc-1", "contacts")] = ["con-1", "con-2"]

    assert espo.unlink_records("Account", "acc-1", "contacts", "con-1") is True

    listed = espo.list_related("Account", "acc-1", "contacts")
    assert [record["id"] for record in listed["list"]] == ["con-2"]


def test_unlink_leaves_other_links_untouched(espo, fake):
    fake.links[("Account", "acc-1", "contacts")] = ["con-1", "con-2"]
    fake.links[("Account", "acc-1", "opportunities")] = ["opp-1"]

    espo.unlink_records("Account", "acc-1", "contacts", "con-1")

    assert fake.links[("Account", "acc-1", "opportunities")] == ["opp-1"]


def test_simulator_reproduces_756_semantics(fake):
    """Meta-check: the fake must ignore a query-string ID exactly like 7.5.6.

    Without this, a permissive mock could hide the very bug P0-1 fixes.
    """
    fake.links[("Account", "acc-1", "contacts")] = ["con-1"]

    request = httpx.Request(
        "DELETE",
        "https://crm.test/api/v1/Account/acc-1/contacts",
        params={"id": "con-1"},
    )

    assert fake.handler(request).json() is False
    assert fake.links[("Account", "acc-1", "contacts")] == ["con-1"]
