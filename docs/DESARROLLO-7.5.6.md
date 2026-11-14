# Desarrollo de `espocrm-mcp7` para EspoCRM 7.5.6

**Estado:** propuesto
**Base elegida:** `espocrm-mcp` (`server.py` único, licencia MIT)
**Nombre del paquete:** `espocrm-mcp7`, versión `1.1.0` (fork que sostiene la línea 7.5.x)
**Objetivo:** que el MCP funcione de forma estable contra EspoCRM **7.5.6**, incluidos los módulos licenciados que agregan entidades y campos personalizados.
**Referencia técnica:** código fuente de `espocrm/espocrm`, etiqueta `7.5.6`, y documentación oficial de la API.
**Fecha:** 2026-11-06

---

## 1. Resumen ejecutivo

`espocrm-mcp` es la base más fácil de adaptar porque **no hardcodea enums, campos obligatorios ni esquemas de entidades**. Es un puente genérico sobre `/api/v1`, así que las entidades de los módulos licenciados funcionan sin tocar código.

La adaptación a 7.5.6 se reduce a:

1. Corregir el desvinculado (`unlink_records`), que hoy manda el `id` por query string y 7.5.6 lo lee del body.
2. Distinguir adjuntos de campos `file` y `attachmentMultiple` al subir.
3. Ajustar `create_note` a `isInternal` de primer nivel.
4. Resolver el acceso a metadata sin exigir un usuario administrador.
5. Mejorar el manejo de errores para que el LLM pueda autocorregirse.
6. Añadir una lista blanca de entidades y un mapa de reglas por entidad (opcional pero recomendado para módulos licenciados).

El resto del documento detalla cada cambio, el contrato de compatibilidad con 7.5.6, el plan de pruebas y un roadmap con mejoras tomadas de `espocrm-mcp-server` y del MCP en Node/TypeScript.

### Principios de diseño

- **Mínimo privilegio:** el API user no debe ser administrador. El CRUD, las relaciones, las notas y los adjuntos deben funcionar con permisos de entidad.
- **Sin metadatos hardcodeados:** los enums y campos obligatorios se descubren en la instancia o se documentan como pistas, no como verdad absoluta.
- **Compatible con módulos licenciados:** cualquier entidad expuesta por la API debe poder usarse con `entity` genérico.
- **Errores útiles para el LLM:** devolver `status`, `message` y `body` de EspoCRM, no solo una excepción.
- **Trazabilidad:** registrar método, ruta, estado y duración; nunca la API key.

---

## 2. Línea base validada en 7.5.6

### 2.1 Lo que ya funciona

| Funcionalidad | Evidencia en 7.5.6 |
|---|---|
| `GET/POST/PUT/PATCH/DELETE /api/v1/{Entity}` | Rutas genéricas de `application/Espo/Resources/routes.json` |
| `X-Api-Key` | Cabecera oficial de autenticación por API Key |
| `where` **en forma `where[0][type]=...`** | Medido en vivo: la forma JSON string se ignora (ver P0-6) |
| `select` como lista separada por comas | Documentado en `api/crud` |
| `maxSize` y `offset` | Documentado en `api-search-params` |
| `POST /{Entity}/{id}/{link}` con `{"ids": [...]}` | `postActionCreateLink` lee `id` e `ids` |
| `DELETE /{Entity}/{id}/{link}` con body | `deleteActionRemoveLink` lee `id`/`ids` del body |
| `POST /Note` con `parentType`/`parentId` | Campo `parent` de tipo `linkParent` |
| `POST /Attachment` con `file` data URL | Documentado en `api/attachment` |
| `PUT/DELETE /{Entity}/{id}/subscription` | Rutas de `follow`/`unfollow` |
| `GET /Stream` y `/{Entity}/{id}/stream` | Rutas de Stream |
| `GET /Settings` | Lectura disponible para usuarios autenticados |

### 2.2 Correcciones obligatorias (P0)

| ID | Problema | Archivo actual | Impacto |
|---|---|---|---|
| P0-1 | `unlink_records` envía `id` por query string | `server.py` → `unlink_records` | 7.5.6 lo ignora y devuelve `false`; no desvincula |
| P0-2 | `upload_attachment` usa `relatedType` también para `attachmentMultiple` | `server.py` → `upload_attachment` | El adjunto no queda asociado al campo correcto |
| P0-3 | `create_note` envía `type` (readOnly) y no expone `isInternal` | `server.py` → `create_note` | `type` se descarta; no se puede marcar nota interna |
| P0-4 | `get_metadata` y `list_entity_types` usan `?key=` | `server.py` → tools de metadata | `GET /Metadata?key=...` exige admin en 7.5.6 |
| P0-5 | `_req` devuelve solo `error` y `body` | `server.py` → `_req` | El LLM no ve el `message` de EspoCRM ni los detalles de validación |

---

## 3. Correcciones P0 en detalle

### P0-1 `unlink_records`: enviar el `id` en el body

**Código actual:**

```python
return _req("DELETE", f"/{entity}/{record_id}/{link}", params={"id": target_id})
```

**Comportamiento de 7.5.6:** `Record::deleteActionRemoveLink` lee `$request->getParsedBody()->id` y `->ids`. Los query params no se usan.

**Cambio propuesto:**

```python
return _req(
    "DELETE",
    f"/{entity}/{record_id}/{link}",
    json={"ids": [target_id]},
)
```

**Prueba de aceptación:** desvincular un contacto de una cuenta devuelve `true` y, al consultar `GET /Account/{id}/contacts`, el contacto ya no aparece.

**Estado:** implementado. Cubierto por `tests/test_p0_1_unlink_records.py` (5 casos, offline).

---

### P0-2 `upload_attachment`: separar `file` de `attachmentMultiple`

**Comportamiento de 7.5.6:**

- Campo tipo `file` (por ejemplo `Document.file`): `relatedType`, `relatedId`, `field`, `file` (data URL).
- Campo tipo `attachmentMultiple` (por ejemplo `Note.attachments`): `parentType`, `field`, `file` (data URL). El vínculo final se hace con `attachmentsIds`.
- `file` debe ser un data URL: `data:<mime>;base64,<contenido>`.

**Cambio propuesto:** aceptar ambos modos de forma explícita.

```python
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
    data: dict[str, Any] = {
        "name": name,
        "type": mime_type,
        "role": "Attachment",
        "field": field,
        "file": f"data:{mime_type};base64,{file_base64}",
    }
    if related_type:
        data["relatedType"] = related_type
    if related_id:
        data["relatedId"] = related_id
    if parent_type:
        data["parentType"] = parent_type
    if parent_id:
        data["parentId"] = parent_id
    return _req("POST", "/Attachment", json=data)
```

**Regla de uso:**

