"""P1-7 — to-one relationships, measured before being "normalised".

The guide says `GET /{Entity}/{id}/{link}` returns an object for a to-one link, not a
`{list}`. On the instance that is **not** what happens: `belongsTo` (`assignedUser`)
and `hasOne` (`originalLead`) both answer with the same `{total, list}` envelope as a
to-many link. So the shape needs no correction.

What *is* broken is `belongsToParent`: listing it answers **500 Internal Server
Error** on every Task tried, while the parent record is readable through the
`parentType`/`parentId` fields. That is what this fixes.
"""
from __future__ import annotations


def test_belongs_to_parent_is_resolved_through_its_fields(espo, fake):
    fake.records[("Task", "task-1")] = {
        "id": "task-1",
        "parentType": "Contact",
        "parentId": "con-1",
    }
    fake.records[("Contact", "con-1")] = {"id": "con-1", "name": "Ana"}

    result = espo.list_related("Task", "task-1", "parent")

    assert result["total"] == 1
    assert result["list"][0]["id"] == "con-1"
    assert result["resolvedVia"] == "parentId"


def test_belongs_to_parent_without_a_parent_is_empty(espo, fake):
    fake.records[("Task", "task-2")] = {"id": "task-2", "parentType": None, "parentId": None}

    result = espo.list_related("Task", "task-2", "parent")

    assert result == {"total": 0, "list": [], "resolvedVia": "parentId"}


def test_belongs_to_parent_forwards_select(espo, fake):
    fake.records[("Task", "task-1")] = {
        "id": "task-1",
        "parentType": "Contact",
        "parentId": "con-1",
    }
    fake.records[("Contact", "con-1")] = {"id": "con-1"}

    espo.list_related("Task", "task-1", "parent", select="id,name")

    parent_request = [r for r in fake.requests if r.url.path.endswith("/Contact/con-1")][-1]
    assert parent_request.url.params["select"] == "id,name"


def test_a_failing_to_many_link_is_not_redirected(espo, fake):
    """Only `belongsToParent` gets the workaround; a real 500 must surface."""
    fake.fail_links.add(("Account", "contacts"))

    result = espo.list_related("Account", "acc-1", "contacts")

    assert result["error"] == 500
    assert "resolvedVia" not in result


def test_a_bare_object_is_wrapped_into_the_envelope(espo, fake):
    """Defensive: if an instance does return an object, the caller sees a list."""
    fake.bare_to_one_links.add(("Account", "assignedUser"))

    result = espo.list_related("Account", "acc-1", "assignedUser")

    assert result == {"total": 1, "list": [{"id": "assignedUser-1", "name": "Objeto"}]}


def test_an_envelope_is_left_untouched(espo, fake):
    fake.links[("Account", "acc-1", "contacts")] = ["con-1"]

    result = espo.list_related("Account", "acc-1", "contacts")

    assert result == {"total": 1, "list": [{"id": "con-1"}]}


def test_unknown_links_pass_through(espo, fake):
    """No metadata for the link: nothing to normalise, nothing to guess."""
    fake.links[("Account", "acc-1", "cosas")] = ["x-1"]

    result = espo.list_related("Account", "acc-1", "cosas")

    assert result == {"total": 1, "list": [{"id": "x-1"}]}
