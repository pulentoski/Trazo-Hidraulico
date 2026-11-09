# Trazo Hidráulico — Etapa 1

Plataforma local para diseñar y simular redes de agua potable. Editor tipo CAD/GIS sobre Google Maps,
motor hidráulico **OWA-EPANET 2.3.5** en el backend (único motor), resultados reproducibles y ligados
a versiones inmutables del modelo. Unidades SI, caudal en L/s.

## Requisitos

- Ubuntu con Docker Engine ≥ 24 y Docker Compose v2
- `make` y `openssl`
- Puerto 8080 libre en 127.0.0.1 (configurable con `HTTP_PORT`)

## Configurar `.env`

```bash
make env          # crea .env desde .env.example con claves aleatorias para PostgreSQL y Redis
```

Google Maps es opcional. Sin key, el editor y la simulación funcionan igual sobre un lienzo neutro
y se muestra un aviso en lugar del mapa. Para usar el mapa base:

1. En Google Cloud, habilite **Maps JavaScript API** (y **Geocoding API** para la búsqueda de dirección).
2. Cree una API key con **restricción de aplicación «Sitios web»** y agregue solo
   `http://localhost:8080/*` y `http://127.0.0.1:8080/*`. Restrinja también las APIs a las dos anteriores.
3. (Opcional) Cree un Map ID vectorial para el tema oscuro del mapa.
4. Edite `.env`:
   ```
   VITE_GOOGLE_MAPS_API_KEY=su-key
   VITE_GOOGLE_MAPS_MAP_ID=su-map-id
   ```
   Estas variables se incorporan al compilar el frontend: después de cambiarlas ejecute `make up`.

## Levantar

```bash
make up           # construye y levanta todo; espera a que los 5 servicios estén healthy
```

Abra http://localhost:8080. Comandos útiles: `make logs`, `make ps`, `make down`, `make reset-db`
(borra la base de datos) y `make gen-types` (regenera los tipos TypeScript desde OpenAPI).
La documentación interactiva de la API está en http://localhost:8080/api/docs.

## Probar

```bash
make test
```

Ejecuta todo dentro de contenedores y sin depender de Google:

- Referencia Net1/Net2/Net3: `runepanet` (compilado desde el tag v2.3.5) contra la API, en todos los pasos de reporte.
- Ida y vuelta `.inp` → base de datos → `.inp` → simulación.
- Validador (un caso por error y advertencia) y pruebas funcionales de la API.
- Frontend: `tsc --noEmit` y verificación de que `schema.d.ts` está al día con OpenAPI.

Los resultados y las tolerancias quedan en [`docs/validation/`](docs/validation/tolerancias.md).

## Uso rápido del editor

| Tecla | Herramienta | | Tecla | Acción |
|---|---|---|---|---|
| V | Seleccionar | | Ctrl+Z / Ctrl+Y | Deshacer / rehacer |
| B | Selección múltiple (caja) | | Ctrl+S | Guardar versión |
| N / E / R | Nudo / Estanque / Reservorio | | F5 | Simular ahora |
| T | Tubería (clics = vértices, doble clic termina) | | Supr | Eliminar selección |
| M | Mover (nudos y vértices) | | Esc | Cancelar dibujo |
| X / D | Eliminar / Medir | | Rueda / arrastre | Zoom / desplazar |

Cada cambio se guarda automáticamente (versión nueva) y se simula 400 ms después; el estado
(sin cambios / calculando / actualizado / error) se ve en la barra superior.

## Estructura

```
backend/   API FastAPI (app/{routers,services,repositories,schemas,models,hydraulic,validators,core}), migraciones, pruebas
frontend/  React + TypeScript + Vite (servido por nginx-unprivileged)
infra/     compose.yml y Caddyfile
docs/      arquitectura, modelo de datos, API y validación del motor
examples/  Net1.inp, Net2.inp y Net3.inp del repositorio oficial (tag v2.3.5)
```
