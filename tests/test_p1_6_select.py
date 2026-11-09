"""P1-6 — `select` on the read paths that can return huge payloads.

`list_records` already accepted `select`; `get_record` and `list_related` did not, so
reading one medical record or one account's contacts dumped every field. EspoCRM
honours `select` as a comma-separated list on both endpoints.
"""
from __future__ import annotations

import json


def _last_params(fake):
    return fake.requests[-1].url.params


def test_get_record_without_select_reads_the_record_directly(espo, fake):
    fake.records[("Contact", "con-1")] = {"id": "con-1", "firstName": "Ana"}

    record = espo.get_record("Contact", "con-1")

    assert record["firstName"] == "Ana"
    assert fake.requests[-1].url.path == "/api/v1/Contact/con-1"


def test_get_record_with_select_uses_the_list_endpoint(espo, fake):
    """7.5.6 ignores `select` on the single-record endpoint, so we go through the list.

    Measured live: `GET /Account/{id}?select=id,name` returned all 58 fields.
    """
    fake.records[("Contact", "con-1")] = {"id": "con-1", "firstName": "Ana"}

    record = espo.get_record("Contact", "con-1", select="id,firstName")

    params = _last_params(fake)
    assert fake.requests[-1].url.path == "/api/v1/Contact"
    assert params["select"] == "id,firstName"
    assert params["where[0][type]"] == "equals"
    assert params["where[0][attribute]"] == "id"
    assert params["where[0][value]"] == "con-1"
    assert params["maxSize"] == "1"
    assert record == {"id": "con-1", "firstName": "Ana"}


def test_get_record_with_select_reports_a_missing_record(espo, fake):
    result = espo.get_record("Contact", "nope", select="id,firstName")

    assert result["error"] == 404
    assert result["data"] == {"id": "nope"}


def test_list_related_forwards_select(espo, fake):
    espo.list_related("Account", "acc-1", "contacts", select="id,name")

    assert _last_params(fake)["select"] == "id,name"


def test_list_related_without_select_sends_no_param(espo, fake):
    espo.list_related("Account", "acc-1", "contacts")

    assert "select" not in _last_params(fake)


def test_list_records_still_forwards_select(espo, fake):
    espo.list_records("Account", select="id,name")

    assert _last_params(fake)["select"] == "id,name"


def test_empty_select_is_treated_as_absent(espo, fake):
    """An empty string would ask EspoCRM for zero fields, which is never intended."""
    espo.get_record("Contact", "con-1", select="")

    assert "select" not in _last_params(fake)