- `file` → `related_type` + `related_id`.
- `attachmentMultiple` → `parent_type` (+ `parent_id` si el campo lo requiere).

**Prueba de aceptación:** subir un archivo con `parent_type="Note"` y `field="attachments"` devuelve un `id`; luego `PUT /Note/{id}` con `attachmentsIds: ["<id>"]` lo asocia.

**Estado:** implementado. Cubierto por `tests/test_p0_2_upload_attachment.py` (6 casos, offline).

---

### P0-3 `create_note`: `isInternal` de primer nivel

**Comportamiento de 7.5.6:** en `Note.json`, `type` es `readOnly` y `isInternal` es un `bool` de primer nivel. `data` es `jsonObject` y no es el lugar para `isInternal`.

**Cambio propuesto:**

```python
@mcp.tool()
def create_note(
    parent_type: str,
    parent_id: str,
    post: str,
    is_internal: bool = False,
    attachment_ids: list[str] | None = None,
) -> Any:
    data: dict[str, Any] = {
        "parentType": parent_type,
        "parentId": parent_id,
        "post": post,
        "isInternal": is_internal,
    }
    if attachment_ids:
        data["attachmentsIds"] = attachment_ids
    return _req("POST", "/Note", json=data)
```

**Prueba de aceptación:** crear una nota con `is_internal=True` y verificar en `GET /Note/{id}` que `isInternal` es `true`.

**Estado:** implementado. Cubierto por `tests/test_p0_3_create_note.py` (8 casos, offline).

---

### P0-4 Metadata sin exigir administrador

**Comportamiento de 7.5.6:**

- `GET /Metadata?key=<ruta>` → `Metadata::getActionGet`, exige `isAdmin()`. Con un API user normal devuelve `403`.
- `GET /Metadata` sin `key` → `Metadata::getActionRead`, disponible para usuarios autenticados y devuelve el metadata que usa el frontend (incluye `entityDefs`).

**Cambio propuesto:** cachear el metadata de frontend y navegar la ruta solicitada.

```python
_metadata_cache: dict | None = None

def _fetch_frontend_metadata() -> dict:
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = _req("GET", "/Metadata") or {}
    return _metadata_cache

def _navigate(data: dict, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current

@mcp.tool()
def get_metadata(scope: str | None = None) -> Any:
    data = _fetch_frontend_metadata()
    if not scope:
        return data
    return _navigate(data, scope)
```

**Notas:**

- El payload puede ser grande; cachear en memoria y, si hace falta, en disco (`/tmp/espocrm-metadata.json`).
- Si el API user sí es admin y se prefiere el endpoint filtrado, habilitar un modo `ESPO_METADATA_MODE=admin` que use `?key=`.
- `list_entity_types` debe leer `scopes` del metadata cacheado y filtrar los que tengan `entity: true`.

**Prueba de aceptación:** con un API user **no admin**, `get_metadata("entityDefs.Account.fields")` devuelve el objeto de campos (200), no 403.

**Estado:** implementado. Cubierto por `tests/test_p0_4_metadata.py` (10 casos, offline) y verificado en vivo.

**Medición en `neo.qsoftware.biz/medic` (7.5.6, usuario `external`, tipo `api`):**

- `GET /Metadata` → `200`, 979 178 bytes, 1,1 s. Claves: `app`, `clientDefs`, `dashlets`, `entityAcl`, `entityDefs`, `fields`, `integrations`, `module`, `scopes`, `streamDefs`, `themes`.
- `GET /Metadata?key=<cualquiera>` → **`200`, no `403`**, y **ignora la clave**: devuelve el mismo payload completo incluso con `?key=noExiste.ruta`. Es decir, en esta instancia el supuesto del punto de partida no se reproduce.
- Con caché, la segunda consulta tarda ~0 s. `list_entity_types()` devuelve 179 entidades sobre 194 scopes.

Conclusión: no se debe depender de `?key=` ni por permisos ni por filtrado. Se implementa igual la caché y la navegación local. `get_metadata()` sin `scope` devuelve un índice compacto (`keys`, `scopes`, `hint`) en lugar del documento completo, porque volcar 979 KB en el contexto del LLM inutiliza la herramienta; esto se aparta a propósito del fragmento de código de arriba.

---

### P0-5 Errores útiles para el LLM

**Código actual:** `_req` devuelve `{"error": status, "body": texto}`.

**Mejora propuesta:**

```python
def _req(method: str, path: str, **kwargs) -> Any:
    r = _client.request(method, path, **kwargs)
    if r.status_code >= 400:
        payload: Any
        try:
            payload = r.json()
        except Exception:
            payload = r.text[:2000]
        return {
            "error": r.status_code,
            "message": payload.get("message") if isinstance(payload, dict) else None,
            "data": payload.get("data") if isinstance(payload, dict) else None,
            "body": payload,
        }
    if not r.text:
        return {"ok": True}
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:2000]}
```

**Casos especiales:**

- `409` por duplicado: incluir `data` con los registros duplicados y sugerir `X-Skip-Duplicate-Check: true`.
- `422`: mostrar los errores por campo.
- `403`: distinguir “sin permiso de scope” de “campo prohibido”.
- **Forma real del error (medida en 7.5.6):** un 400 de validación devuelve `{"messageTranslation":{"label":"validationFailure","scope":null,"data":{"field":"pacienteCedula","type":"required"}}}`. **No hay clave `message`**, así que el código propuesto arriba devolvería `message: null`. Hay que leer también `messageTranslation.label` y `messageTranslation.data.field`/`.type`.

**Prueba de aceptación:** crear un `Case` con `type: "Feature Request"` devuelve un error con el `message` de EspoCRM y el detalle de validación.

**Estado:** implementado. Cubierto por `tests/test_p0_5_errors.py` (7 casos, offline) y verificado en vivo:

| Llamada | Respuesta devuelta por el MCP |
|---|---|
| `Case` con `type: "Feature Request"` | `{"error": 400, "message": "validationFailure", "data": {"field": "type", "type": "valid"}, "body": {...}}` |
| `Contact` sin `pacienteCedula` | `{"error": 400, "message": "validationFailure", "data": {"field": "pacienteCedula", "type": "required"}}` |
| `GET` de un id inexistente | `{"error": 404, "message": "Not Found", "data": null, "body": ""}` |

Pendiente de verificar: el caso `403` que distingue “sin permiso de scope” de “campo prohibido” necesita un rol que prohiba un campo concreto; no se reprodujo en la instancia de prueba. La sugerencia de `X-Skip-Duplicate-Check` para `409` tampoco está verificada en vivo.

---

### P0-6 `where`: enviar el filtro en la forma que EspoCRM lee

**Encontrado durante P1-6**, y de la misma gravedad que los demás P0: `list_records` enviaba el filtro como JSON string, que es la forma que sugiere la documentación de `api-search-params`. **7.5.6 la ignora por completo.**

