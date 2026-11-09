"""P1-5 — a single call cannot return an unbounded page.

`max_size` used to go straight to EspoCRM, so one careless `max_size=10000` filled
the whole conversation with records. It is now clamped to 200 and, when the clamp
applies, the response says so instead of silently returning fewer rows than asked.
"""
from __future__ import annotations

MAX = 200


def _last_params(fake):
    return fake.requests[-1].url.params


def test_oversized_page_is_clamped(espo, fake):
    result = espo.list_records("Account", max_size=5000)

    assert _last_params(fake)["maxSize"] == str(MAX)
    assert result["pageSizeCapped"] == {"requested": 5000, "applied": MAX, "max": MAX}


def test_page_at_the_limit_is_not_flagged(espo, fake):
    result = espo.list_records("Account", max_size=MAX)

    assert _last_params(fake)["maxSize"] == str(MAX)
    assert "pageSizeCapped" not in result


def test_small_page_passes_through(espo, fake):
    result = espo.list_records("Account", max_size=10)

    assert _last_params(fake)["maxSize"] == "10"
    assert "pageSizeCapped" not in result


def test_zero_or_negative_page_is_raised_to_one(espo, fake):
    result = espo.list_records("Account", max_size=0)

    assert _last_params(fake)["maxSize"] == "1"
    assert result["pageSizeCapped"] == {"requested": 0, "applied": 1, "max": MAX}


def test_list_related_is_clamped_too(espo, fake):
    espo.list_related("Account", "acc-1", "contacts", max_size=999)

    assert _last_params(fake)["maxSize"] == str(MAX)


def test_stream_is_clamped_too(espo, fake):
    espo.get_stream("Account", "acc-1", max_size=1000)

    assert _last_params(fake)["maxSize"] == str(MAX)


def test_errors_are_not_decorated(espo, fake):
    """An error payload must stay exactly as the server sent it."""
    note = {"requested": 999, "applied": MAX, "max": MAX}
    error = {"error": 404, "message": "Not Found"}

    assert espo._with_page_note(error, note) == error
    assert espo._with_page_note("texto", note) == "texto"
    assert espo._with_page_note([], note) == []
