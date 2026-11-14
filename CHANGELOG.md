# Changelog

Todas las fechas en formato AAAA-MM-DD. El proyecto sigue versionado semántico
mientras la versión sea `0.x`: la API de las herramientas puede cambiar entre
versiones menores.

## [1.1.0] — 2026-11-13

Soporte de las **141 entidades que define QMedic** sobre EspoCRM. Las herramientas
CRUD ya las alcanzaban; lo que faltaba era un mapa para descubrirlas sin descargar
el metadata completo.

### Añadido

- **`qmedic_catalog.py`**: catálogo generado desde el metadata de QMedic con etiqueta
  de interfaz, grupo funcional, campos obligatorios, opciones cerradas, campos de
  fecha y hora y enlaces de dominio de cada entidad.
- **`list_qmedic_entities`**: lista las entidades por grupo (`clinico`, `facturacion`,
  `fhir`…), con el flujo recomendado para cada uno y filtro por nombre o etiqueta.
- **`describe_entity`**: ficha de una entidad con obligatorios, enums, fechas y
  enlaces. Usa el metadata vivo y, si no responde, el catálogo, indicándolo en
  `source`. En modo compacto sólo muestra lo necesario para escribir un payload.
- **`get_patient_summary`**: cabeza del paciente más los últimos registros de
  `atenciones`, `signosVitales`, `recetas`, `certificados` y `resultados` en una sola
  llamada de sólo lectura.
- **`scripts/generate_qmedic_catalog.py`** con `--check`, para regenerar el catálogo
  cuando cambie QMedic y fallar si el archivo versionado quedó viejo. Ruta
  configurable con `QMEDIC_METADATA`.
- **Arranque desde Visual Studio Code**: `.vscode/mcp.json` y
  `scripts/start_mcp.py`. El script carga `.env` (no versionado), lo crea
  preguntando `ESPO_URL` y `ESPO_API_KEY` (`--setup`), normaliza la URL, prefiere el
  intérprete de `.venv`, comprueba que `mcp` y `httpx` se importen y, lanzado sin
  terminal desde el cliente MCP, termina con código 2 y un mensaje accionable en
  lugar de quedarse esperando en stdin.

### Cambiado

- **Validación previa ampliada**: `ENTITY_RULES` se completa con los obligatorios y
  enums del catálogo, así que un enum fuera de rango o un campo obligatorio ausente
  se detectan incluso si `GET /Metadata` falla. El metadata de la instancia sigue
  teniendo prioridad.
- **Fechas**: sin metadata, los campos `datetime` del catálogo se convierten a UTC
  (antes sólo `dateStart`/`dateEnd`); `Atencion.fechaIngreso` ya no se envía como
  hora local sin convertir.
- **Empaquetado**: la rueda incluye `qmedic_catalog.py` además de `server.py`;
  versión `1.1.0`.

### Pruebas

- 30 pruebas del catálogo (`tests/test_p2_1_qmedic_catalog.py`): integridad,
  herramienta por herramienta, validación y fechas desde el catálogo, enlaces
  múltiples en forma `Ids`, y comparación del archivo versionado contra el metadata
  real de QMedic (se omite si no está).
- 18 pruebas del arranque (`tests/test_p2_2_start_script.py`): lectura del `.env`,
  validación, preguntas sin eco, escritura sin CRLF, precedencia del entorno, fallo
  rápido sin terminal y el propio `mcp.json`.
- Total: **183 pruebas**.

## [1.0.1] — 2026-11-09

El paquete pasa a llamarse **`espocrm-mcp7`** para poder convivir con el
`espocrm-mcp` original, y la versión continúa la línea del upstream (1.0.0) en lugar
de empezar de cero: es un fork que mantiene una versión concreta de EspoCRM.

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

- Nombre del paquete: `espocrm-mcp7`; versión `1.0.1`.
- Sólo se publica `server.py`: la rueda ya no arrastra tests, scripts ni docs.
- Versiones de `mcp` y `httpx` acotadas; `LICENSE` (MIT) y `.env.example`.

[1.0.1]: https://github.com/xavfo/espocrm-mcp/releases/tag/v1.0.1
