#!/usr/bin/env python3
"""EspoCRM MCP server — exposes EspoCRM REST API as MCP tools for Claude."""
import json
import os
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ESPO_URL = os.environ.get("ESPO_URL", "").rstrip("/")
ESPO_API_KEY = os.environ.get("ESPO_API_KEY", "")

if not ESPO_URL or not ESPO_API_KEY:
    print(
        "Error: ESPO_URL and ESPO_API_KEY environment variables must be set.\n"
        "Set them in ~/.claude/settings.json under mcpServers.espocrm.env.",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------
mcp = FastMCP("espocrm", port=int(os.environ.get("MCP_PORT", "8000")))

_client = httpx.Client(
    base_url=f"{ESPO_URL}/api/v1",
    headers={"X-Api-Key": ESPO_API_KEY, "Content-Type": "application/json"},
    timeout=30.0,
)


def _req(method: str, path: str, **kwargs) -> Any:
    r = _client.request(method, path, **kwargs)
    if r.status_code >= 400:
        return _error_result(r)
    if not r.text:
        return {"ok": True}
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:2000]}


def _error_result(response: httpx.Response) -> dict[str, Any]:
    """Shape an EspoCRM error so the model can correct itself on the next call.

    7.5.6 does not always send `message`. A validation failure, for instance, comes
    as `{"messageTranslation": {"label": "validationFailure", "data": {"field":
    "pacienteCedula", "type": "required"}}}`: the label has to be unpacked and the
    actionable detail lives in `data`. Returning only the status, as the previous
    version did, left the caller with nothing to act on.
    """
    try:
        payload: Any = response.json()
    except Exception:
        payload = response.text[:2000]

    message: str | None = None
    data: Any = None
    if isinstance(payload, dict):
        message = payload.get("message")
        data = payload.get("data")
        translation = payload.get("messageTranslation")
        if isinstance(translation, dict):
            message = message or translation.get("label") or None
            if data is None:
                data = translation.get("data")
    if not message:
        # Non-JSON errors (proxies, PHP fatals) have no payload to mine.
        message = response.reason_phrase or None

    result: dict[str, Any] = {
        "error": response.status_code,
        "message": message,
        "data": data,
        "body": payload,
    }
    if response.status_code == 409:
        result["hint"] = (
            "EspoCRM reports a duplicate. Retry with the header "
            "'X-Skip-Duplicate-Check: true' if the duplicate is intended."
        )
    return result


# ---------------------------------------------------------------------------
# Access policy and payload rules
# ---------------------------------------------------------------------------
# `MCP_ENTITY_ALLOW` is a comma-separated list of the entities this deployment is
# meant to expose (the licensed modules plus the core ones it needs). Empty means
# no restriction. It keeps the API key's reach narrower than "every scope it owns".
ENTITY_ALLOW = frozenset(
    name.strip()
    for name in os.environ.get("MCP_ENTITY_ALLOW", "").split(",")
    if name.strip()
)

# Fallback hints used only when the instance's metadata does not know the entity.
# These are ported from 7.5.6 and deliberately incomplete: the instance is the
# authority, because a customization can add mandatory fields (measured live:
# `Account.tipoIdentificacion` and `Contact.pacienteCedula`) or rename enum options.
ENTITY_RULES: dict[str, dict[str, Any]] = {
    "Meeting": {
        "required": ["name", "dateStart", "dateEnd", "assignedUserId"],
        "enums": {"status": ["Planned", "Held", "Not Held"]},
    },
    "Call": {
        "required": ["name", "dateStart", "dateEnd", "assignedUserId"],
        "enums": {
            "status": ["Planned", "Held", "Not Held"],
            "direction": ["Outbound", "Inbound"],
        },
    },
    "Task": {
        "required": ["name", "assignedUserId"],
        "enums": {
            "status": ["Not Started", "Started", "Completed", "Canceled", "Deferred"],
            "priority": ["Low", "Normal", "High", "Urgent"],
        },
    },
    "Opportunity": {
        "required": ["name", "accountId", "stage", "closeDate", "amount"],
        "enums": {
            "stage": [
                "Prospecting",
                "Qualification",
                "Proposal",
                "Negotiation",
                "Closed Won",
                "Closed Lost",
            ],
        },
    },
    "Case": {"enums": {"type": ["Question", "Incident", "Problem"]}},
    "User": {
        "enums": {
            "type": ["regular", "admin", "portal", "system", "super-admin", "api"],
        },
    },
}

# 7.5.6 fills `assignedUser` with the API user when the role forbids assigning, so
# a missing value is not necessarily a 400. P1-3 will handle the rest.
REQUIRED_EXEMPT = {"assignedUser", "assignedUserId"}