Medición en vivo:

| Petición | `total` | Registros |
|---|---|---|
| `where=[{"type":"equals","attribute":"name","value":"ZZZ_NO_EXISTE"}]` (JSON) | 38 | 5 |
| `where[0][type]=equals&where[0][attribute]=name&where[0][value]=ZZZ_NO_EXISTE` | **0** | **0** |
| `where[0][...][value]=KLEVER` (contains) | **2** | **2** |
| `where[0][attribute]=id` con id real / inexistente | 1 / 0 | 1 / 0 |

Consecuencia: cualquier filtro que pidiera el LLM se descartaba y la herramienta devolvía **todos** los registros, con un `total` que tampoco correspondía a la consulta. Es un fallo silencioso: ni error ni aviso.

**Cambio:** `_where_params` codifica la lista en forma de corchetes, con un nivel por clave (`where[0][value][0][...]` para los grupos `or`/`and`), convierte booleanos a `1`/`0` y no entrecomilla los valores.

**Estado:** implementado. Cubierto por `tests/test_p0_6_where_encoding.py` (10 casos) y verificado en vivo.

---

## 4. Correcciones recomendadas (P1)

| ID | Mejora | Motivo |
|---|---|---|
| P1-1 | Lista blanca `MCP_ENTITY_ALLOW` | Exponer solo las entidades de los módulos licenciados y evitar acceso accidental al resto |
| P1-2 | Mapa de reglas por entidad (`ENTITY_RULES`) | Evitar 400 por campos obligatorios o enums inválidos en las entidades más usadas |
| P1-3 | Asignado por defecto | En 7.5.6 `Meeting`, `Call` y `Task` requieren `assignedUser`; si no se envía, usar el usuario del API key |
| P1-4 | Normalización de fechas | Aceptar ISO con `T`/`Z` y enviar `YYYY-MM-DD HH:mm:ss` en UTC |
| P1-5 | Límite de paginación | `max_size` máximo 200; avisar si se supera |
| P1-6 | `select` en `get_record` y `list_related` | Evitar respuestas gigantes |
| P1-7 | Normalizar relaciones `to-one` | `GET /{Entity}/{id}/{link}` devuelve un objeto, no `{list}` |
| P1-8 | Timeout, reintentos y logs | `ESPO_TIMEOUT`, reintentos con backoff para `429`/`5xx`, respetar `Retry-After` |
| P1-9 | Detección de versión | Leer `settings.version` de `App/user` y avisar si no es 7.5.x |
| P1-10 | Empaquetado | Fijar versiones de `mcp`/`httpx`, añadir `LICENSE` y `.env.example` |

### P1-1 Lista blanca `MCP_ENTITY_ALLOW`

Variable de entorno con nombres de entidad separados por coma. Vacía = sin restricción. Se evalúa en todas las herramientas que nombran una entidad (CRUD, relaciones, stream, notas y adjuntos) **antes** de cualquier request, así que una entidad bloqueada no consume cuota ni deja rastro en el servidor.

```powershell
$env:MCP_ENTITY_ALLOW = "Account,Contact,Opportunity"
```

Rechazo devuelto al LLM:

```json
{"error": "entity_not_allowed", "message": "'Lead' is not in MCP_ENTITY_ALLOW.",
 "entity": "Lead", "allowed": ["Account", "Contact", "Opportunity"]}
```

**Estado:** implementado. Cubierto por `tests/test_p1_1_entity_allow.py` (17 casos, incluido uno por herramienta) y verificado en vivo.

### P1-2 Mapa de reglas sugerido (7.5.6)

```python
ENTITY_RULES = {
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
            "stage": ["Prospecting", "Qualification", "Proposal",
                      "Negotiation", "Closed Won", "Closed Lost"],
        },
        "nota": "probability se autocalcula desde stage en 7.5.6",
    },
    "Case": {
        "enums": {"type": ["Question", "Incident", "Problem"]},
    },
    "Contact": {
        "no_usar": ["title", "department"],
        "nota": "title es notStorable en 7.5.6; department no existe",
    },
    "Note": {
        "nota": "type es readOnly; isInternal va en el nivel superior",
    },
    "Team": {
        "no_usar": ["description"],
        "nota": "Team no tiene description en 7.5.6",
    },
    "User": {
        "enums": {"type": ["regular", "admin", "portal", "system", "super-admin", "api"]},
    },
}
```

Estas reglas deben usarse como **pistas y validación previa**, no como sustituto del metadata de la instancia. Si un módulo licenciado cambia una opción, el metadata manda.

**Estado:** implementado con esa prioridad — metadata primero, tabla como respaldo.

Lo que se valida antes de enviar, y nada más:

1. **Enums**: si el campo es `enum`/`multiEnum` y el valor no está en `options`, se devuelve la lista de valores válidos.
2. **Obligatorios al crear**: campos `required` sin `default` que no estén en el payload ni en su forma `{campo}Id`.

Se dejaron fuera a propósito: la lista `no_usar`, porque el servidor acepta esos campos sin error (se comprobó que `Contact.title` y `department` se aceptan), y cualquier validación de formato o patrón, que el servidor ya comunica mejor.

`assignedUser` queda **exento** del control de obligatorios: 7.5.6 lo rellena con el API user cuando el rol prohíbe asignar, así que bloquear por su ausencia daría falsos positivos. Ese caso lo cubre P1-3.

Rechazo devuelto al LLM:

```json
{"error": "validation_failed", "message": "EspoCRM would reject this Contact payload; nothing was sent.",
 "entity": "Contact", "problems": [{"field": "pacienteCedula", "type": "required"}]}
```

**Cubierto por:** `tests/test_p1_2_entity_rules.py` (14 casos). **Verificado en vivo:**

| Payload | Resultado |
|---|---|
| `Account` con `tipoIdentificacion: "RUC"` | `invalidOption` con `allowed: ["04","05","06","07","08"]` leído del metadata real |
| `Contact` sin `pacienteCedula` | `{"field": "pacienteCedula", "type": "required"}` |
| `Meeting` con solo `name` | `{"field": "dateEnd", "type": "required"}` |
| `Contact` completo | se crea normalmente (y se borró después) |

### P1-3 Asignado por defecto

En 7.5.6, `Record\Service::populateDefaults` asigna el usuario actual **solo si el campo `assignedUser` está prohibido para el rol**. Si el rol permite asignar, la API no lo rellena. Por eso:

- Si `assignedUserId` no viene en `Meeting`/`Call`/`Task`, consultar `GET /App/user` y usar `user.id`.
- Documentar que un rol que prohíba asignación hará que EspoCRM use el API user automáticamente.

**Estado:** implementado. El perfil se cachea (`GET /App/user` una sola vez por proceso; el usuario viene anidado en `user`), y la inyección sólo se aplica al crear `Meeting`, `Call` o `Task` sin `assignedUserId` ni `assignedUser`.

