#!/usr/bin/env python3
"""EspoCRM MCP server — exposes EspoCRM REST API as MCP tools for Claude."""
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from qmedic_catalog import (
    QMEDIC_ENTITIES,
    QMEDIC_GROUPS,
    QMEDIC_WORKFLOW,
    describe_catalog_entry,
    entities_in_group,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ESPO_URL = os.environ.get("ESPO_URL", "").rstrip("/")
ESPO_API_KEY = os.environ.get("ESPO_API_KEY", "")
ESPO_TIMEOUT = float(os.environ.get("ESPO_TIMEOUT", "30"))
ESPO_MAX_RETRIES = int(os.environ.get("ESPO_MAX_RETRIES", "2"))
# Tests set this to 0; a real deployment wants a pause between attempts.
RETRY_BACKOFF_SECONDS = float(os.environ.get("ESPO_RETRY_BACKOFF", "0.5"))

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

# stderr on purpose: stdout carries the MCP protocol when the transport is stdio.
logger = logging.getLogger("espocrm")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(os.environ.get("ESPO_LOG_LEVEL", "INFO").upper())

_client = httpx.Client(
    base_url=f"{ESPO_URL}/api/v1",
    headers={"X-Api-Key": ESPO_API_KEY, "Content-Type": "application/json"},
    timeout=ESPO_TIMEOUT,
)

# 429 means the request was refused, so retrying is always safe. A 5xx on a write may
# have created the record, so only GETs are retried there.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Honour `Retry-After` when present, otherwise back off exponentially."""
    if response is not None:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return max(0.0, float(header))
            except ValueError:
                pass
    return RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))


def _req(method: str, path: str, **kwargs) -> Any:
    """Call the API, logging method, route, status and duration — never the key.

    Retries `429` always and `5xx`/transport failures only for `GET`: a failed write
    may already have created the record, and duplicating a patient's appointment is
    worse than surfacing the error.
    """
    attempt = 0
    while True:
        started = time.perf_counter()
        try:
            response = _client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            if method == "GET" and attempt < ESPO_MAX_RETRIES:
                attempt += 1
                logger.warning(
                    "%s %s transport error (%s), retry %d/%d",
                    method, path, type(exc).__name__, attempt, ESPO_MAX_RETRIES,
                )
                time.sleep(_retry_delay(None, attempt))
                continue
            logger.error("%s %s failed: %s", method, path, exc)
            return {"error": "transport", "message": str(exc), "path": path}

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("%s %s -> %s (%.0f ms)", method, path, response.status_code, elapsed_ms)

        retryable = response.status_code in RETRYABLE_STATUSES and (
            response.status_code == 429 or method == "GET"
        )
        if retryable and attempt < ESPO_MAX_RETRIES:
            attempt += 1
            delay = _retry_delay(response, attempt)
            logger.warning(
                "%s %s -> %s, retry %d/%d in %.2fs",
                method, path, response.status_code, attempt, ESPO_MAX_RETRIES, delay,
            )
            time.sleep(delay)
            continue

        return _decode(response)


def _decode(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        return _error_result(response)
    if not response.text:
        return {"ok": True}
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:2000]}


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

# QMedic defines over 140 entities of its own (clinical, billing, FHIR, WhatsApp...).
# The catalog supplies their mandatory fields and closed options so pre-validation
# keeps working when `GET /Metadata` fails or the entity is not in the cached
# metadata yet. It does not replace the instance: `_required_fields` and
# `_validate_payload` always prefer what the metadata says.
for _entity_name, _catalog_entry in QMEDIC_ENTITIES.items():
    _rules = ENTITY_RULES.setdefault(_entity_name, {})
    if _catalog_entry.get("required"):
        _rules.setdefault("required", list(_catalog_entry["required"]))
    for _field_name, _options in (_catalog_entry.get("enums") or {}).items():
        _rules.setdefault("enums", {}).setdefault(_field_name, list(_options))

