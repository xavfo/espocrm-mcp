# espocrm-mcp7

MCP server that exposes the [EspoCRM](https://www.espocrm.com/) REST API as tools for Claude.

Fork of [`espocrm-mcp`](https://github.com/przyszloscjestdzisiaj/espocrm-mcp) adapted and verified against **EspoCRM 7.5.x**. The package is published as `espocrm-mcp7` so it can coexist with the upstream one; the module is still `server.py`.

Ships a generated catalog of the **141 entities QMedic** defines (clinical history,
vital signs, prescriptions, billing, inventory, FHIR, WhatsApp), so the model does not
have to download the ~1 MB metadata or guess names such as `Atencion`.

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

### QMedic

| Tool | Description |
|------|-------------|
| `list_qmedic_entities` | List QMedic's entities by functional group (`clinico`, `facturacion`, `fhir`…), with label, mandatory fields and a workflow hint |
| `describe_entity` | Describe one entity: mandatory fields, closed options, datetime fields and domain links. Reads live metadata and falls back to the QMedic catalog |
| `get_patient_summary` | Read a patient's head record plus their last atenciones, signos vitales, recetas, certificados and resultados in a single call |

---

## Requirements

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or pip
- EspoCRM instance (self-hosted or cloud) with an API key

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/xavfo/espocrm-mcp.git
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

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ESPO_URL` | yes | — | Base URL of the instance, e.g. `https://crm.example.com`. A subdirectory install works: `https://host/espocrm`. |
| `ESPO_API_KEY` | yes | — | API key of the API user (`Admin → Users → [user] → API Key`). |
| `MCP_ENTITY_ALLOW` | no | empty | Comma-separated allow-list. When set, every tool rejects entities outside it **before** sending a request. |
| `ESPO_AUTO_ASSIGN` | no | `1` | Assign new `Meeting`/`Call`/`Task` records to the API user when no assignee is given. Set `0` if the role forbids the field. |
| `ESPO_UTC_OFFSET` | no | `-5` | Working offset used to convert datetimes to UTC (America/Guayaquil is UTC-5 year-round). |
| `ESPO_TIMEOUT` | no | `30` | Per-request timeout in seconds. |
| `ESPO_MAX_RETRIES` | no | `2` | Retries for `429` and, on reads only, `5xx`/transport errors. |
| `ESPO_LOG_LEVEL` | no | `INFO` | Log level; lines go to stderr, never including the API key. |
| `ESPO_METADATA_MODE` | no | `frontend` | `frontend` caches `GET /Metadata` and navigates it locally (works for non-admin users). `admin` uses the filtered `?key=` endpoint and requires an administrator. |
| `MCP_PORT` | no | `8000` | Port used with `--http`. |

Minimal deployment with a restricted surface:

```json
"env": {
  "ESPO_URL": "https://crm.example.com",
  "ESPO_API_KEY": "your-api-key-here",
  "MCP_ENTITY_ALLOW": "Account,Contact,Opportunity"
}
```

---

## Development

```powershell
pip install -e ".[dev]"      # or: uv sync --extra dev
python -m pytest             # 165 tests against a simulated EspoCRM 7.5.6
```

The suite needs no EspoCRM instance: `tests/conftest.py` swaps the HTTP client for a
simulator that reproduces the 7.5.6 quirks. These scripts do talk to a real instance,
and `live_acceptance.py` writes (and deletes) records tagged `MCPTEST-*`:

```powershell
python scripts/live_check.py        # read-only probes
python scripts/live_acceptance.py   # end-to-end, cleans up after itself
```

Detailed installation steps, the measured 7.5.6 behaviour and every adaptation made
are in [`docs/DESARROLLO-7.5.6.md`](docs/DESARROLLO-7.5.6.md); §10 is the
installation guide and §11 covers the QMedic catalog.

---

## QMedic entities

QMedic is EspoCRM plus 141 custom entities. The generic CRUD tools already reach all
of them; what was missing was knowing *which* ones exist, what they are called in the
UI and which fields they demand. `qmedic_catalog.py` answers that offline.

| Group | What it covers |
|-------|----------------|
| `clinico` | Patient (`Contact`), `Atencion`, `SignosVitales`, diagnoses, certificates, consents |
| `especialidad` | Optometry, dentistry, nutrition, mental health, vaccines, obstetrics |
| `recetas` | `Receta` / `RecetaProducto` and the alternate prescription model |
| `facturacion` | Invoices, quotes, prices, taxes, payments |
| `inventario` | Products, suppliers, stock movements |
| `contabilidad` | Chart of accounts (`ChartClass` → `ChartTypes` → `ChartMaster`), journals |
| `comercial` | Accounts, agreements, insurers, branches |
| `comunicaciones` | WhatsApp messaging |
| `fhir` | FHIR mapping engine |
| `actividad` | Meetings (`Meeting` is labelled «Consulta»), calls, tasks |
| `administracion` | Users, teams, employees, reports |

Typical flow for a clinical request:

```text
get_patient_summary(contact_id)      -> patient head + last records per section
describe_entity("Atencion")          -> mandatory fields, enums, links, datetimes
list_records("Atencion", where=[…])  -> filter by pacienteId, estado, fechaIngreso…
```

The catalog is **generated**, never edited by hand. Regenerate it whenever QMedic's
metadata changes, and `--check` fails if the committed copy is stale:

```powershell
python scripts/generate_qmedic_catalog.py            # rewrite qmedic_catalog.py
python scripts/generate_qmedic_catalog.py --check    # CI-style verification
```

It reads `custom/Espo/Custom/Resources` from a sibling `qmedic-v4` checkout by
default; set `QMEDIC_METADATA` to point elsewhere. The instance's live metadata always
wins over the catalog: the catalog is a map, not an authority.

---

## Usage examples

Once connected, you can ask Claude:

> "Show me all open opportunities over $10k"

> "What did we do for patient 0102030405 in their last visit?"

> "Create a task for Acme account: follow up on the proposal, due next Friday"

> "Add a note to the John Smith contact: called to discuss renewal, very interested"

> "List all contacts at Acme Corp with their email addresses"

> "Which fields does an Atencion require, and what values does `estado` accept?"

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