Salvaguardas:

- `ESPO_AUTO_ASSIGN=0` desactiva la inyección para roles que prohíben el campo.
- Si aun así el servidor responde `403` nombrando `assignedUser`, se reintenta **una vez** sin el campo: en un `403` no se creó nada, así que el reintento es seguro. Otros `403` se devuelven tal cual.
- Si el perfil no se puede leer, se envía el payload original en lugar de fallar.

**Verificado en vivo:** `Meeting` —que antes devolvía `400 assignedUser required`—, `Call` y `Task` se crean correctamente y quedan asignados al usuario API (`external`); los tres se borraron después. En esa instancia `acl.assignmentPermission` es `all` y `fieldTable.Meeting` está vacío, es decir, el rol permite asignar.

**Cubierto por:** `tests/test_p1_3_default_assignee.py` (10 casos).

### P1-4 Fechas

- Campos `date`: `YYYY-MM-DD`.
- Campos `datetime`: `YYYY-MM-DD HH:mm:ss` en UTC.
- Aceptar como entrada `YYYY-MM-DDTHH:mm:ss`, `YYYY-MM-DDTHH:mm:ssZ` y convertirlos antes de enviar.
- En `Meeting` y `Call`, `dateStart`/`dateEnd` son obligatorios.

**Medición en vivo (`scripts/probe_dates.py`):**

| Entrada | Respuesta del servidor |
|---|---|
| `2026-12-01 10:00:00` | `200`, se guarda igual → se interpreta como **UTC** |
| `2026-12-01T10:00:00` | `400 {"field": "dateStart", "type": "valid"}` |
| `2026-12-01T10:00:00Z` | `400` ídem |
| `2026-12-01T10:00:00-05:00` | `400` ídem |
| `2026-12-01T10:00:00+00:00` | `400` ídem |

Además, el tipo real de `Meeting.dateStart`/`dateEnd` en 7.5.6 es **`datetimeOptional`**, no `datetime`: una primera versión que sólo miraba `datetime` dejaba pasar la cadena ISO y el servidor respondía 400.

**Estado:** implementado. La zona de trabajo es **América/Guayaquil (UTC-5)** fija, no la del sistema: Ecuador no aplica horario de verano desde 1993, así que un desplazamiento constante es exacto y no depende de la base IANA (que Python en Windows no trae). Se puede cambiar con `ESPO_UTC_OFFSET`.

Reglas aplicadas al **escribir** (`create_record` y `update_record`):

- Campo de tipo `datetime`/`datetimeOptional` y valor **sin** desplazamiento → se lee como hora de Guayaquil y se envía en UTC (10:00 local → `15:00:00`).
- Con desplazamiento explícito (`Z`, `-05:00`, `+02:00`) → se respeta y se convierte a UTC.
- Campos `date` y valores no interpretables → intactos; el servidor explica el error.
- Sin metadata disponible sólo se normalizan `dateStart`/`dateEnd`; un campo `datetime` propio no se toca, para no desplazarlo por conjetura.

**Decisión:** la normalización es sólo de entrada. Las lecturas (`get_record`, `list_records`) devuelven lo que manda EspoCRM, en UTC. Convertirlas a UTC-5 obligaría a reinterpretar cada respuesta y haría que los valores leídos no coincidan con los filtros enviados; si se necesita, es una entrega aparte.

**Verificado en vivo:** `dateStart: "2026-12-01 10:00:00"` se guarda como `2026-12-01 15:00:00`, y `dateEnd: "2026-12-01T11:00:00-05:00"` como `2026-12-01 16:00:00`. El registro se borró después.

**Cubierto por:** `tests/test_p1_4_dates.py` (14 casos).

### P1-5 Límite de paginación

`max_size` se acota a **200** en `list_records`, `list_related` y `get_stream`. No se rechaza la llamada: se devuelve la página acotada y la respuesta lo dice, para que el llamador sepa que pidió más de lo que recibió.

```json
{"list": [...], "total": 38,
 "pageSizeCapped": {"requested": 5000, "applied": 200, "max": 200}}
```

Un `max_size` de 0 o negativo sube a 1. La marca no se añade a las respuestas de error.

**Estado:** implementado. `tests/test_p1_5_pagination.py` (7 casos), verificado en vivo (`max_size=5000` → `applied: 200`).

### P1-6 `select` en lectura

`select` añadido a `get_record` y `list_related`; `list_records` ya lo tenía. Medición en vivo:

- `GET /Account` (listado) **respeta** `select` y añade solo unos campos automáticos (`id`, `createdAt`, `createdById`, `assignedUserId`).
- `GET /Account/{id}?select=id,name` **lo ignora**: devolvió los 58 campos del registro. Probado también con `attributeSelect`, con el mismo resultado.
- `GET /Account/{id}/contacts?select=...` **sí lo respeta**.

Por eso `get_record` con `select` no usa el endpoint de registro único: consulta el listado filtrando por `id` (`maxSize=1`) y devuelve la fila. Si no hay coincidencia devuelve un `404` explícito en lugar de un registro ajeno.

Resultado medido: **5 campos en vez de 58**.

**Estado:** implementado. `tests/test_p1_6_select.py` (7 casos) y verificado en vivo.

### P1-7 Relaciones `to-one`

El supuesto de esta ficha — que `GET /{Entity}/{id}/{link}` devuelve un objeto y no `{list}` — **no se cumple en 7.5.6**. Medición en vivo:

| Enlace | Tipo | Respuesta |
|---|---|---|
| `Account/{id}/assignedUser` | `belongsTo` | `{"total": 1, "list": [...]}` |
| `Account/{id}/originalLead` | `hasOne` | `{"total": 0, "list": []}` |
| `Task/{id}/parent` | `belongsToParent` | **`500 Internal Server Error`** (en las tres tareas probadas) |

No hay nada que “normalizar” en cuanto a forma: el sobre ya es uniforme. Lo que sí está roto es `belongsToParent`, y ahí se interviene:

- Si el enlace es `belongsToParent` según el metadata y el servidor falla con `5xx`, se lee el registro, se toman `parentType`/`parentId` y se devuelve `{"total": 1, "list": [<padre>], "resolvedVia": "parentId"}`. Sin padre: `{"total": 0, "list": []}`.
- Si un servidor devolviera un objeto suelto en un enlace `to-one`, se envuelve en el sobre. Es defensivo, no una corrección de lo observado.
- Un `5xx` en un enlace `to-many` se devuelve tal cual: no se redirige nada que no corresponda.

**Estado:** implementado. `tests/test_p1_7_links.py` (7 casos) y verificado en vivo (`Task/{id}/parent` ahora devuelve el contacto padre).

### P1-8 Timeout, reintentos y logs

