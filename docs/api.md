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
| `E_CLIENT_NODE` | error | Cliente asignado a un nudo inexistente o que no es de consumo (impide guardar) |
| `E_SHUTOFF_LINK` | error | Llave de corte sobre un elemento que no es una tubería existente (impide guardar) |
| `W_SCENARIO_VALVE` | advertencia | Un escenario cierra llaves que ya no existen |
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

## Clientes, llaves de corte, escenarios y factibilidad

La red (`network.features`) admite además de nudos y tramos:

- **Cliente** (`element: "client"`, punto): `name`, `client_type` (residencial, comercial, industrial, publico),
  `status` (activo, proyectado), `consumption_value` + `consumption_unit` (`L/s` o `m3/mes`, mes de 30 días),
  `node` (nudo de consumo asignado), `link` y `connection` (tubería y punto del arranque), `connection_mode`
  (`nearest` o `new_node`) y `elevation` opcional (la presión del cliente se calcula en su cota).
  La demanda del nudo es su demanda manual + la de sus clientes activos (y los proyectados si
  `options.include_projected_clients`). En el `.inp` cada cliente es una categoría de `[DEMANDS]` llamada
  `cliente_<ID>`, y la demanda manual se llama `manual`.
- **Llave de corte** (`element: "shutoff"`, punto): `link` (tubería), `position` (0–1 a lo largo de la
  tubería; la API recalcula la geometría), `state` (`open` o `closed`). Cerrada = la tubería se escribe `Closed`.

`scenarios` (en `PUT /network` y `GET /network`): `[{id, name, closed: [IDs de llaves]}]`; se versionan con el modelo.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/projects/{id}/scenarios/simulate` | `{model_version, scenario}` (`normal`, `todas_cerradas`, `actual` o ID propio). Nudos y clientes con o sin suministro (topología por tramos abiertos) y presión mínima del periodo; los sectores sin suministro se simulan sin demanda para evitar presiones sin sentido |
| POST | `/api/projects/{id}/scenarios/compare` | `{model_version, a, b}`: presión por nudo y cliente en ambos escenarios y diferencia |
| POST | `/api/projects/{id}/feasibility` | `{model_version, link, point, consumption_lps, elevation}`: simula la red con un nudo nuevo en el punto (divide la tubería) sin modificar el proyecto. FACTIBLE si la presión del punto ≥ presión mínima del proyecto y ningún consumo existente pasa a quedar bajo el mínimo. Si no lo es, aumenta el DN del cuello de botella (mayor pérdida unitaria entre los tramos que aumentaron su caudal) al siguiente del catálogo, hasta 3 veces |
| POST | `/api/projects/{id}/feasibility/report` | Mismo cuerpo; devuelve el informe HTML imprimible |
| POST | `/api/projects/{id}/clients/import` | CSV (`lat, lon, nombre, consumo` en L/s; opcionales `tipo, estado, unidad`). Asigna cada cliente al nudo de consumo más cercano de la tubería más próxima y crea una versión. Todo o nada: 422 con la lista de filas con error |
| GET / PUT | `/api/projects/{id}/design-params` | Parámetros de diseño del proyecto (criterios, dotación, densidad, pérdidas, coeficientes, curva de modulación) con fuente y estado de verificación. Por defecto vienen del perfil y de las planillas de referencia, «no verificado» |

Las alertas de criterios y la factibilidad usan los parámetros del proyecto, no directamente el perfil.
