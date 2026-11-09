"""P1-2 — catch avoidable 400s before spending a round trip.

Two classes of mistake are checked, both unambiguous: a value outside a closed enum,
and a missing mandatory field. The instance's metadata is the authority; the
`ENTITY_RULES` table is only a fallback for entities the metadata does not know.

Measured live on 7.5.6: `Account.tipoIdentificacion` (enum `04`-`08`, default `05`)
and `Contact.pacienteCedula` are mandatory on a customised instance, so a hardcoded
table of core fields would miss them.
"""
from __future__ import annotations

import pytest


def _writes(fake) -> list:
    """Validation may read metadata and the profile; no write may go out."""
    return [r for r in fake.requests if r.method != "GET"]


def test_invalid_enum_is_caught_before_the_request(espo, fake):
    result = espo.create_record(
        "Account", {"name": "Acme", "tipoIdentificacion": "RUC"}
    )

    assert result["error"] == "validation_failed"
    assert result["problems"] == [
        {
            "field": "tipoIdentificacion",
            "type": "invalidOption",
            "value": "RUC",
            "allowed": ["04", "05", "06", "07", "08"],
        }
    ]
    assert _writes(fake) == []


def test_valid_enum_and_defaulted_required_field_pass(espo, fake):
    """`tipoIdentificacion` is required but defaulted: omitting it is not an error."""
    created = espo.create_record("Account", {"name": "Acme"})

    assert created["id"] == "account-1"


def test_missing_required_field_from_metadata_is_reported(espo, fake):
    result = espo.create_record("Contact", {"firstName": "Ana", "lastName": "Perez"})

    assert result["problems"] == [{"field": "pacienteCedula", "type": "required"}]
    assert _writes(fake) == []


def test_required_link_is_satisfied_by_its_id_field(espo, fake):
    """`parent` is a link: the payload carries `parentId`, not `parent`."""
    created = espo.create_record(
        "Task", {"name": "Llamar", "parentId": "acc-1", "parentType": "Account"}
    )

    assert created["id"] == "task-1"


def test_missing_required_link_is_reported(espo, fake):
    result = espo.create_record("Task", {"name": "Llamar"})

    assert {"field": "parent", "type": "required"} in result["problems"]


def test_assigned_user_is_not_required_up_front(espo, fake):
    """7.5.6 fills it when the role forbids assigning, so blocking would be wrong."""
    result = espo.create_record(
        "Task", {"name": "Llamar", "parentId": "acc-1", "parentType": "Account"}
    )

    assert "id" in result


def test_rules_table_is_the_fallback_for_unknown_entities(espo, fake):
    """`Meeting` is not in the fake metadata, so ENTITY_RULES decides."""
    result = espo.create_record("Meeting", {"name": "Kickoff"})

    fields = {problem["field"] for problem in result["problems"]}
    assert {"dateStart", "dateEnd"} <= fields
    assert "assignedUserId" not in fields  # exempt
    assert _writes(fake) == []


def test_rules_table_also_checks_enums(espo, fake):
    result = espo.create_record(
        "Meeting",
        {
            "name": "Kickoff",
            "dateStart": "2026-12-01 10:00:00",
            "dateEnd": "2026-12-01 11:00:00",
            "status": "Done",
        },
    )

    assert result["problems"] == [
        {"field": "status", "type": "invalidOption", "value": "Done",
         "allowed": ["Planned", "Held", "Not Held"]}
    ]


def test_update_checks_enums_but_not_missing_required(espo, fake):
    """A partial update must not demand fields it never touched."""
    stored = fake.records[("Contact", "contact-9")] = {"id": "contact-9"}

    assert espo.update_record("Contact", "contact-9", {"firstName": "Ana"}) == stored

    blocked = espo.update_record(
        "Account", "acc-1", {"tipoIdentificacion": "NO"}
    )
    assert blocked["error"] == "validation_failed"


def test_unreadable_metadata_does_not_break_writes(espo, fake, monkeypatch):
    """If metadata cannot be fetched, validation degrades instead of failing."""
    monkeypatch.setattr(espo, "_fetch_metadata", lambda: {"error": 500, "body": ""})

    created = espo.create_record("Account", {"name": "Acme"})

    assert created["id"] == "account-1"


def test_empty_payload_is_left_to_the_server(espo, fake):
    """Nothing to validate: the server's message is more useful than a guess."""
    result = espo.create_record("Account", {})

    assert result["error"] == "validation_failed"
    assert {problem["field"] for problem in result["problems"]} == {"name"}


@pytest.mark.parametrize("value", [None, "texto", []])
def test_non_dict_payload_is_ignored(espo, fake, value):
    assert espo._validate_payload("Account", value, creating=True) is None