| Variable | Default | Efecto |
|---|---|---|
| `ESPO_TIMEOUT` | `30` | Timeout por petición, en segundos. |
| `ESPO_MAX_RETRIES` | `2` | Reintentos adicionales. |
| `ESPO_RETRY_BACKOFF` | `0.5` | Base del retroceso exponencial. |
| `ESPO_LOG_LEVEL` | `INFO` | Nivel del registro. |

Política de reintentos, deliberadamente conservadora:

- **`429` se reintenta siempre**, respetando `Retry-After` cuando viene. Un `429` significa que la petición fue rechazada, así que repetirla no duplica nada.
- **`5xx` y errores de transporte sólo en `GET`**. Un `POST` que falla con `500` pudo haber creado el registro: duplicar una cita médica es peor que mostrar el error.

Trazabilidad: una línea por petición con método, ruta, estado y duración. Va a **stderr**, porque con transporte `stdio` el stdout es el protocolo MCP. La API key no aparece nunca: sólo se registra la ruta.

**Estado:** implementado. `tests/test_p1_8_resilience.py` (9 casos, con el retroceso a cero para no dormir en CI).

### P1-9 Detección de versión

`get_current_user` añade un bloque `compatibility` calculado desde `settings.version` de `GET /App/user`, y si la versión no empieza por `7.5.` se registra **un solo aviso**. No se bloquea nada: la instancia se sigue usando.

**Verificado en vivo:** `{"version": "7.5.6", "expected": "7.5.x", "compatible": true}`.

**Estado:** implementado. `tests/test_p1_9_version.py` (5 casos).

---

## 5. Contrato de compatibilidad con 7.5.6

| Entidad | Regla |
|---|---|
| `Meeting` | `assignedUser` requerido; `dateStart`/`dateEnd` requeridos; `status` Planned/Held/Not Held; no existe `googleEventId` en el core |
| `Call` | `assignedUser`, `dateStart` y `dateEnd` requeridos; `duration` es calculado (`notStorable`); no existe `phoneNumber` en el core |
| `Task` | `assignedUser` requerido; estados Not Started/Started/Completed/Canceled/Deferred; prioridad Low/Normal/High/Urgent |
| `Opportunity` | `stage`: Prospecting/Qualification/Proposal/Negotiation/Closed Won/Closed Lost; `amount` y `closeDate` requeridos; `probability` se autocalcula |
| `Case` | `type`: Question/Incident/Problem; estado New/Assigned/Pending/Closed/Rejected/Duplicate |
| `Contact` | `title` es `notStorable`; `department` no existe; `emailAddress` y `phoneNumber` sí funcionan |
| `Lead` | `status` y `source` con las opciones estándar; `industry` referencia las opciones de `Account.industry` |
| `Note` | `type` es `readOnly`; `isInternal` es booleano de primer nivel; `attachmentsIds` para adjuntos |
| `Team` | No tiene `description`; sí tiene `positionList` |
| `User` | Tipos: `regular`, `admin`, `portal`, `system`, `super-admin`, `api` |
| `Document` | `file` y `publishDate` requeridos si se crea desde la API |
| `Attachment` | Subida con `file` data URL; `parentType` para `attachmentMultiple`; `relatedType` para `file` |
| `Metadata` | `GET /Metadata?key=...` exige admin; `GET /Metadata` sin `key` no |
| Vínculos | `POST`/`DELETE /{Entity}/{id}/{link}` leen `id`/`ids` del body |
| Fechas | `YYYY-MM-DD` para date; `YYYY-MM-DD HH:mm:ss` en UTC para datetime |

---

## 6. Mejoras para siguientes versiones

### 6.1 Tomadas de `espocrm-mcp-server`

1. **Normalización por tipo de campo** (la mejora más valiosa para módulos licenciados):
   - `email` → `emailAddressData` (y fusionar en updates).
   - `phone` → `phoneNumberData` (y fusionar en updates).
   - `multiEnum` → fusionar con el valor actual.
   - `attachmentMultiple` → `{campo}Ids`.
   - `link` → `{campo}Id`.
   - `linkMultiple` → `{campo}Ids` y `{campo}Columns`.
   - `file` → subir primero y usar `{campo}Id`.
   - `currency` → `{campo}` y `{campo}Currency`.
2. **Metadata local o cacheada:** snapshot `metadata.json` generado con un admin para evitar elevar privilegios del API user.
3. **Lista blanca de entidades** y namespaces por entidad.
4. **Decorador de logging de tool calls** con nombre y parámetros.
5. **Docker Compose + healthcheck** para despliegue reproducible.
6. **Pruebas con pytest** y `conftest.py`.
7. **Helpers por entidad:** `find_by_email`, `find_by_domain`, `find_by_name`.
8. **Conversión de lead** usando la acción nativa.

### 6.2 Tomadas de `EspoMCP` (Node/TypeScript)

1. **Validación previa por entidad** para evitar 400 evitables.
2. **Asignado por defecto** desde `App/user`.
3. **`convert_lead` con `POST /Lead/action/convert`** y payload `{id, records}`.
4. **`get_user_permissions` real** usando `GET /User/{id}/acl` (existe en 7.5.6).
5. **Herramientas de equipos y roles** (`add_user_to_team`, `assign_role_to_user`, etc.).
6. **`health_check`** que valide autenticación y entidades clave.
7. **HMAC** si se necesita: digest crudo, sin body, `base64(apiKey + ":" + hash)`.
8. **Descripciones e `inputSchema` ricos** para que el LLM elija bien las tools.
9. **Pruebas de contrato** contra una instancia 7.5.6.

### 6.3 Mejoras propias de plataforma

1. **Modo solo lectura** (`ESPO_READ_ONLY=true`) para consultas seguras.
2. **Auditoría** de operaciones de escritura (quién, qué entidad, qué ID).
3. **Rate limit** local y respeto de `429`/`Retry-After`.
4. **Detección de versión** y matriz de compatibilidad (7.5.6, 8.x, 9.x).
5. **Transporte configurable**: `stdio` y `streamable-http`.
6. **CI** con lint, type check y pruebas.
7. **Versionado semántico** y `CHANGELOG.md`.
8. **Documentación de roles**: scopes mínimos por entidad para el API user.

---

## 7. Plan de pruebas

### 7.1 Pruebas de humo con `curl`

