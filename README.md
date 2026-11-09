# Trazo Hidráulico — Etapas 1 a 4

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
make up           # construye y levanta todo; espera a que los 7 servicios estén healthy
```

Abra http://localhost:8080: la pantalla de inicio lista los proyectos recientes y permite crear,
importar `.inp`, ir a Configuración y a Acerca de. Cada proyecto se edita en `/proyecto/<id>`.
Comandos útiles: `make logs`, `make ps`, `make down`, `make reset-db`
(borra la base de datos) y `make gen-types` (regenera los tipos TypeScript desde OpenAPI).
`make backup` crea un respaldo local completo (base de datos, ortofotos, imágenes Docker, git bundle y copia del
`.env`) en `~/Documentos/respaldos/trazo-hidraulico/<fecha-hora>/`, con un `RESTAURAR.md` con los pasos.
La documentación interactiva de la API está en http://localhost:8080/api/docs.

## SIG de agua potable (etapa 2)

Detalle en [docs/sig.md](docs/sig.md). En resumen:

- **Planillas Excel**: plantilla descargable (una hoja por tipo de elemento + «Instrucciones», listas de
  validación), exportación del proyecto completo e importación en dos pasos (vista previa → aplicar, todo o
  nada, crea una versión). Actualiza por ID solo las columnas presentes; las columnas desconocidas quedan
  como atributos libres. También CSV por hoja. Menú **Planilla y SIG** del editor y «Crear desde Excel» en
  el inicio. Ejemplo: `examples/apr-demo.xlsx` (proyecto «APR Demo», La Serena).
- **Ortofotos** (pestaña Capas): GeoTIFF, JPG/PNG con archivo world o con puntos de control (error residual).
  El servicio `worker` (GDAL 3.10.3) genera un Cloud Optimized GeoTIFF y `tiler` (TiTiler 2.3.0, fijado por
  digest) sirve las teselas en `/tiles/…`; funcionan sin key de Google. Límite `MAX_ORTHO_MB` (500 MB).
- **Gestión**: estado, año y tipo de red en tramos; tipo, condición, diámetro y profundidad en válvulas;
  grifos (escenario de incendio) y pozos; datos comerciales de clientes.
- **Cuarteles de corta** (pestaña Cuarteles): válvulas a cerrar, metros de red y clientes sin agua (incluidos
  los de aguas abajo). Clic en un tramo → «Para cortar aquí, cierre …», exportable.
- **Consultas** (pestaña Consultas) con condiciones Y/O, resaltado en el mapa, sumas, consultas guardadas y
  exportación Excel/CSV; búsqueda rápida sobre el mapa.
- **Exportaciones**: DXF por capas en UTM y GeoPackage para QGIS.

## Etapa 3: .trazo, demanda, 24 h y gráficos

Detalle en [docs/etapa3.md](docs/etapa3.md): formato de proyecto `.trazo` (zip con .inp + JSON, ida y vuelta
sin pérdida; menú **Planilla y SIG** y la tarjeta de importación del inicio), importación .inp con [VERTICES],
[LABELS], [TAGS] y detección de UTM / lat-lon / locales, proyección de demanda y escenarios (pestaña Demanda),
simulación de 24 h con curvas de modulación, estanques, bombas con horario, control por nivel y curva de 1 o 3
puntos (pestaña Simulación y panel de la bomba), alertas de operación, gráficos con exportación PNG/CSV y
deslizador de hora en el mapa. Referencia SimulaEST1 en [docs/validation/simulaest1.md](docs/validation/simulaest1.md).

## Etapa 4: pozo y bombeo, mediciones y diagnóstico

Detalle en [docs/etapa4.md](docs/etapa4.md): cálculo de bombeo del pozo (altura manométrica, potencia, corriente
trifásica, velocidades; reproduce BombaPozo1) con ficha imprimible y curva de bomba, registro de mediciones con
comparación contra el modelo, diagnóstico automático con sugerencias verificadas por simulación e informe
técnico imprimible. `make test-e2e` hace el recorrido visual con Playwright (capturas en [docs/capturas/](docs/capturas/)).

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
make test        # backend y frontend en contenedores
make test-e2e    # recorrido visual con Playwright (con la pila levantada: make up)
```

Ejecuta todo dentro de contenedores y sin depender de Google:

- Referencia Net1/Net2/Net3: `runepanet` (compilado desde el tag v2.3.5) contra la API, en todos los pasos de reporte.
- Ida y vuelta `.inp` → base de datos → `.inp` → simulación.
- Validador (un caso por error y advertencia) y pruebas funcionales de la API.
- Batería QA hidráulica (`backend/tests/qa/`), protección (límite de solicitudes y de subida) y verificación de
  que las pruebas solo usan la base `trazo_test` y la base Redis 1 (abortan si no).
- SIG: ida y vuelta Excel sin cambios, errores por fila, actualización parcial, CSV/UTM, demostración «APR Demo»,
  cuarteles con resultado conocido, consultas con conteo esperado, grifos, DXF/GeoPackage (leídos con GDAL) y
  ortofotos (GeoTIFF, JPG + world y puntos de control en su posición, tolerancia 1 m).
- Etapa 3: SimulaEST1 (nivel horario contra la planilla), operación de bombas, alertas de período extendido,
  proyección contra la hoja de la planilla, escenarios de demanda, ida y vuelta .trazo, .inp con etiquetas en
  lat/lon y demo de 24 h.
- Etapa 4: BombaPozo1 (Hman 138,4 m, 12,3 kW), lecturas de medidor (15,49 L/s), comparación con tolerancias,
  diagnóstico con sugerencia verificada e informe técnico.
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