def _entity_guard(entity: str) -> dict[str, Any] | None:
    """Reject entities outside `MCP_ENTITY_ALLOW`, before any request is sent."""
    if ENTITY_ALLOW and entity not in ENTITY_ALLOW:
        return {
            "error": "entity_not_allowed",
            "message": f"'{entity}' is not in MCP_ENTITY_ALLOW.",
            "entity": entity,
            "allowed": sorted(ENTITY_ALLOW),
        }
    return None


def _entity_fields(entity: str) -> dict[str, Any]:
    """`entityDefs.<entity>.fields` from the cached metadata, or {} if unknown."""
    md = _fetch_metadata()
    if not isinstance(md, dict) or "error" in md:
        return {}
    fields = _navigate(md, f"entityDefs.{entity}.fields")
    return fields if isinstance(fields, dict) else {}


def _required_fields(entity: str, fields: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    if fields:
        # Metadata wins. A field with a default is filled by the server, so demanding
        # it would be a false positive (e.g. `Account.tipoIdentificacion` -> "05").
        return [
            name
            for name, definition in fields.items()
            if isinstance(definition, dict)
            and definition.get("required")
            and definition.get("default") is None
        ]
    return list(rules.get("required") or [])


def _validate_payload(
    entity: str, data: Any, *, creating: bool
) -> dict[str, Any] | None:
    """Report payloads EspoCRM would refuse, before spending a round trip.

    Only two classes of mistake are checked, both unambiguous: a value outside a
    closed enum, and a missing mandatory field. Anything subtler is left to the
    server, whose error is now actionable thanks to P0-5.
    """
    if not isinstance(data, dict):
        return None

    fields = _entity_fields(entity)
    rules = ENTITY_RULES.get(entity, {})
    problems: list[dict[str, Any]] = []

    for name, value in data.items():
        definition = fields.get(name)
        if isinstance(definition, dict):
            field_type = definition.get("type")
            options = definition.get("options")
        else:
            options = (rules.get("enums") or {}).get(name)
            field_type = "enum" if options else None
        if field_type not in ("enum", "multiEnum") or not isinstance(options, list) or not options:
            continue
        values = value if isinstance(value, list) else [value]
        unknown = [item for item in values if item not in options]
        if unknown:
            problems.append(
                {"field": name, "type": "invalidOption", "value": value, "allowed": options}
            )

    if creating:
        missing = [
            name
            for name in _required_fields(entity, fields, rules)
            if name not in REQUIRED_EXEMPT
            and name not in data
            and f"{name}Id" not in data
        ]
        problems.extend({"field": name, "type": "required"} for name in missing)

    if not problems:
        return None
    return {
        "error": "validation_failed",
        "message": f"EspoCRM would reject this {entity} payload; nothing was sent.",
        "entity": entity,
        "problems": problems,
    }


# ---------------------------------------------------------------------------
# CRUD tools — work for any EspoCRM entity type
# ---------------------------------------------------------------------------

@mcp.tool()
def list_records(
    entity: str,
    where: list | None = None,
    select: str | None = None,
    order_by: str | None = None,
    order: str = "desc",
    offset: int = 0,
    max_size: int = 50,
) -> Any:
    """List records of any entity type.

    Args:
        entity:   EspoCRM entity name, e.g. Account, Contact, Opportunity, Task.
        where:    List of filter dicts, e.g. [{"type":"equals","attribute":"stage","value":"Closed Won"}].
        select:   Comma-separated list of fields to return.
        order_by: Field name to sort by.
        order:    Sort direction — "asc" or "desc".
        offset:   Pagination offset.
        max_size: Maximum number of records to return (default 50).
    """
    params: dict[str, Any] = {"offset": offset, "maxSize": max_size, "order": order}
    if order_by:
        params["orderBy"] = order_by
    if select:
        params["select"] = select
    if where:
        params["where"] = json.dumps(where)
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("GET", f"/{entity}", params=params)


@mcp.tool()
def get_record(entity: str, record_id: str) -> Any:
    """Fetch a single record by its ID.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("GET", f"/{entity}/{record_id}")


@mcp.tool()
def create_record(entity: str, data: dict) -> Any:
    """Create a new record.

    Args:
        entity: EspoCRM entity name.
        data:   Field values, e.g. {"name": "Acme", "website": "acme.com"}.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    invalid = _validate_payload(entity, data, creating=True)
    if invalid:
        return invalid
    return _req("POST", f"/{entity}", json=data)


@mcp.tool()
def update_record(entity: str, record_id: str, data: dict) -> Any:
    """Update fields on an existing record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
        data:      Fields to update.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    invalid = _validate_payload(entity, data, creating=False)
    if invalid:
        return invalid
    return _req("PUT", f"/{entity}/{record_id}", json=data)


@mcp.tool()
def delete_record(entity: str, record_id: str) -> Any:
    """Delete a record by its ID.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("DELETE", f"/{entity}/{record_id}")


# ---------------------------------------------------------------------------
# Relationship tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_related(
    entity: str,
    record_id: str,
    link: str,
    max_size: int = 50,
    offset: int = 0,
) -> Any:
    """List records related to a record via a named relationship link.

    Args:
        entity:    EspoCRM entity name, e.g. Account.
        record_id: Parent record ID.
        link:      Relationship link name, e.g. "contacts", "opportunities".
        max_size:  Maximum number of records to return.
        offset:    Pagination offset.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req(
        "GET",
        f"/{entity}/{record_id}/{link}",
        params={"maxSize": max_size, "offset": offset},
    )


@mcp.tool()
def link_records(entity: str, record_id: str, link: str, target_ids: list[str]) -> Any:
    """Link existing records to a record via a relationship.

    Args:
        entity:     EspoCRM entity name.
        record_id:  Parent record ID.
        link:       Relationship link name.
        target_ids: List of IDs to link.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("POST", f"/{entity}/{record_id}/{link}", json={"ids": target_ids})