# 7.5.6 fills `assignedUser` with the API user when the role forbids assigning, so
# a missing value is not necessarily a 400. The server does *not* fill it when the
# role allows assigning (measured: `Meeting` without it answers 400
# `{"field": "assignedUser", "type": "required"}`), so P1-3 injects the API user.
REQUIRED_EXEMPT = {"assignedUser", "assignedUserId"}

AUTO_ASSIGN_ENTITIES = {"Meeting", "Call", "Task"}
AUTO_ASSIGN = os.environ.get("ESPO_AUTO_ASSIGN", "1").lower() not in {"0", "false", "no"}

_current_user_cache: dict[str, Any] | None = None


def _current_user() -> dict[str, Any]:
    """The API user's profile from `GET /App/user`, fetched once per process.

    The payload nests the profile under `user` (alongside `acl`, `settings` and
    `preferences`), which is not obvious and was the first thing that broke here.
    """
    global _current_user_cache
    if _current_user_cache is None:
        data = _req("GET", "/App/user")
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
            return {}  # do not cache failures
        _current_user_cache = data["user"]
    return _current_user_cache


def _with_default_assignee(entity: str, data: Any) -> Any:
    """Assign new `Meeting`/`Call`/`Task` records to the API user when nobody is set."""
    if not AUTO_ASSIGN or entity not in AUTO_ASSIGN_ENTITIES or not isinstance(data, dict):
        return data
    if "assignedUserId" in data or "assignedUser" in data:
        return data
    user_id = _current_user().get("id")
    return {**data, "assignedUserId": user_id} if user_id else data


def _assignment_forbidden(result: Any) -> bool:
    """True when the server rejected the payload because of `assignedUser`."""
    if not isinstance(result, dict) or result.get("error") != 403:
        return False
    return "assignedUser" in json.dumps(result.get("body"), ensure_ascii=False)


def _create_entity(entity: str, data: Any) -> Any:
    """POST a record, retrying without the injected assignee if the role forbids it.

    A role that forbids the field makes the server assign the API user itself; our
    explicit value would be rejected. Nothing is created on a 403, so retrying is
    safe.
    """
    result = _req("POST", f"/{entity}", json=data)
    if isinstance(data, dict) and "assignedUserId" in data and _assignment_forbidden(result):
        return _req(
            "POST",
            f"/{entity}",
            json={k: v for k, v in data.items() if k != "assignedUserId"},
        )
    return result


# America/Guayaquil is UTC-05:00 all year round: Ecuador dropped DST after 1993, so a
# fixed offset is exact here and avoids the IANA database, which stock Windows Python
# does not ship. Override with ESPO_UTC_OFFSET if a deployment needs another zone.
UTC_OFFSET_HOURS = float(os.environ.get("ESPO_UTC_OFFSET", "-5"))
INSTANCE_TZ = timezone(timedelta(hours=UTC_OFFSET_HOURS))

# Used only when the metadata cannot say which fields are datetime-typed.
DATETIME_FALLBACK_FIELDS = {"dateStart", "dateEnd"}


def _to_utc_string(value: Any) -> Any:
    """Render a caller-supplied datetime the only way 7.5.6 accepts it.

    Measured live: `2026-12-01T10:00:00`, `...Z` and `...-05:00` all answer 400
    `{"field": "dateStart", "type": "valid"}`; only `YYYY-MM-DD HH:mm:ss` works.
    A value without an offset is read as local time in the instance's zone (UTC-5 by
    default) and shifted to UTC, which is what the UI expects — sending it untouched
    would show the event five hours early.
    """
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value  # let the server explain what is wrong with it
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=INSTANCE_TZ)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_dates(entity: str, data: Any) -> Any:
    """Convert datetime-typed fields to UTC; `date` fields are left alone.

    The field type comes from the instance's metadata, and 7.5.6 uses two names for
    it: `datetime` and `datetimeOptional` (measured live — `Meeting.dateStart` and
    `dateEnd` are the latter, which is why matching only `datetime` silently let the
    raw ISO string through). Anything else is left untouched. Without metadata the
    well-known event fields and the QMedic catalog's datetime fields are normalised,
    so a QMedic date does not silently pass through unconverted.
    """
    if not isinstance(data, dict):
        return data
    fields = _entity_fields(entity)
    # Without metadata, the QMedic catalog knows which fields are datetimes in this
    # project (e.g. `Atencion.fechaIngreso`), so the UTC conversion does not depend
    # on `GET /Metadata` succeeding.
    fallback = DATETIME_FALLBACK_FIELDS | set(
        (QMEDIC_ENTITIES.get(entity) or {}).get("datetimes") or ()
    )
    normalized = dict(data)
    for name, value in data.items():
        definition = fields.get(name)
        field_type = definition.get("type") if isinstance(definition, dict) else None
        is_datetime = isinstance(field_type, str) and field_type.startswith("datetime")
        if not is_datetime and not (field_type is None and name in fallback):
            continue
        normalized[name] = _to_utc_string(value)
    return normalized