```bash
# 1. Versión y usuario
curl -H "X-Api-Key: $KEY" "$ESPO/api/v1/App/user"

# 2. Meeting con asignado y fechas
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"Prueba","dateStart":"2026-12-01 10:00:00","dateEnd":"2026-12-01 11:00:00","assignedUserId":"ID"}' \
  "$ESPO/api/v1/Meeting"

# 3. Opportunity con etapa válida y amount
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"Prueba","accountId":"ID","stage":"Proposal","closeDate":"2026-12-31","amount":1000}' \
  "$ESPO/api/v1/Opportunity"

# 4. Case con tipo válido
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name":"Prueba","type":"Problem"}' "$ESPO/api/v1/Case"

# 5. Nota interna
curl -X POST -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"parentType":"Account","parentId":"ID","post":"Nota interna","isInternal":true}' \
  "$ESPO/api/v1/Note"

# 6. Desvincular con body
curl -X DELETE -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"ids":["CONTACT_ID"]}' "$ESPO/api/v1/Account/ACCOUNT_ID/contacts"

# 7. Metadata sin admin
curl -H "X-Api-Key: $KEY" "$ESPO/api/v1/Metadata"
```

### 7.2 Casos de prueba automatizados

| Caso | Resultado esperado |
|---|---|
| `test_app_user_version` | `settings.version` empieza con `7.5.` |
| `test_contact_crud` | crear, leer, actualizar y borrar un contacto |
| `test_meeting_requires_assigned_user` | crear con `assignedUserId` → 200; sin él → 400 |
| `test_call_requires_dates` | crear con fechas → 200; sin fechas → 400 |
| `test_opportunity_stage_and_amount` | etapa `Proposal` + `amount` → 200; etapa vieja → 400 |
| `test_case_type` | `Problem` → 200; `Feature Request` → 400 |
| `test_note_internal` | `isInternal: true` se persiste |
| `test_link_unlink` | `link` con `ids` y `unlink` con `ids` funcionan |
| `test_attachment_multiple` | subir con `parentType` y asociar con `attachmentsIds` |
| `test_metadata_non_admin` | `GET /Metadata` sin `key` → 200; con `key` → 403 |
| `test_licensed_entity` | crear y listar una entidad de un módulo licenciado |

**Implementado hasta ahora:** `tests/conftest.py` (EspoCRM 7.5.6 simulado con `httpx.MockTransport`), `tests/test_p0_1_unlink_records.py`, `tests/test_p0_2_upload_attachment.py`, `tests/test_p0_3_create_note.py`, `tests/test_p0_4_metadata.py`, `tests/test_p0_5_errors.py`, `tests/test_p0_6_where_encoding.py`, `tests/test_p1_1_entity_allow.py`, `tests/test_p1_2_entity_rules.py`, `tests/test_p1_3_default_assignee.py`, `tests/test_p1_4_dates.py`, `tests/test_p1_5_pagination.py`, `tests/test_p1_6_select.py`, `tests/test_p1_7_links.py`, `tests/test_p1_8_resilience.py`, `tests/test_p1_9_version.py`, `tests/test_p2_1_qmedic_catalog.py` y `tests/test_p2_2_start_script.py` — 183 casos. Se ejecutan con `python -m pytest`.

### 7.3 Verificación contra una instancia real

Ejecutada el 2026-11-06 contra una instancia 7.5.6 con usuario API de tipo `api` (no administrador).

```powershell
$env:ESPO_URL = "https://<host>/<ruta>"
$env:ESPO_API_KEY = "<api key>"
python scripts/live_check.py        # sondas de solo lectura
python scripts/live_acceptance.py   # P0-1, P0-2 y P0-3 con limpieza automática
```

**Resultado:** 10/10 verificaciones correctas (versión, vínculo/desvínculo, nota interna persistida y adjunto `attachmentMultiple` asociado). Los cinco registros de prueba (Account, Contact, 2 Note, Attachment) se crearon con marcador `MCPTEST-*` y se eliminaron al finalizar.

Hallazgos de la instancia:

| Hallazgo | Consecuencia |
|---|---|
| `Account.tipoIdentificacion` obligatorio, enum `04`–`08`, default `05` | sin él o con otro valor → 400 (`type: "valid"`) |
| `Contact.pacienteCedula` obligatorio (varchar, máx. 25) | sin él → 400 (`type: "required"`) |
| `GET /Metadata?key=` responde 200 e ignora la clave | P0-4: no se puede depender de `?key=` |
| Los errores de validación no traen `message` | P0-5 debe leer `messageTranslation` |

Confirma el riesgo de P1-2: en instancias personalizadas las reglas por entidad hardcodeadas quedan cortas, y el metadata de la instancia es la única fuente confiable.

---

## 8. Riesgos y decisiones pendientes

| Riesgo | Mitigación |
|---|---|
| El metadata de frontend es grande | Cachear en memoria/disco y exponer solo rutas solicitadas |
| El API user necesita admin para `?key=` | Usar `/Metadata` sin `key` o un snapshot local; no elevar el API user |
| Módulos licenciados con campos personalizados | Normalización por tipo de campo y metadata de la instancia |
| `assignedUser` depende del rol | Enviar siempre `assignedUserId` o documentar el comportamiento del rol |
| 7.5.6 está fuera de soporte | Mantener la matriz de compatibilidad y planear la actualización |
| HMAC no implementado | Añadirlo solo si se necesita; API Key es suficiente para 7.5.6 |
| Fechas y zonas horarias | Normalizar a UTC y documentar el formato |

---

## 9. Checklist de entrega

- [x] P0-1 `unlink_records` con body `ids` — probado (`tests/test_p0_1_unlink_records.py`).
- [x] P0-2 `upload_attachment` con `parentType` para `attachmentMultiple` — probado (`tests/test_p0_2_upload_attachment.py`).
- [x] P0-3 `create_note` con `isInternal` — probado (`tests/test_p0_3_create_note.py`).
- [x] P0-4 metadata sin admin — probado (`tests/test_p0_4_metadata.py`) y verificado en vivo.
- [x] P0-5 errores con `message`/`data` — probado (`tests/test_p0_5_errors.py`) y verificado en vivo.
- [x] P0-6 `where` en forma de corchetes — probado (`tests/test_p0_6_where_encoding.py`) y verificado en vivo.
- [x] P1-1 lista blanca de entidades — probado (`tests/test_p1_1_entity_allow.py`) y verificado en vivo.
- [x] P1-2 reglas por entidad — probado (`tests/test_p1_2_entity_rules.py`) y verificado en vivo; metadata primero, tabla como respaldo.
- [x] P1-3 asignado por defecto — probado (`tests/test_p1_3_default_assignee.py`) y verificado en vivo.
- [x] P1-4 normalización de fechas — probado (`tests/test_p1_4_dates.py`) y verificado en vivo (zona fija UTC-5, América/Guayaquil).
- [x] P1-5 límite de paginación — probado (`tests/test_p1_5_pagination.py`) y verificado en vivo.
- [x] P1-6 `select` en `get_record` y `list_related` — probado (`tests/test_p1_6_select.py`) y verificado en vivo.
- [x] P1-7 relaciones `to-one` — probado (`tests/test_p1_7_links.py`) y verificado en vivo; `belongsToParent` resuelto por `parentType`/`parentId`.
- [x] P1-8 timeout, reintentos y logs — probado (`tests/test_p1_8_resilience.py`).
- [x] P1-9 detección de versión — probado (`tests/test_p1_9_version.py`) y verificado en vivo.
- [x] P1-10 empaquetado y `LICENSE` — versiones acotadas, `.env.example`, rueda verificada (`server.py` y `qmedic_catalog.py`).
- [x] P2-1 catálogo de entidades de QMedic — probado (`tests/test_p2_1_qmedic_catalog.py`, 30 casos) y regenerable con `--check`.
- [x] P2-2 arranque desde VS Code con `.env` — `.vscode/mcp.json`, `scripts/start_mcp.py` y 18 casos en `tests/test_p2_2_start_script.py`.
- [x] Pruebas de contrato contra 7.5.6 — `scripts/live_acceptance.py` 10/10, más verificaciones puntuales por cada P0/P1.
- [x] README actualizado con las variables de entorno; las particularidades de 7.5.6 están en §2–§4 y §10.
- [x] `CHANGELOG.md` y versión `1.0.1` (paquete `espocrm-mcp7`).
- [x] Instrucciones de instalación en §10.

