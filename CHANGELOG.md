# Changelog

Todas las fechas en formato AAAA-MM-DD. El proyecto sigue versionado semántico
mientras la versión sea `0.x`: la API de las herramientas puede cambiar entre
versiones menores.

## [0.2.0] — 2026-11-09

Adaptación de la base 1.0.0 para **EspoCRM 7.5.6**, verificada contra una instancia
real (incluidos módulos y campos personalizados).

### Corregido (P0)

- **`unlink_records`**: envía `{"ids": [...]}` en el cuerpo. 7.5.6 ignora el `id` por
  query string y devolvía `false` sin desvincular nada.
- **`upload_attachment`**: distingue campos `file` (con `relatedType`/`relatedId`) de
  `attachmentMultiple` (con `parentType`/`parentId`). Antes el adjunto quedaba
  huérfano. `field` pasa a ser obligatorio.
- **`create_note`**: `isInternal` va en el primer nivel y deja de enviarse `type`
  (`readOnly`). Antes una nota interna podía guardarse como pública.
- **Metadata sin administrador**: se cachea `GET /Metadata` y se navega localmente.
  `ESPO_METADATA_MODE=admin` queda como opción.
- **Errores útiles**: `_req` devuelve `error`, `message`, `data` y `body`, incluyendo
  la forma `messageTranslation` que usa 7.5.6 para las validaciones.
- **`where`**: se envía en forma `where[0][type]=...`. La forma JSON string que
  sugiere la documentación **se ignora** en 7.5.6, así que todo filtro devolvía la
  colección completa sin aviso.

### Añadido (P1)

- **`MCP_ENTITY_ALLOW`**: lista blanca de entidades, evaluada antes de cualquier
  petición en todas las herramientas.
- **Validación previa**: enums fuera de rango y campos obligatorios, tomados del
  metadata de la instancia (la tabla `ENTITY_RULES` es solo respaldo).
- **Asignado por defecto** en `Meeting`, `Call` y `Task`, con
  `ESPO_AUTO_ASSIGN` y reintento si el rol prohíbe el campo.
- **Fechas normalizadas** a UTC con zona de trabajo fija UTC-5 (América/Guayaquil);
  acepta ISO con `T`/`Z`/desplazamiento. `ESPO_UTC_OFFSET`.
- **Límite de paginación** de 200 con aviso `pageSizeCapped`.
- **`select`** en `get_record` y `list_related`; en lectura individual se resuelve
  vía listado porque 7.5.6 ignora `select` en `GET /{Entity}/{id}`.
- **Enlaces `belongsToParent`** resueltos por `parentType`/`parentId`: listarlos
  devuelve `500` en 7.5.6.
- **Timeout, reintentos y trazas**: `ESPO_TIMEOUT`, `ESPO_MAX_RETRIES`,
  `ESPO_LOG_LEVEL`. `429` siempre se reintenta; `5xx` solo en lecturas. Los registros
  van a stderr y nunca incluyen la API key.
- **Detección de versión**: `get_current_user` informa `compatibility` y avisa una
  vez si la instancia no es 7.5.x.

### Pruebas y utilidades

- 135 pruebas (`python -m pytest`) contra un EspoCRM 7.5.6 simulado.
- `scripts/live_check.py`: sondas de solo lectura contra una instancia real.
- `scripts/live_acceptance.py`: aceptación en vivo con limpieza automática.
- `scripts/probe_dates.py`: mide cómo interpreta la instancia cada formato de fecha.

### Empaquetado

- Versiones de `mcp` y `httpx` acotadas; `LICENSE` (MIT) y `.env.example`.

[0.2.0]: https://github.com/przyszloscjestdzisiaj/espocrm-mcp/releases/tag/v0.2.0