# A single call cannot return more than this; over-sized requests are clamped rather
# than rejected, and the response says so. 200 keeps one page inside a sane context
# budget while still being useful.
MAX_PAGE_SIZE = 200


def _page_size(max_size: Any) -> tuple[int, dict[str, Any] | None]:
    """Clamp `max_size` to a usable range and describe the clamp when it applies."""
    try:
        requested = int(max_size)
    except (TypeError, ValueError):
        requested = 50
    applied = max(1, min(requested, MAX_PAGE_SIZE))
    note = None
    if applied != requested:
        note = {"requested": requested, "applied": applied, "max": MAX_PAGE_SIZE}
    return applied, note


def _with_page_note(result: Any, note: dict[str, Any] | None) -> Any:
    """Tell the caller the page was capped, without touching error payloads."""
    if note and isinstance(result, dict) and "error" not in result:
        return {**result, "pageSizeCapped": note}
    return result


def _encode_where(prefix: str, value: Any, params: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _encode_where(f"{prefix}[{key}]", item, params)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _encode_where(f"{prefix}[{index}]", item, params)
    elif value is None:
        return
    elif isinstance(value, bool):
        params[prefix] = "1" if value else "0"
    else:
        params[prefix] = str(value)


def _where_params(where: Any) -> dict[str, str]:
    """Encode a filter list the way EspoCRM actually reads it.

    7.5.6 builds `where` from the query as a PHP array. The documented JSON-string
    form is *silently ignored*: measured live, filtering on a non-existent name still
    returned all 38 accounts and an unchanged `total`. The bracketed query form
    (`where[0][type]=...`) filters correctly, including by `id`.

    Nested groups are encoded one level at a time, so `{"type": "or", "value": [...]}`
    becomes `where[0][value][0][...]`.
    """
    params: dict[str, str] = {}
    if isinstance(where, list) and where:
        _encode_where("where", where, params)
    return params


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


# Link types that address a single record. Measured live: 7.5.6 answers with the same
# `{total, list}` envelope for `belongsTo` and `hasOne`, but `belongsToParent` fails.
LINK_TO_ONE_TYPES = {"belongsTo", "hasOne", "belongsToParent"}
LINK_FAILURE_STATUSES = {500, 501, 502, 503, 504}


def _link_type(entity: str, link: str) -> str | None:
    """The `type` of a relationship link according to the instance's metadata."""
    md = _fetch_metadata()
    if not isinstance(md, dict) or "error" in md:
        return None
    links = _navigate(md, f"entityDefs.{entity}.links")
    if not isinstance(links, dict):
        return None
    definition = links.get(link)
    return definition.get("type") if isinstance(definition, dict) else None


def _normalize_link_payload(result: Any, link_type: str | None) -> Any:
    """Give a to-one link the same `{total, list}` shape as a to-many one.

    The note in the guide claims a to-one link returns a bare object; on the instance
    it returns the same envelope, so this only rewrites what an instance might still
    send — a defensive normalisation, not a correction of observed behaviour.
    """
    if link_type not in LINK_TO_ONE_TYPES:
        return result
    if isinstance(result, dict) and "error" not in result and "list" not in result:
        return {"total": 0, "list": []} if not result else {"total": 1, "list": [result]}
    return result


def _resolve_parent(entity: str, record_id: str, select: str | None = None) -> Any:
    """Read a `belongsToParent` link through its `parentType`/`parentId` fields.

    Listing that link answers 500 Internal Server Error on 7.5.6 (measured on every
    Task tried), while the parent record itself is perfectly readable.
    """
    record = _req("GET", f"/{entity}/{record_id}")
    if not isinstance(record, dict) or "error" in record:
        return record
    parent_type, parent_id = record.get("parentType"), record.get("parentId")
    if not parent_type or not parent_id:
        return {"total": 0, "list": [], "resolvedVia": "parentId"}
    params = {"select": select} if select else None
    parent = _req("GET", f"/{parent_type}/{parent_id}", params=params)
    if isinstance(parent, dict) and "error" in parent:
        return parent
    return {"total": 1, "list": [parent], "resolvedVia": "parentId"}


# The server targets one major line; anything else is still allowed but announced.
EXPECTED_VERSION_PREFIX = "7.5."
_version_warned = False


def _compatibility(version: Any) -> dict[str, Any]:
    """Describe whether the instance matches the version this server was written for."""
    global _version_warned
    text = str(version or "")
    compatible = text.startswith(EXPECTED_VERSION_PREFIX)
    if text and not compatible and not _version_warned:
        logger.warning(
            "EspoCRM %s detected; this server targets %sx", text, EXPECTED_VERSION_PREFIX
        )
        _version_warned = True
    return {
        "version": text or None,
        "expected": f"{EXPECTED_VERSION_PREFIX}x",
        "compatible": compatible,
    }


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
            # A linkMultiple is sent as `{field}Ids`, not as `{field}Id`.
            and f"{name}Ids" not in data
        ]
        problems.extend({"field": name, "type": "required"} for name in missing)

    if not problems:
        return None
    # Say where the rules came from: a catalog-based rejection on an instance whose
    # metadata did not answer is a hint, not a measurement.
    if fields:
        source = "metadata"
    elif entity in QMEDIC_ENTITIES:
        source = "catalog"
    else:
        source = "builtin"
    return {
        "error": "validation_failed",
        "message": f"EspoCRM would reject this {entity} payload; nothing was sent.",
        "entity": entity,
        "rulesSource": source,
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
        max_size: Maximum number of records to return (default 50, capped at 200).
    """
    params: dict[str, Any] = {"offset": offset, "maxSize": max_size, "order": order}
    if order_by:
        params["orderBy"] = order_by
    if select:
        params["select"] = select
    if where:
        params.update(_where_params(where))
    denied = _entity_guard(entity)
    if denied:
        return denied
    page_size, note = _page_size(max_size)
    params["maxSize"] = page_size
    return _with_page_note(_req("GET", f"/{entity}", params=params), note)


@mcp.tool()
def get_record(entity: str, record_id: str, select: str | None = None) -> Any:
    """Fetch a single record by its ID.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
        select:    Comma-separated list of fields to return, to avoid huge payloads.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    if select:
        return _read_selected(entity, record_id, select)
    return _req("GET", f"/{entity}/{record_id}")


def _read_selected(entity: str, record_id: str, select: str) -> Any:
    """Read one record carrying only the requested fields.

    7.5.6 ignores `select` on `GET /{Entity}/{id}` (measured live: `?select=id,name`
    still returned all 58 fields), while the list endpoint honours it. So the request
    goes through the collection with a filter on `id` and the single row is unwrapped,
    which keeps the return shape the caller expects.
    """
    where = [{"type": "equals", "attribute": "id", "value": record_id}]
    result = _req(
        "GET",
        f"/{entity}",
        params={"select": select, "maxSize": 1, **_where_params(where)},
    )
    if isinstance(result, dict) and "error" in result:
        return result
    rows = result.get("list") if isinstance(result, dict) else None
    if not rows:
        return {
            "error": 404,
            "message": f"{entity} {record_id} not found.",
            "data": {"id": record_id},
        }
    return rows[0]


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
    data = _normalize_dates(entity, data)
    data = _with_default_assignee(entity, data)
    invalid = _validate_payload(entity, data, creating=True)
    if invalid:
        return invalid
    return _create_entity(entity, data)


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
    data = _normalize_dates(entity, data)
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
    select: str | None = None,
    max_size: int = 50,
    offset: int = 0,
) -> Any:
    """List records related to a record via a named relationship link.

    Args:
        entity:    EspoCRM entity name, e.g. Account.
        record_id: Parent record ID.
        link:      Relationship link name, e.g. "contacts", "opportunities".
        select:    Comma-separated list of fields to return, to avoid huge payloads.
        max_size:  Maximum number of records to return (capped at 200).
        offset:    Pagination offset.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied
    page_size, note = _page_size(max_size)
    params: dict[str, Any] = {"maxSize": page_size, "offset": offset}
    if select:
        params["select"] = select
    link_type = _link_type(entity, link)
    result = _req("GET", f"/{entity}/{record_id}/{link}", params=params)
    if (
        link_type == "belongsToParent"
        and isinstance(result, dict)
        and result.get("error") in LINK_FAILURE_STATUSES
    ):
        # 7.5.6 cannot list that link; the parent is still reachable through its fields.
        result = _resolve_parent(entity, record_id, select)
    return _with_page_note(_normalize_link_payload(result, link_type), note)


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
        max_size:  Maximum number of stream entries to return (capped at 200).
    """
    if bool(entity) != bool(record_id):
        return {"error": "Provide both entity and record_id, or neither for the global stream."}
    if entity:
        denied = _entity_guard(entity)
        if denied:
            return denied
    page_size, note = _page_size(max_size)
    path = f"/{entity}/{record_id}/stream" if entity else "/Stream"
    return _with_page_note(
        _req("GET", path, params={"offset": offset, "maxSize": page_size}), note
    )


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
# QMedic catalog tools
# ---------------------------------------------------------------------------
# The CRUD tools already reach any entity; what was missing was knowing which ones
# exist in QMedic, what they are called in the UI and which fields they demand. The
# catalog is static (generated from the project's metadata) and live metadata wins
# whenever it is available.