@mcp.tool()
def unlink_records(entity: str, record_id: str, link: str, target_id: str) -> Any:
    """Remove a relationship between two records.

    The ID goes in the JSON body: on EspoCRM 7.5.6 `POST`/`DELETE /{Entity}/{id}/{link}`
    read `id`/`ids` from the parsed body only, so a query-string `?id=` is ignored and
    the call silently returns `false`.

    Args:
        entity:    EspoCRM entity name.
        record_id: Parent record ID.
        link:      Relationship link name.
        target_id: ID of the record to unlink.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("DELETE", f"/{entity}/{record_id}/{link}", json={"ids": [target_id]})


# ---------------------------------------------------------------------------
# Stream tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_stream(
    entity: str | None = None,
    record_id: str | None = None,
    offset: int = 0,
    max_size: int = 50,
) -> Any:
    """Fetch the activity stream — either the global user stream or a record-specific stream.

    Args:
        entity:    Entity name (required when fetching a record stream, e.g. "Account").
        record_id: Record ID (required when fetching a record stream).
        offset:    Pagination offset.
        max_size:  Maximum number of stream entries to return.
    """
    if bool(entity) != bool(record_id):
        return {"error": "Provide both entity and record_id, or neither for the global stream."}
    if entity:
        denied = _entity_guard(entity)
        if denied:
            return denied
    path = f"/{entity}/{record_id}/stream" if entity else "/Stream"
    return _req("GET", path, params={"offset": offset, "maxSize": max_size})


@mcp.tool()
def create_note(
    parent_type: str,
    parent_id: str,
    post: str,
    is_internal: bool = False,
    attachment_ids: list[str] | None = None,
) -> Any:
    """Post a note/comment to a record's activity stream.

    In 7.5.6 `Note.type` is `readOnly`, so it is not sent: the server sets it. The
    internal flag is a top-level boolean — `data` is a `jsonObject` and putting
    `isInternal` there has no effect, which silently produces a public note when an
    internal one was intended.

    Args:
        parent_type:    Entity type of the parent record, e.g. "Account".
        parent_id:      ID of the parent record.
        post:           Note text (Markdown supported).
        is_internal:    True to make the note visible to internal users only.
        attachment_ids: Optional list of attachment IDs to attach to the note.
    """
    data: dict[str, Any] = {
        "parentType": parent_type,
        "parentId": parent_id,
        "post": post,
        "isInternal": is_internal,
    }
    if attachment_ids:
        data["attachmentsIds"] = attachment_ids
    denied = _entity_guard(parent_type)
    if denied:
        return denied
    return _req("POST", "/Note", json=data)


@mcp.tool()
def subscribe(entity: str, record_id: str) -> Any:
    """Subscribe the current user to updates on a record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("PUT", f"/{entity}/{record_id}/subscription")


