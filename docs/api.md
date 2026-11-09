# API (resumen)

Esquema completo: http://localhost:8080/api/openapi.json (interactivo en `/api/docs`). Los tipos del frontend se
generan desde ese esquema (`make gen-types` → `frontend/src/api/schema.d.ts`) y `make test` verifica que estén al día.

| Método y ruta | Descripción |
|---|---|
| `GET /api/health` | Estado de API, base de datos y caché |
| `GET /api/engine` | Motor verificado: wheel, tag, SHA, banner de `runepanet` |
| `GET /api/catalog/pipes`, `GET /api/design-profiles` | Catálogo de tuberías y perfiles de criterios |
| `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}` | CRUD de proyectos (crear genera la versión 1) |
| `GET /api/projects/{id}/versions[/{n}]` | Versiones (inmutables) con conteos y si tienen resultados |
| `GET /api/projects/{id}/network?version=n` | Red como GeoJSON + opciones + secciones complementarias |
| `PUT /api/projects/{id}/network` | Guarda la red (crea una versión; `base_version` controla la concurrencia → 409) |
| `POST /api/projects/{id}/validate` | Valida `model_version` o una red en edición: `errors` (bloqueantes) y `warnings` |
| `POST /api/projects/{id}/simulate` | Síncrono. `{model_version}` → resultados en todos los pasos + mensajes del motor + alertas de criterios. Con errores bloqueantes responde 422 `{status: "blocked", validation}` sin ejecutar |
| `GET /api/projects/{id}/runs/{run_id}` | Resultados de una corrida guardada |
| `POST /api/projects/import` | Importa un `.inp` (multipart: `file`, `name`, `crs` = auto/local/EPSG:xxxx) |
| `GET /api/projects/{id}/export.inp?version=n` | Exporta una versión como `.inp` (coordenadas en el SRID del proyecto) |

## Validación

| Código | Tipo | Regla |
|---|---|---|
| `E_EMPTY_NETWORK` | error | Red vacía |
| `E_NO_SOURCE` | error | Sin reservorio ni estanque |
| `E_LINK_NODE` | error | Tramo con nudo inexistente o con el mismo nudo inicial y final |
| `E_DIAMETER_NOT_IN_CATALOG` | error | DN, clase o ítem inexistente en el catálogo del material |
| `E_DUPLICATE_ID` / `E_INVALID_ID` | error | IDs repetidos o con formato no aceptado por EPANET |
| `E_ISOLATED_NODE` | error | Nudo sin tramos |
| `E_DISCONNECTED_NODE` | error | Nudo con tramos pero sin camino a ningún reservorio o estanque |
| `E_MISSING_PARAM` | error | Cota (nunca se supone: un elemento nuevo queda sin cota hasta ingresarla), carga, niveles, largo, rugosidad, diámetro, curva/patrón inexistente, parámetros PDA |
| `W_ELEVATION_ASSUMED` | advertencia | Cota supuesta traída por una importación (p. ej. `.inp` sin columna de cota, que EPANET toma como 0 m) |
| `W_ELEVATION_DOUBTFUL` | advertencia | Cota con salto mayor a 50 m respecto de los vecinos |
| `W_SHORT_PIPE` | advertencia | Largo hidráulico menor que 1 m |
| `W_NO_DEMAND` | advertencia | Nudo de consumo sin demanda |
| `W_CRITERIA` | advertencia | DN bajo el mínimo del perfil o rugosidad fuera del rango típico de la fórmula |

Alertas de resultados (`alerts`): `PRESSURE_LOW`, `PRESSURE_HIGH`, `VELOCITY_LOW`, `VELOCITY_HIGH` y
`BOTTLENECK` (pérdida unitaria sobre el criterio del perfil, 10 m/km por defecto).

## Protección mínima (hasta la etapa 5)

| Respuesta | Cuándo |
|---|---|
| `401` | Sin credenciales de basic auth (lo responde Caddy; ver README) |
| `413` | `.inp` mayor que `MAX_INP_MB` (20 MB) o solicitud a `/api` mayor que 50 MB |
| `429` | Más de `RATE_LIMIT_PER_MINUTE` (300) solicitudes a `/api` por IP en el minuto; incluye `Retry-After` |

`/api/health` no se limita. La IP se toma del último valor de `X-Forwarded-For`, que agrega Caddy.