def _field_summary(definition: Any) -> dict[str, Any]:
    """What a caller needs to know about a field to build a valid payload."""
    if not isinstance(definition, dict):
        return {}
    item: dict[str, Any] = {}
    for key in ("type", "required", "readOnly", "default"):
        if definition.get(key) not in (None, False):
            item[key] = definition[key]
    options = definition.get("options")
    if isinstance(options, list) and options:
        item["options"] = options
    return item


def _entity_links(definition: Any) -> dict[str, str]:
    """Domain links: name -> target entity, without EspoCRM's own plumbing."""
    links = definition.get("links") if isinstance(definition, dict) else None
    if not isinstance(links, dict):
        return {}
    result: dict[str, str] = {}
    for name, link in links.items():
        if name in ("createdBy", "modifiedBy", "assignedUser", "teams"):
            continue
        target = link.get("entity") if isinstance(link, dict) else None
        if isinstance(target, str) and target:
            result[name] = target
    return result


@mcp.tool()
def list_qmedic_entities(group: str | None = None, query: str | None = None) -> Any:
    """List the entities QMedic defines, grouped by functional area.

    QMedic ships 141 entities on top of EspoCRM. Without this map the model has to
    download the ~1 MB metadata or guess names like `Atencion`, `SignosVitales` or
    `RecetaProducto`. Each group also carries a one-paragraph workflow hint saying
    where to start reading.

    Args:
        group: Optional group key, e.g. "clinico", "facturacion", "comunicaciones".
        query: Optional case-insensitive filter on entity name or UI label.
    """
    if group and group not in QMEDIC_GROUPS:
        return {
            "error": "unknown_group",
            "message": f"'{group}' is not a QMedic group.",
            "groups": sorted(QMEDIC_GROUPS),
        }

    names = entities_in_group(group) if group else sorted(QMEDIC_ENTITIES)
    if query:
        needle = query.casefold()
        names = [
            name
            for name in names
            if needle in name.casefold()
            or needle in str(QMEDIC_ENTITIES[name].get("label", name)).casefold()
        ]

    entries = []
    for name in names:
        entry = QMEDIC_ENTITIES[name]
        item: dict[str, Any] = {"entity": name, "label": entry.get("label", name)}
        if not group:
            item["group"] = entry.get("group")
        if entry.get("required"):
            item["required"] = entry["required"]
        if entry.get("status"):
            item["status"] = entry["status"]
        entries.append(item)

    if group:
        return {
            "group": group,
            "description": QMEDIC_GROUPS[group],
            "workflow": QMEDIC_WORKFLOW.get(group),
            "total": len(entries),
            "entities": entries,
            "hint": "Use describe_entity(name) for fields, options and links.",
        }
    return {
        "total": len(entries),
        "groups": {
            key: {
                "description": QMEDIC_GROUPS[key],
                "count": len(entities_in_group(key)),
            }
            for key in QMEDIC_GROUPS
        },
        "entities": entries,
        "hint": (
            "Filter with group=... or query=...; use describe_entity(name) for the "
            "detail. list_entity_types shows what the instance exposes today."
        ),
    }