---

## 10. Instalación y puesta en marcha

### 10.1 Requisitos

- Python 3.10 o superior (probado con 3.14 en Windows).
- EspoCRM 7.5.x. Otra versión no se bloquea, pero el servidor avisa (P1-9) y las particularidades documentadas pueden no aplicar.
- Un usuario de API y su clave. **No hace falta administrador**: nada de lo que hace este servidor lo requiere.
- Permisos del rol suficientes para las entidades que se vayan a usar (lectura y escritura).

### 10.2 Instalar

```powershell
git clone https://github.com/xavfo/espocrm-mcp.git
cd espocrm-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

- Con `uv`: `uv sync --extra dev`.
- El extra `dev` sólo añade `pytest`. Para ejecutar el servidor basta `pip install -e .`.
- El paquete **no está publicado en PyPI** a la fecha de esta entrega: se instala desde el repositorio.

### 10.3 Configurar las credenciales

El servidor lee **variables de entorno**, no un archivo `.env`. `.env.example` sirve como plantilla de qué variables existen; los valores se pasan en el bloque `env` del cliente MCP o en la sesión de PowerShell:

```powershell
$env:ESPO_URL = "https://crm.example.com"
$env:ESPO_API_KEY = "<api key>"
```

Si faltan `ESPO_URL` o `ESPO_API_KEY`, el servidor termina con código 1 y un mensaje en stderr.

### 10.4 Registrar el servidor en el cliente MCP

En Claude Code (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "espocrm": {
      "command": "uv",
      "args": ["run", "--directory", "C:/ruta/a/espocrm-mcp", "python", "server.py"],
      "env": {
        "ESPO_URL": "https://crm.example.com",
        "ESPO_API_KEY": "<api key>",
        "MCP_ENTITY_ALLOW": "Account,Contact,Opportunity"
      }
    }
  }
}
```

Sin `uv`, usa `"command": "python"` con la ruta absoluta a `server.py` como único argumento. El nombre de la clave raíz (`mcpServers`, `servers`) depende del cliente; los argumentos y el bloque `env` son iguales en todos.

**Visual Studio Code:** el repo incluye `.vscode/mcp.json`, que arranca
`scripts/start_mcp.py` en vez de `server.py`. El script saca las credenciales de
`.env` (ignorado por git, así la API key no queda en un archivo versionado),
prefiere el intérprete de `.venv`, comprueba que `mcp` y `httpx` se puedan importar
y reenvía `--http` si se le pasa:

```powershell
python scripts/start_mcp.py --setup   # pregunta ESPO_URL y ESPO_API_KEY una vez
```

Si VS Code arranca el servidor sin `.env`, el script **no se queda esperando** en
stdin (eso colgaría el cliente MCP): termina con código 2 y deja el mensaje en
**Output → MCP**. `ESPO_PYTHON` fuerza un intérprete concreto; el entorno del proceso
tiene prioridad sobre `.env`.

Transporte HTTP opcional: `python server.py --http` (puerto en `MCP_PORT`, 8000 por defecto).

### 10.5 Comprobar que quedó bien

```powershell
python scripts/live_check.py        # solo lectura: versión, permisos y metadata
python -m pytest                    # 183 casos, sin instancia real
python scripts/live_acceptance.py   # crea y borra registros de prueba
```

Resultados esperados:

| Comprobación | Esperado |
|---|---|
| `live_check.py` | `version=7.5.6` en `App/user`; 200 en `Metadata`, `Settings` y `Account` |
| `pytest` | `183 passed` |
| `live_acceptance.py` | `10/10 verificaciones correctas` y los registros `MCPTEST-*` eliminados |

`live_acceptance.py` **escribe** en el CRM: crea una cuenta, un contacto, dos notas y un adjunto con el prefijo `MCPTEST-`, y los borra en un bloque `finally`. Si el proceso se interrumpe, esos registros quedan en el CRM y hay que borrarlos a mano.

### 10.6 Variables de entorno

| Variable | Requerida | Default | Para qué |
|---|---|---|---|
| `ESPO_URL` | sí | — | URL base, con subdirectorio si la instalación lo usa. |
| `ESPO_API_KEY` | sí | — | Clave del usuario de API. |
| `MCP_ENTITY_ALLOW` | no | vacío | Lista blanca de entidades (P1-1). |
| `ESPO_METADATA_MODE` | no | `frontend` | `frontend` cachea `/Metadata`; `admin` usa `?key=` (requiere administrador). |
| `ESPO_AUTO_ASSIGN` | no | `1` | Asigna `Meeting`/`Call`/`Task` al usuario de API (P1-3). |
| `ESPO_UTC_OFFSET` | no | `-5` | Zona de trabajo para convertir fechas a UTC (P1-4). |
| `ESPO_TIMEOUT` | no | `30` | Timeout por petición, en segundos. |
| `ESPO_MAX_RETRIES` | no | `2` | Reintentos de `429` y, sólo en lecturas, de `5xx`. |
| `ESPO_RETRY_BACKOFF` | no | `0.5` | Base del retroceso exponencial. |
| `ESPO_LOG_LEVEL` | no | `INFO` | Nivel de traza (stderr). |
| `MCP_PORT` | no | `8000` | Puerto con `--http`. |

### 10.7 Si algo no funciona

