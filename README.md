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

La key es **única para toda la plataforma** (la define quien administra el servidor). La pantalla
Configuración solo indica si está configurada; nunca la muestra.

### Acceso (basic auth)

Mientras no existan usuarios (etapa 5, ver [docs/autenticacion.md](docs/autenticacion.md)), todo el
sitio queda protegido con basic auth en Caddy. **Sin usuario y hash definidos, `make up` y el proxy
no arrancan** y explican qué falta.

```bash
docker run --rm -it caddy:2.11.9-alpine caddy hash-password   # pide la contraseña y entrega el hash bcrypt
```

En `.env` (el hash entre **comillas simples**, porque contiene `$`):

```
BASIC_AUTH_ENABLED=true
BASIC_AUTH_USER=equipo
BASIC_AUTH_HASH='$2a$14$...'
```

Solo para desarrollo local en su propio equipo puede desactivarse con `BASIC_AUTH_ENABLED=false`.

Además, la API limita las solicitudes a `/api` por IP (`RATE_LIMIT_PER_MINUTE`, 300 por minuto por
defecto; responde 429) y el tamaño del `.inp` importado (`MAX_INP_MB`, 20 MB; Caddy y la API
responden 413). `/healthz` queda sin autenticación para monitores externos.

## Levantar

```bash
make up           # construye y levanta todo; espera a que los 5 servicios estén healthy
```

Abra http://localhost:8080: la pantalla de inicio lista los proyectos recientes y permite crear,
importar `.inp`, ir a Configuración y a Acerca de. Cada proyecto se edita en `/proyecto/<id>`.
Comandos útiles: `make logs`, `make ps`, `make down`, `make reset-db`
(borra la base de datos) y `make gen-types` (regenera los tipos TypeScript desde OpenAPI).
La documentación interactiva de la API está en http://localhost:8080/api/docs.

## Publicar en un dominio con HTTPS

Caddy obtiene y renueva el certificado automáticamente (Let's Encrypt) cuando el sitio tiene un
dominio. Requisitos: un servidor con IP pública, un registro DNS `A`/`AAAA` del dominio apuntando a
él y los puertos **80 y 443** abiertos (80 es necesario para emitir el certificado y redirigir a HTTPS).

1. En `.env`:
   ```
   SITE_ADDRESS=trazo.midominio.cl
   BASIC_AUTH_ENABLED=true
   BASIC_AUTH_USER=equipo
   BASIC_AUTH_HASH='$2a$14$...'
   ```
2. **Restrinja la key de Google Maps al dominio**: en Google Cloud → Credenciales → la key →
   «Sitios web», reemplace las entradas de localhost por `https://trazo.midominio.cl/*` (y solo las
   APIs Maps JavaScript y Geocoding). Una key sin restricción publicada en un sitio puede ser usada
   por terceros con cargo a su cuenta.
3. Publique:
   ```bash
   make up-public
   ```
   Usa `infra/compose.public.yml`: publica 80/443 en todas las interfaces, guarda los certificados en
   un volumen persistente (`caddy_data`) y exige basic auth. La base de datos, Redis y la API siguen
   sin exponerse.
4. Verifique `https://trazo.midominio.cl` (pide usuario y contraseña) y que `http://` redirige a `https://`.

Copie también `.env` fuera del servidor de forma segura: contiene las claves de PostgreSQL y Redis.

## Probar

```bash
make test
```

Ejecuta todo dentro de contenedores y sin depender de Google:

- Referencia Net1/Net2/Net3: `runepanet` (compilado desde el tag v2.3.5) contra la API, en todos los pasos de reporte.
- Ida y vuelta `.inp` → base de datos → `.inp` → simulación.
- Validador (un caso por error y advertencia) y pruebas funcionales de la API.
- Batería QA hidráulica (`backend/tests/qa/`), protección (límite de solicitudes y de subida) y verificación de
  que las pruebas solo usan la base `trazo_test` y la base Redis 1 (abortan si no).
- Frontend: `tsc --noEmit`, pruebas unitarias (vitest) y verificación de que `schema.d.ts` está al día con OpenAPI.

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
| C | Cliente (se conecta a la tubería más cercana: nudo cercano o nudo nuevo) | | | |
| L | Llave de corte sobre una tubería | | | |
| F | Factibilidad de un nuevo cliente (no modifica el proyecto) | | | |

En el panel inferior, **Clientes** permite importar un CSV (`lat, lon, nombre, consumo` en L/s;
opcionales `tipo, estado, unidad`) y exportar la tabla; **Escenarios** simula llaves cerradas
(operación normal, todas cerradas o escenarios propios), lista los clientes sin suministro o bajo la
presión mínima (exportable a CSV), compara dos escenarios y resalta en el mapa los sectores sin agua.
Los parámetros de diseño (presión mínima, dotación, pérdidas, curva de modulación…) se editan por
proyecto en el panel Proyecto; los valores por defecto son típicos y están marcados «no verificado».

Cada cambio se guarda automáticamente (versión nueva) y se simula 400 ms después; el estado
(sin cambios / calculando / actualizado / error) se ve en la barra superior.

## Estructura

```
backend/   API FastAPI (app/{routers,services,repositories,schemas,models,hydraulic,validators,core}), migraciones, pruebas
frontend/  React + TypeScript + Vite (servido por nginx-unprivileged)
infra/     compose.yml, compose.public.yml (dominio + HTTPS) y Caddy (Caddyfile, entrypoint.sh)
docs/      arquitectura, modelo de datos, API, validación del motor y plan de autenticación
examples/  Net1.inp, Net2.inp y Net3.inp del repositorio oficial (tag v2.3.5)
```
