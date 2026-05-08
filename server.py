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
        return {"error": r.status_code, "body": r.text[:2000]}
    if not r.text:
        return {"ok": True}
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:2000]}


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
    return _req("GET", f"/{entity}", params=params)


@mcp.tool()
def get_record(entity: str, record_id: str) -> Any:
    """Fetch a single record by its ID.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    return _req("GET", f"/{entity}/{record_id}")


@mcp.tool()
def create_record(entity: str, data: dict) -> Any:
    """Create a new record.

    Args:
        entity: EspoCRM entity name.
        data:   Field values, e.g. {"name": "Acme", "website": "acme.com"}.
    """
    return _req("POST", f"/{entity}", json=data)


@mcp.tool()
def update_record(entity: str, record_id: str, data: dict) -> Any:
    """Update fields on an existing record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
        data:      Fields to update.
    """
    return _req("PUT", f"/{entity}/{record_id}", json=data)


@mcp.tool()
def delete_record(entity: str, record_id: str) -> Any:
    """Delete a record by its ID.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
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
    return _req("POST", f"/{entity}/{record_id}/{link}", json={"ids": target_ids})


@mcp.tool()
def unlink_records(entity: str, record_id: str, link: str, target_id: str) -> Any:
    """Remove a relationship between two records.

    Args:
        entity:    EspoCRM entity name.
        record_id: Parent record ID.
        link:      Relationship link name.
        target_id: ID of the record to unlink.
    """
    return _req("DELETE", f"/{entity}/{record_id}/{link}", params={"id": target_id})


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
    path = f"/{entity}/{record_id}/stream" if entity else "/Stream"
    return _req("GET", path, params={"offset": offset, "maxSize": max_size})


@mcp.tool()
def create_note(
    parent_type: str,
    parent_id: str,
    post: str,
    attachment_ids: list[str] | None = None,
) -> Any:
    """Post a note/comment to a record's activity stream.

    Args:
        parent_type:    Entity type of the parent record, e.g. "Account".
        parent_id:      ID of the parent record.
        post:           Note text (Markdown supported).
        attachment_ids: Optional list of attachment IDs to attach to the note.
    """
    data: dict[str, Any] = {
        "type": "Post",
        "parentType": parent_type,
        "parentId": parent_id,
        "post": post,
    }
    if attachment_ids:
        data["attachmentsIds"] = attachment_ids
    return _req("POST", "/Note", json=data)


@mcp.tool()
def subscribe(entity: str, record_id: str) -> Any:
    """Subscribe the current user to updates on a record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    return _req("PUT", f"/{entity}/{record_id}/subscription")


@mcp.tool()
def unsubscribe(entity: str, record_id: str) -> Any:
    """Unsubscribe the current user from updates on a record.

    Args:
        entity:    EspoCRM entity name.
        record_id: Record ID.
    """
    return _req("DELETE", f"/{entity}/{record_id}/subscription")


# ---------------------------------------------------------------------------
# Attachment tools
# ---------------------------------------------------------------------------

@mcp.tool()
def upload_attachment(
    name: str,
    mime_type: str,
    file_base64: str,
    related_type: str | None = None,
    related_id: str | None = None,
    field: str | None = None,
) -> Any:
    """Upload a file attachment.

    The file must be base64-encoded. Returns the attachment record including its ID,
    which can then be linked to an entity record.

    Args:
        name:         File name, e.g. "contract.pdf".
        mime_type:    MIME type, e.g. "application/pdf" or "image/png".
        file_base64:  Base64-encoded file content (use standard base64, no data-URL prefix).
        related_type: Entity type to attach to, e.g. "Account".
        related_id:   ID of the entity record to attach to.
        field:        Field name on the entity that holds this attachment, e.g. "attachments".
    """
    data: dict[str, Any] = {
        "name": name,
        "type": mime_type,
        "role": "Attachment",
        "file": f"data:{mime_type};base64,{file_base64}",
    }
    if related_type:
        data["relatedType"] = related_type
    if related_id:
        data["relatedId"] = related_id
    if field:
        data["field"] = field
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

@mcp.tool()
def list_entity_types() -> Any:
    """Return a sorted list of all entity type names defined in EspoCRM."""
    md = _req("GET", "/Metadata", params={"key": "scopes"})
    if isinstance(md, dict) and "error" not in md:
        return sorted(k for k, v in md.items() if isinstance(v, dict) and v.get("entity"))
    return md


@mcp.tool()
def get_metadata(scope: str | None = None) -> Any:
    """Fetch EspoCRM metadata.

    Args:
        scope: Dot-separated path into the metadata tree, e.g. "entityDefs.Account".
               Omit to retrieve the full metadata object (response will be large).
    """
    params = {"key": scope} if scope else {}
    return _req("GET", "/Metadata", params=params)


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
