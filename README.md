# espocrm-mcp

MCP server that exposes the [EspoCRM](https://www.espocrm.com/) REST API as tools for [Claude](https://claude.ai/code).

Connect any EspoCRM instance to Claude and manage records, relationships, attachments, and the activity stream — all through natural language.

---

## Tools

### CRUD

| Tool | Description |
|------|-------------|
| `list_records` | List records of any entity type with filtering, sorting, and pagination |
| `get_record` | Fetch a single record by ID |
| `create_record` | Create a new record |
| `update_record` | Update fields on an existing record |
| `delete_record` | Delete a record |

### Relationships

| Tool | Description |
|------|-------------|
| `list_related` | List records related via a named link (e.g. contacts of an account) |
| `link_records` | Link existing records via a relationship |
| `unlink_records` | Remove a relationship between two records |

### Stream

| Tool | Description |
|------|-------------|
| `get_stream` | Fetch the global activity stream or a record-specific stream |
| `create_note` | Post a note/comment to a record's activity stream |
| `subscribe` | Subscribe the current user to record updates |
| `unsubscribe` | Unsubscribe the current user from record updates |

### Attachments

| Tool | Description |
|------|-------------|
| `upload_attachment` | Upload a file (base64-encoded) and attach it to a record |
| `get_attachment_url` | Return the download URL for an attachment |

### Metadata & utilities

| Tool | Description |
|------|-------------|
| `list_entity_types` | List all entity types defined in EspoCRM |
| `get_metadata` | Fetch EspoCRM metadata (full or scoped, e.g. `entityDefs.Account`) |
| `get_current_user` | Return the profile and permissions of the current API user |
| `get_translations` | Return UI labels and translations |

---

## Requirements

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or pip
- EspoCRM instance (self-hosted or cloud) with an API key

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/przyszloscjestdzisiaj/espocrm-mcp.git
cd espocrm-mcp
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Generate an EspoCRM API key

In your EspoCRM instance: **Admin → Users → [user] → API Key → Generate**

### 4. Register the server in Claude Code

Add the following to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "espocrm": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/espocrm-mcp", "python", "server.py"],
      "env": {
        "ESPO_URL": "https://crm.yourdomain.com",
        "ESPO_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Replace `/path/to/espocrm-mcp` with the absolute path to the cloned directory.

Restart Claude Code. The `espocrm` MCP server will appear in the tool list.

---

## Usage examples

Once connected, you can ask Claude:

> "Show me all open opportunities over $10k"

> "Create a task for Acme account: follow up on the proposal, due next Friday"

> "Add a note to the John Smith contact: called to discuss renewal, very interested"

> "List all contacts at Acme Corp with their email addresses"

> "What's in the activity stream for deal ID abc123?"

---

## Configuration reference

| Environment variable | Required | Description |
|----------------------|----------|-------------|
| `ESPO_URL` | Yes | Full URL of your EspoCRM instance, e.g. `https://crm.example.com` |
| `ESPO_API_KEY` | Yes | API key generated in EspoCRM Admin panel |

---

## Filtering (list_records)

The `where` parameter accepts a list of filter objects following the [EspoCRM search API](https://docs.espocrm.com/development/api-search-params/):

```json
[
  {"type": "equals", "attribute": "stage", "value": "Closed Won"},
  {"type": "greaterThan", "attribute": "amount", "value": 10000}
]
```

Common filter types: `equals`, `notEquals`, `contains`, `startsWith`, `greaterThan`, `lessThan`, `isNull`, `isNotNull`, `in`, `notIn`, `linkedWith`, `today`, `past`, `future`.

---

## License

MIT