@mcp.tool()
def describe_entity(entity: str, include_all_fields: bool = False) -> Any:
    """Describe one entity: mandatory fields, closed options, dates and links.

    Reads `entityDefs.<entity>` from the instance's metadata; when that fails or the
    entity is not there yet, falls back to the QMedic catalog (and says so in
    `source`). Use it before `create_record`/`update_record` instead of guessing
    field names or enum values.

    Args:
        entity: EspoCRM entity name, e.g. "Atencion", "SignosVitales", "Invoice".
        include_all_fields: True returns every field, not just mandatory and enum
            ones. Start compact; ask for all fields only when you need them.
    """
    denied = _entity_guard(entity)
    if denied:
        return denied

    entry = describe_catalog_entry(entity)
    fields: dict[str, Any] = {}
    links: dict[str, str] = {}
    scope: dict[str, Any] = {}
    metadata_error: Any = None

    md = _fetch_metadata()
    if isinstance(md, dict) and "error" in md:
        metadata_error = md.get("error")
    else:
        definition = _navigate(md, f"entityDefs.{entity}")
        if isinstance(definition, dict):
            raw_fields = definition.get("fields")
            fields = raw_fields if isinstance(raw_fields, dict) else {}
            links = _entity_links(definition)
        found_scope = _navigate(md, f"scopes.{entity}")
        scope = found_scope if isinstance(found_scope, dict) else {}

    if not fields and entry is None:
        return {
            "error": 404,
            "message": f"'{entity}' is neither in the instance nor in the QMedic catalog.",
            "entity": entity,
            "metadataError": metadata_error,
            "hint": "Use list_qmedic_entities or list_entity_types to see valid names.",
        }

    source = "metadata" if fields else "catalog"
    rules = entry or {}
    required = [
        name
        for name in _required_fields(entity, fields, rules)
        if name not in REQUIRED_EXEMPT
    ]
    if not links:
        links = dict(rules.get("links") or {})

    selected: dict[str, Any] = {}
    for name, definition in fields.items():
        is_interesting = (
            include_all_fields
            or name in required
            or name == "name"
            or (isinstance(definition, dict)
                and (definition.get("type") in ("enum", "multiEnum")
                     or str(definition.get("type")).startswith("datetime")))
        )
        if is_interesting:
            selected[name] = _field_summary(definition)

    if not fields:
        # Without metadata the sheet comes from the catalog: enums and datetimes are
        # all it knows, and that is enough to avoid an out-of-range option or an
        # unconverted local time.
        for name, options in (rules.get("enums") or {}).items():
            selected[name] = {"type": "enum", "options": list(options)}
        for name in rules.get("datetimes") or ():
            selected[name] = {"type": "datetime"}

    result: dict[str, Any] = {
        "entity": entity,
        "label": rules.get("label", entity),
        "group": rules.get("group"),
        "source": source,
        "nameField": "name" if "name" in fields or rules.get("name") else None,
        "statusField": scope.get("statusField") or rules.get("status"),
        "stream": bool(scope.get("stream") or rules.get("stream")),
        "required": required,
        "links": links,
        "fields": selected,
    }
    if fields and not include_all_fields and len(selected) < len(fields):
        result["fieldCount"] = len(fields)
        result["note"] = (
            f"Showing {len(selected)} of {len(fields)} fields (mandatory, enums, "
            "datetimes and `name`). Pass include_all_fields=True to see them all."
        )
    if source == "catalog":
        result["note"] = (
            "The instance metadata did not return this entity; the sheet comes from "
            "the QMedic catalog and may not reflect later customisations."
        )
    if "assignedUser" in fields and fields["assignedUser"].get("required"):
        result["assignedUserNote"] = (
            "assignedUser is filled with the API user when omitted "
            "(ESPO_AUTO_ASSIGN); there is no need to send it."
        )
    return result


