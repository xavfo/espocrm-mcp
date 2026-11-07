# Desarrollo de `espocrm-mcp` para EspoCRM 7.5.6

**Estado:** propuesto
**Base elegida:** `espocrm-mcp` (`server.py` único, licencia MIT)
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
| `where` como JSON string | Documentado en `api-search-params` |
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

**Prueba de aceptación:** crear un `Case` con `type: "Feature Request"` devuelve un error con el `message` de EspoCRM y el detalle de validación.

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

### P1-3 Asignado por defecto

En 7.5.6, `Record\Service::populateDefaults` asigna el usuario actual **solo si el campo `assignedUser` está prohibido para el rol**. Si el rol permite asignar, la API no lo rellena. Por eso:

- Si `assignedUserId` no viene en `Meeting`/`Call`/`Task`, consultar `GET /App/user` y usar `user.id`.
- Documentar que un rol que prohíba asignación hará que EspoCRM use el API user automáticamente.

### P1-4 Fechas

- Campos `date`: `YYYY-MM-DD`.
- Campos `datetime`: `YYYY-MM-DD HH:mm:ss` en UTC.
- Aceptar como entrada `YYYY-MM-DDTHH:mm:ss`, `YYYY-MM-DDTHH:mm:ssZ` y convertirlos antes de enviar.
- En `Meeting` y `Call`, `dateStart`/`dateEnd` son obligatorios.

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

- [ ] P0-1 `unlink_records` con body `ids`.
- [ ] P0-2 `upload_attachment` con `parentType` para `attachmentMultiple`.
- [ ] P0-3 `create_note` con `isInternal`.
- [ ] P0-4 metadata sin admin.
- [ ] P0-5 errores con `message`/`data`.
- [ ] P1-1 lista blanca de entidades.
- [ ] P1-2 reglas por entidad.
- [ ] P1-3 asignado por defecto.
- [ ] P1-4 normalización de fechas.
- [ ] P1-5–P1-9 límites, `select`, relaciones, timeout/logs y versión.
- [ ] P1-10 empaquetado y `LICENSE`.
- [ ] Pruebas de contrato contra 7.5.6.
- [ ] README actualizado con las particularidades de 7.5.6.
- [ ] `CHANGELOG.md` y versión `0.2.0`.

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