@mcp.tool()
def unsubscribe(entity: str, record_id: str) -> Any:
    """Unsubscribe the current user from updates on a record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    return _req("DELETE", f"/{entity}/{record_id}/subscription")


# ---------------------------------------------------------------------------
# Attachment tools
# ---------------------------------------------------------------------------

@mcp.tool()
def upload_attachment(
    name: str,
    mime_type: str,
    file_base64: str,
    field: str,
    related_type: str | None = None,
    related_id: str | None = None,
    parent_type: str | None = None,
    parent_id: str | None = None,
) -> Any:
    """Upload a file attachment and bind it to the field that stores it.

    EspoCRM 7.5.6 expects two different payloads depending on the field type, and
    sending the wrong one stores the file but never links it to the field:

    - `file` (e.g. `Document.file`): pass `field` plus `related_type`/`related_id`.
    - `attachmentMultiple` (e.g. `Note.attachments`): pass `field` plus
      `parent_type` (and `parent_id` when the field needs it). The final link is a
      separate `update_record` call carrying `attachmentsIds`.

    The previous version reused `relatedType` for both cases, so uploads for
    `attachmentMultiple` fields were orphaned.

    Args:
        name:         File name, e.g. "contract.pdf".
        mime_type:    MIME type, e.g. "application/pdf" or "image/png".
        file_base64:  Base64-encoded file content (standard base64, no data-URL prefix).
        field:        Field that holds the attachment, e.g. "file" or "attachments".
        related_type: Entity type owning a `file` field, e.g. "Document".
        related_id:   ID of the record owning the `file` field.
        parent_type:  Entity type owning an `attachmentMultiple` field, e.g. "Note".
        parent_id:    Parent record ID, when the field needs it.
    """
    data: dict[str, Any] = {
        "name": name,
        "type": mime_type,
        "role": "Attachment",
        "field": field,
        "file": f"data:{mime_type};base64,{file_base64}",
    }
    for owner in (related_type, parent_type):
        if owner:
            denied = _entity_guard(owner)
            if denied:
                return denied
    if related_type:
        data["relatedType"] = related_type
    if related_id:
        data["relatedId"] = related_id
    if parent_type:
        data["parentType"] = parent_type
    if parent_id:
        data["parentId"] = parent_id
    return _req("POST", "/Attachment", json=data)


@mcp.tool()
def get_attachment_url(attachment_id: str) -> dict[str, str]:
    """Return the download URL for an attachment.

    Args:
        attachment_id: ID of the Attachment record.
    """
    return {"url": f"{ESPO_URL}/api/v1/Attachment/file/{attachment_id}"}


# ---------------------------------------------------------------------------
# Metadata tools
# ---------------------------------------------------------------------------

# `GET /Metadata?key=...` requires an admin in 7.5.6, and on some instances the key
# is ignored altogether (the whole ~1 MB payload comes back whatever you ask for).
# The unparameterised endpoint is readable by any authenticated user, so the default
# is to download it once and navigate the tree locally. `ESPO_METADATA_MODE=admin`
# switches to the filtered endpoint for instances where the API user is an admin.
METADATA_MODE = os.environ.get("ESPO_METADATA_MODE", "frontend")

_metadata_cache: dict[str, Any] | None = None


def _fetch_metadata() -> Any:
    """Download the frontend metadata once per process, or return the cached copy."""
    global _metadata_cache
    if _metadata_cache is None:
        data = _req("GET", "/Metadata")
        if not isinstance(data, dict) or "error" in data:
            return data  # do not cache failures: a later call may succeed
        _metadata_cache = data
    return _metadata_cache


def _navigate(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


@mcp.tool()
def list_entity_types() -> Any:
    """Return a sorted list of all entity type names defined in EspoCRM."""
    if METADATA_MODE == "admin":
        md = _req("GET", "/Metadata", params={"key": "scopes"})
        scopes = md if isinstance(md, dict) and "error" not in md else {}
    else:
        md = _fetch_metadata()
        if not isinstance(md, dict) or "error" in md:
            return md
        scopes = md.get("scopes") or {}
    return sorted(k for k, v in scopes.items() if isinstance(v, dict) and v.get("entity"))


@mcp.tool()
def get_metadata(scope: str | None = None) -> Any:
    """Fetch EspoCRM metadata, optionally scoped to a subtree.

    Args:
        scope: Dot-separated path into the metadata tree, e.g. "entityDefs.Account".
               Omit to get an index of the available top-level sections; the full
               payload is around 1 MB and would flood the conversation.
    """
    if METADATA_MODE == "admin":
        params = {"key": scope} if scope else {}
        return _req("GET", "/Metadata", params=params)

    md = _fetch_metadata()
    if not isinstance(md, dict) or "error" in md:
        return md
    if not scope:
        return {
            "keys": sorted(md),
            "scopes": sorted(k for k, v in (md.get("scopes") or {}).items() if isinstance(v, dict) and v.get("entity")),
            "hint": 'Pass a scope such as "entityDefs.Account.fields" to read a subtree.',
        }
    value = _navigate(md, scope)
    if value is None:
        return {"error": "scope not found", "scope": scope, "keys": sorted(md)}
    return value


# ---------------------------------------------------------------------------
# Utility tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_current_user() -> Any:
    """Return the profile and permissions of the currently authenticated API user."""
    return _req("GET", "/App/user")


@mcp.tool()
def get_translations(use_default: bool = False) -> Any:
    """Return all UI labels and translations from EspoCRM.

    Args:
        use_default: If True, return the default (English) translations regardless of
                     the configured language.
    """
    params = {"default": "true"} if use_default else {}
    return _req("GET", "/I18n", params=params)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    mcp.run(transport=transport)