# Links read by the patient summary. Verified against QMedic's metadata: a link the
# instance does not define is rejected before any request is sent.
PATIENT_ENTITY = "Contact"
PATIENT_SECTIONS = (
    "atenciones",
    "signosVitales",
    "recetas",
    "certificados",
    "resultados",
)
PATIENT_SELECT = (
    "name,pacienteCedula,pacienteNacimiento,pacienteEdad,pacienteGenero,"
    "pacienteEstadoCivil,phoneNumber,emailAddress,"
    "cuentaFacturacionId,cuentaFacturacionName"
)


@mcp.tool()
def get_patient_summary(
    contact_id: str,
    max_items: int = 5,
    sections: str | None = None,
) -> Any:
    """Read a patient's clinical overview in one call (read-only).

    QMedic hangs the whole history off `Contact` («Paciente»), so answering "what is
    going on with this patient" used to take five separate calls. This one returns
    the demographic head plus the last records of each section.

    Args:
        contact_id: ID of the Contact (patient) record.
        max_items:  Records per section (default 5, capped at 200).
        sections:   Comma-separated links to read. Default: atenciones,
                    signosVitales, recetas, certificados, resultados.
    """
    denied = _entity_guard(PATIENT_ENTITY)
    if denied:
        return denied

    entry = describe_catalog_entry(PATIENT_ENTITY) or {}
    available = entry.get("links") or {}
    requested = (
        [item.strip() for item in sections.split(",") if item.strip()]
        if sections
        else list(PATIENT_SECTIONS)
    )
    unknown = [name for name in requested if name not in available]
    if unknown:
        return {
            "error": "unknown_link",
            "message": f"Contact has no such links in QMedic: {', '.join(unknown)}.",
            "allowed": sorted(available),
        }

    patient = _read_selected(PATIENT_ENTITY, contact_id, PATIENT_SELECT)
    if isinstance(patient, dict) and patient.get("error"):
        # A `select` naming fields this instance does not have must not sink the
        # summary: retry without `select` and return the full record.
        patient = _req("GET", f"/{PATIENT_ENTITY}/{contact_id}")
        if isinstance(patient, dict) and patient.get("error"):
            return patient

    page_size, note = _page_size(max_items)
    result: dict[str, Any] = {
        "patient": patient,
        "sections": {},
        "total": len(requested),
    }
    for link in requested:
        section = _req(
            "GET",
            f"/{PATIENT_ENTITY}/{contact_id}/{link}",
            params={"maxSize": page_size, "orderBy": "createdAt", "order": "desc"},
        )
        if isinstance(section, dict) and "error" in section:
            result["sections"][link] = section
            continue
        rows = section.get("list") if isinstance(section, dict) else None
        result["sections"][link] = {
            "total": section.get("total") if isinstance(section, dict) else None,
            "list": rows or [],
        }
    return _with_page_note(result, note)


# ---------------------------------------------------------------------------
# Utility tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_current_user() -> Any:
    """Return the profile and permissions of the currently authenticated API user.

    Includes a `compatibility` block: this server targets 7.5.x, so an instance on a
    different version is reported instead of failing in obscure ways later.
    """
    data = _req("GET", "/App/user")
    if not isinstance(data, dict) or "error" in data:
        return data
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    return {**data, "compatibility": _compatibility(settings.get("version"))}


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
