# Modelo de datos (PostgreSQL 16 + PostGIS 3.4)

| Tabla | Contenido |
|---|---|
| `project` | Nombre, descripción, `length_srid` (32719 por defecto), perfil de diseño |
| `project_version` | **Inmutable**. Número correlativo por proyecto, tipo (`auto`/`manual`/`import`), etiqueta, opciones hidráulicas (JSONB), secciones complementarias del `.inp` (patrones, curvas, controles, reglas, tiempos, energía, calidad), huella SHA-256 |
| `network_node` | `junction` / `reservoir` / `tank`; `geom Point(4326)`; cota = `elevation` + `elevation_source` (`manual`/`inp`/`supuesta`) + `elevation_method`; demanda base y categorías; carga del reservorio; niveles y diámetro del estanque |
| `network_link` | `pipe` / `pump` / `valve`; `geom LineString(4326)` con vértices, separada de la topología (`from_node_id`, `to_node_id`); DN, diámetro interior, material, clase, ítem de catálogo, rugosidad, pérdidas menores, estado inicial; `length_plan_m`, `length_slope_m`, `length_hydraulic_m` y `length_choice` (`plan`/`slope`/`manual`) |
| `catalog_pipe` | PVC (C6, C10, C16) y HDPE PE100 (PN10, PN16): DN, clase, DE, espesor, diámetro interior, C de H-W, ε de D-W (mm), n de Manning. **Valores referenciales no verificados** |
| `design_profile` | Criterios con nombre, fuente, versión, vigencia, límites y unidades. Estado inicial «no verificado» |
| `simulation_run` | Ligada a `project_version`: motor (wheel, SHA, `EN_getversion`), opciones, huella del `.inp`, mensajes traducidos, pasos de reporte, tiempo de cálculo |
| `result_node` | Por corrida, nudo y periodo: demanda (L/s), cota piezométrica (m), presión (m) |
| `result_link` | Por corrida, tramo y periodo: caudal (L/s), velocidad (m/s), pérdida (m/km en tuberías), estado |

La rugosidad cambia de significado según la fórmula de la versión: C (H-W), ε en mm (D-W) o n (C-M). Al cambiar la
fórmula, el editor recalcula la rugosidad de los tramos ligados al catálogo y advierte sobre los tramos personalizados.

Migraciones en `backend/migrations/versions/` (Alembic): `0001` esquema y triggers de inmutabilidad; `0002` catálogo y perfil.

## Etapa clientes y operación

| Tabla / columna | Contenido |
|---|---|
| `network_client` | Clientes por versión (inmutable): punto, conexión sobre la tubería, nudo asignado (`node_id`), tipo, estado, consumo en su unidad y en L/s, cota opcional |
| `network_shutoff` | Llaves de corte por versión (inmutable): tubería (`link_id`), posición 0–1, estado abierta/cerrada, punto |
| `project_version.scenarios` | Escenarios de llaves `[{id, name, closed}]` de la versión |
| `project.design_params` | Parámetros de diseño editados en el proyecto (solo los que difieren de los valores por defecto) |
| `network_link.inner_diameter_source` | `catalogo` o `manual` |
| `catalog_pipe.review` | Observaciones de revisión (catálogo ModeloPozo); `od_mm`/`wall_mm` pasan a ser opcionales |

El catálogo incluye las 62 combinaciones material × clase × DN de `docs/referencias/ModeloPozo.xlsx`
(hoja «D=Interiores»: AC, Acero, FFD, HA, PEAD y PVC; PN10 y PN16), con fuente «Planilla ModeloPozo
(ingeniero hidráulico), no verificado» y rugosidades típicas por material también no verificadas. La
planilla se lee con `app/data/modelopozo.py` (evalúa las fórmulas y respeta las celdas vacías), se congela
en `app/data/catalogo_modelopozo.json` y la carga la migración 0003. Las filas dudosas se listan en
[validation/catalogo-modelopozo-revision.md](validation/catalogo-modelopozo-revision.md).
