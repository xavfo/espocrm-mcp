"""P1-4 — datetime normalisation with America/Guayaquil as the working zone.

Measured live on 7.5.6: only `YYYY-MM-DD HH:mm:ss` is accepted. `2026-12-01T10:00:00`,
`...Z` and `...-05:00` all answer 400 `{"field": "dateStart", "type": "valid"}`, and a
value without an offset is stored verbatim, i.e. read as UTC.

So the conversion has to happen here. A value the caller sends without an offset is
their local time — Guayaquil, UTC-5 — and sending it unchanged would put the event
five hours early in the UI.
"""
from __future__ import annotations

import json
from datetime import timedelta, timezone

TASK = {"name": "Llamar", "parentId": "acc-1", "parentType": "Account"}


def _payload(fake) -> dict:
    writes = [r for r in fake.requests if r.method in ("POST", "PUT")]
    return json.loads(writes[-1].content)


def test_naive_datetime_is_read_as_guayaquil_and_sent_as_utc(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01 10:00:00"})

    assert _payload(fake)["dateStart"] == "2026-12-01 15:00:00"


def test_iso_with_t_and_no_offset_is_accepted(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01T10:00:00"})

    assert _payload(fake)["dateStart"] == "2026-12-01 15:00:00"


def test_iso_utc_is_not_shifted(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01T10:00:00Z"})

    assert _payload(fake)["dateStart"] == "2026-12-01 10:00:00"


def test_local_offset_is_honoured(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01T10:00:00-05:00"})

    assert _payload(fake)["dateStart"] == "2026-12-01 15:00:00"


def test_foreign_offset_is_converted(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01T10:00:00+02:00"})

    assert _payload(fake)["dateStart"] == "2026-12-01 08:00:00"


def test_date_fields_are_left_alone(espo, fake):
    espo.create_record("Task", {**TASK, "dueDate": "2026-12-01"})

    assert _payload(fake)["dueDate"] == "2026-12-01"


def test_datetime_optional_fields_are_normalised(espo, fake):
    """7.5.6 types `Meeting.dateEnd` as `datetimeOptional`, not `datetime`.

    Matching only the latter let the raw ISO string reach the server, which answered
    400 `{"field": "dateEnd", "type": "valid"}` — measured live.
    """
    espo.create_record("Task", {**TASK, "dateEnd": "2026-12-01 10:00:00"})

    assert _payload(fake)["dateEnd"] == "2026-12-01 15:00:00"


def test_non_datetime_fields_are_untouched(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01 10:00:00"})

    assert _payload(fake)["name"] == "Llamar"


def test_unparseable_value_is_passed_to_the_server(espo, fake):
    """A value we cannot parse is better explained by EspoCRM than rewritten."""
    espo.create_record("Task", {**TASK, "dateStart": "el martes"})

    assert _payload(fake)["dateStart"] == "el martes"


def test_empty_value_is_untouched(espo, fake):
    espo.create_record("Task", {**TASK, "dateStart": "   "})

    assert _payload(fake)["dateStart"] == "   "


def test_event_fields_are_normalised_without_metadata(espo, fake):
    """`Call` is unknown to the metadata here, so the name fallback applies."""
    espo.create_record(
        "Call",
        {"name": "Llamada", "dateStart": "2026-12-01 10:00:00", "dateEnd": "2026-12-01 11:00:00"},
    )

    payload = _payload(fake)
    assert payload["dateStart"] == "2026-12-01 15:00:00"
    assert payload["dateEnd"] == "2026-12-01 16:00:00"


def test_custom_datetime_field_without_metadata_is_not_guessed(espo, fake):
    """Guessing would shift values silently; the server answers instead."""
    espo.create_record(
        "Call",
        {
            "name": "Llamada",
            "dateStart": "2026-12-01 10:00:00",
            "dateEnd": "2026-12-01 11:00:00",
            "fechaInicio": "2026-12-01 10:00:00",
        },
    )

    payload = _payload(fake)
    assert payload["fechaInicio"] == "2026-12-01 10:00:00"  # unknown name: untouched
    assert payload["dateStart"] == "2026-12-01 15:00:00"  # known name: normalised


def test_update_normalises_too(espo, fake):
    fake.records[("Task", "task-9")] = {"id": "task-9"}

    espo.update_record("Task", "task-9", {"dateEnd": "2026-12-01T10:00:00Z"})

    assert _payload(fake)["dateEnd"] == "2026-12-01 10:00:00"


def test_offset_is_configurable(espo, fake, monkeypatch):
    """`ESPO_UTC_OFFSET` lets another deployment pick its zone."""
    monkeypatch.setattr(espo, "INSTANCE_TZ", timezone(timedelta(hours=0)))

    espo.create_record("Task", {**TASK, "dateStart": "2026-12-01 10:00:00"})

    assert _payload(fake)["dateStart"] == "2026-12-01 10:00:00"
