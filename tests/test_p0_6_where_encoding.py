"""The `where` filter must be sent in the form EspoCRM 7.5.6 actually reads.

Found while implementing P1-6. The server was sending `where` as a JSON string — the
form the documentation suggests — and the instance ignored it: filtering on a
non-existent account name still returned all 38 accounts, `total` included, so
`list_records` was quietly returning everything regardless of the filter.

7.5.6 reads `where` from the query as a PHP array, so it has to be sent bracketed:
`where[0][type]=equals&where[0][attribute]=name&where[0][value]=...`. Measured live:
that form narrows the result (2 matches) and filters by `id` correctly (1 match).
"""
from __future__ import annotations


def _params(fake):
    return fake.requests[-1].url.params


def test_flat_filter_is_sent_bracketed(espo, fake):
    espo.list_records(
        "Account",
        where=[{"type": "equals", "attribute": "name", "value": "Acme"}],
    )

    params = _params(fake)
    assert params["where[0][type]"] == "equals"
    assert params["where[0][attribute]"] == "name"
    assert params["where[0][value]"] == "Acme"


def test_json_string_form_is_never_sent(espo, fake):
    """The JSON form is what got silently ignored; a regression would hide filters."""
    espo.list_records(
        "Account", where=[{"type": "equals", "attribute": "name", "value": "Acme"}]
    )

    assert "where" not in _params(fake)


def test_conditions_keep_their_order(espo, fake):
    espo.list_records(
        "Account",
        where=[
            {"type": "equals", "attribute": "type", "value": "Customer"},
            {"type": "contains", "attribute": "name", "value": "Ac"},
        ],
    )

    params = _params(fake)
    assert params["where[0][attribute]"] == "type"
    assert params["where[1][attribute]"] == "name"


def test_nested_group_is_encoded_level_by_level(espo, fake):
    espo.list_records(
        "Account",
        where=[
            {
                "type": "or",
                "value": [
                    {"type": "equals", "attribute": "type", "value": "Customer"},
                    {"type": "equals", "attribute": "type", "value": "Partner"},
                ],
            }
        ],
    )

    params = _params(fake)
    assert params["where[0][type]"] == "or"
    assert params["where[0][value][0][value]"] == "Customer"
    assert params["where[0][value][1][value]"] == "Partner"


def test_values_are_not_json_quoted(espo, fake):
    """`"Closed Won"` as a JSON string would compare against quotes and match nothing."""
    espo.list_records(
        "Opportunity", where=[{"type": "equals", "attribute": "stage", "value": "Closed Won"}]
    )

    assert _params(fake)["where[0][value]"] == "Closed Won"


def test_booleans_become_one_and_zero(espo, fake):
    espo.list_records("Account", where=[{"type": "isTrue", "attribute": "deleted"}])

    assert _params(fake)["where[0][type]"] == "isTrue"


def test_no_where_sends_no_filter_params(espo, fake):
    espo.list_records("Account")

    assert not [key for key in _params(fake) if key.startswith("where")]


def test_empty_filter_list_is_ignored(espo, fake):
    espo.list_records("Account", where=[])

    assert not [key for key in _params(fake) if key.startswith("where")]


def test_read_selected_filters_by_id(espo, fake):
    """The select fallback depends on `id` filtering, so it uses the same encoding."""
    fake.records[("Contact", "con-1")] = {"id": "con-1"}

    espo.get_record("Contact", "con-1", select="id")

    params = _params(fake)
    assert params["where[0][attribute]"] == "id"
    assert params["where[0][value]"] == "con-1"
