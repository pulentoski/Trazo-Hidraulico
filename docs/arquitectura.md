# Arquitectura (etapa 1)

```
navegador ──► proxy (Caddy :8080, solo 127.0.0.1) ──┬─► web  (nginx-unprivileged, SPA React)
                                                    └─► api  (FastAPI + OWA-EPANET 2.3.5) ──┬─► db    (PostgreSQL 16 + PostGIS 3.4)
                                       red "front"                          red "back" (interna) └─► cache (Redis 7)
```

- Todos los contenedores corren sin root, con `read_only`, `cap_drop: ALL` y `no-new-privileges`, y tienen healthcheck.
- La red `back` es interna: la base de datos y Redis no tienen salida a Internet ni puertos publicados.
- Caddy agrega CSP compatible con Google Maps, `X-Frame-Options: DENY`, `nosniff` y `Referrer-Policy`.

## Motor hidráulico

`backend/app/hydraulic/` es el único lugar que habla con el motor:

| Módulo | Función |
|---|---|
| `inp_writer.py` | Modelo de dominio → `.inp` en SI (L/s, m). H-W/D-W/C-M, DDA/PDA, `STATISTIC NONE` |
| `inp_reader.py` | `.inp` → modelo. El motor convierte las unidades; la estructura se lee con getters (doble precisión) |
| `engine.py` | `EN_runproject` (mismo camino que `runepanet`) en un directorio temporal propio |
| `out_reader.py` | Lector del binario `.out` (todos los pasos de reporte) |
| `messages.py` | Traducción al español: presiones negativas, desequilibrio, nudos desconectados, bombas y válvulas fuera de operación, errores de entrada |
| `version.py` | Identidad del motor: versión del wheel, SHA del tag compilado, banner de `runepanet` |

El frontend no calcula nada: solo dibuja la red y los resultados que entrega la API.

## Versionado y reproducibilidad

- `PUT /network` crea siempre una **versión nueva inmutable** (`project_version`), salvo un guardado automático
  idéntico a la versión anterior (misma huella SHA-256). Triggers de PostgreSQL impiden modificar versiones, red y resultados.
- `POST /simulate` recibe `model_version`. La corrida (`simulation_run`) guarda la versión del motor, las opciones,
  la huella del `.inp` generado y los mensajes; los resultados por nudo y tramo quedan en `result_node` y `result_link`.
- Si la versión ya tiene una corrida con el mismo motor, se reutiliza. Redis guarda resultados por huella del `.inp`.

## Simulación casi en vivo (frontend)

`frontend/src/state/live.ts`: cada cambio confirmado incrementa la revisión local → 400 ms sin cambios → guardado
automático (versión N) → simulación de N. Durante el arrastre no se calcula. Al llegar la respuesta, se descarta si la
versión o la revisión ya no son las vigentes. Hay una sola operación en curso; los cambios que llegan mientras tanto
programan otro ciclo.

## Georreferenciación

- Coordenadas en EPSG:4326. Los largos en planta se calculan en el SRID métrico del proyecto (`LENGTH_SRID`, 32719 por defecto).
- Largo con pendiente = √(planta² + Δz²) con las cotas de los nudos. El largo hidráulico usado se elige por tramo:
  planta, con pendiente o manual (las redes importadas conservan el largo del `.inp`).
- Importación: si las coordenadas parecen UTM se transforman desde el SRID del proyecto; si no, se tratan como locales,
  se escalan según la mediana de largo/distancia y se ubican en el centro configurado. La exportación escribe coordenadas UTM.