| Síntoma | Causa probable |
|---|---|
| El proceso termina con código 1 | Falta `ESPO_URL` o `ESPO_API_KEY`. |
| `401` | Clave incorrecta o usuario inactivo. |
| `403` al leer una entidad | El rol del usuario de API no tiene ese scope. |
| `400` con `message: validationFailure` | Mira `data.field` y `data.type`: el campo concreto y el motivo. |
| `error: entity_not_allowed` | La entidad no está en `MCP_ENTITY_ALLOW`. |
| Aviso “EspoCRM X detected” | La instancia no es 7.5.x; sigue funcionando, pero revisa §5. |
| `select` no acota la respuesta | Estás leyendo con `get_record` sin `select`, o la instancia ignora `select` en lectura individual (P1-6). |

### 10.8 Limitaciones conocidas

- La rueda publica `server.py` como módulo **global** `server`, junto a `qmedic_catalog` (también global). Para publicar en PyPI conviene moverlos a un paquete (`espocrm_mcp/`), que es un cambio de estructura pendiente.
- Las lecturas devuelven las fechas en UTC; sólo se normaliza la escritura (§P1-4).
- `GET /{Entity}/{id}?select=` se ignora en 7.5.6, y `belongsToParent` no se puede listar: ambos casos tienen rodeo implementado y documentado.

---

## 11. Catálogo de entidades de QMedic (P2-1)

### 11.1 El problema

La instancia de QMedic no es «EspoCRM con unos campos extra»: el metadata del
proyecto define **141 entidades** propias (`Atencion`, `SignosVitales`, `Receta`,
`RecetaProducto`, `Prscdspnlineitem`, `FhirMap`, `Wischat`…). Las herramientas CRUD
ya las alcanzaban, porque son genéricas, pero el modelo no tenía forma de saber que
existían: `list_entity_types` devuelve nombres sin etiqueta, y `get_metadata` cuesta
unos 979 KB (§P0-4).

Síntoma típico: el asistente inventa `Patient` cuando en QMedic el paciente es
`Contact` con etiqueta «Paciente», o escribe en `Invoice` sin saber que las líneas
van en `items` y los impuestos en `InvoiceItem.taxTypes`.

### 11.2 La solución

`qmedic_catalog.py`, un módulo **generado** desde
`custom/Espo/Custom/Resources` de QMedic:

| Dato | Origen |
|---|---|
| Nombre y etiqueta de la entidad | `i18n/es_ES/Global.json` → `scopeNames` (fallback al propio i18n del scope) |
| Campos obligatorios | `entityDefs.<Entidad>.fields`, descartando `readOnly`, los de infraestructura y los que traen `default` |
| Opciones cerradas | Campos `enum`/`multiEnum` con `options` estáticas |
| Campos de fecha y hora | Campos `datetime`/`datetimeOptional` no `readOnly` |
| Enlaces de dominio | `entityDefs.<Entidad>.links` con `entity`, sin `assignedUser`/`teams`/`createdBy`/`modifiedBy` |
| `statusField` y `stream` | `scopes/<Entidad>.json` |

Lo único escrito a mano es la **agrupación funcional** (`clinico`, `especialidad`,
`recetas`, `facturacion`, `inventario`, `contabilidad`, `comercial`,
`comunicaciones`, `fhir`, `actividad`, `administracion`) y la frase de flujo de cada
grupo. Todas las afirmaciones de esas frases se verificaron contra los enlaces del
metadata: por ejemplo, las recetas cuelgan de `Contact.recetas` y **no** de la
Atención; `Meeting` se llama «Consulta» en esta instancia; y las entidades `Chart*`
son el plan de cuentas contable, no las curvas de crecimiento.

### 11.3 Herramientas

| Herramienta | Para qué |
|---|---|
| `list_qmedic_entities(group, query)` | Mapa del proyecto: grupos con recuento, flujo recomendado y entidades con etiqueta y obligatorios |
| `describe_entity(entity, include_all_fields)` | Ficha de una entidad: obligatorios, enums, fechas y enlaces. Lee el metadata vivo y, si no está, el catálogo (`source`) |
| `get_patient_summary(contact_id, max_items, sections)` | Cabeza del paciente más los últimos registros de `atenciones`, `signosVitales`, `recetas`, `certificados` y `resultados` |

`describe_entity` responde en modo compacto (obligatorios, enums, fechas y `name`) y
dice cuántos campos quedaron fuera; `include_all_fields=True` los devuelve todos.

### 11.4 Prioridad de las fuentes

La instancia sigue siendo la autoridad:

1. `_required_fields` y `_validate_payload` usan `entityDefs` del metadata cuando
   existe; el catálogo sólo rellena huecos.
2. `_normalize_dates` usa el tipo del metadata; si no hay metadata, usa los campos
   `datetime` del catálogo, así que `Atencion.fechaIngreso` se convierte a UTC en
   lugar de enviarse tal cual.
3. `describe_entity` marca `source: "metadata"` o `source: "catalog"` para que el
   llamador sepa cuánto confiar en la ficha.

### 11.5 Regeneración y verificación

```powershell
python scripts/generate_qmedic_catalog.py            # reescribe qmedic_catalog.py
python scripts/generate_qmedic_catalog.py --check    # falla si está desactualizado
```

La ruta por defecto es el repositorio hermano `../qmedic-v4/custom/Espo/Custom/Resources`;
se cambia con `QMEDIC_METADATA` o `--metadata`. El generador avisa por stderr de
cualquier entidad que no tenga grupo, para que una entidad nueva no pase inadvertida.

La prueba `test_catalog_is_up_to_date_with_qmedic_metadata` reconstruye el catálogo
en memoria y lo compara con el archivo versionado; se omite si el metadata de QMedic
no está en la máquina, así que la suite sigue corriendo sin el proyecto al lado.

---

## Anexo A. Payloads de referencia para 7.5.6

### Opportunity

```json
{
  "name": "Propuesta Acme",
  "accountId": "ACCOUNT_ID",
  "stage": "Proposal",
  "amount": 15000,
  "closeDate": "2026-12-31"
}
```

### Meeting

```json
{
  "name": "Kickoff",
  "dateStart": "2026-12-01 10:00:00",
  "dateEnd": "2026-12-01 11:00:00",
  "assignedUserId": "USER_ID",
  "status": "Planned"
}
```

### Call

```json
{
  "name": "Llamada de seguimiento",
  "dateStart": "2026-12-01 15:00:00",
  "dateEnd": "2026-12-01 15:30:00",
  "assignedUserId": "USER_ID",
  "direction": "Outbound",
  "status": "Held"
}
```

### Note

```json
{
  "parentType": "Account",
  "parentId": "ACCOUNT_ID",
  "post": "Reunión reprogramada",
  "isInternal": true
}
```

### Lead convert

```json
{
  "id": "LEAD_ID",
  "records": {
    "Account": { "name": "Acme" },
    "Contact": { "firstName": "Ana", "lastName": "Pérez" },
    "Opportunity": { "name": "Acme - Implementación", "amount": 20000 }
  }
}
```

### Desvincular

```json
{
  "ids": ["CONTACT_ID"]
}
```
