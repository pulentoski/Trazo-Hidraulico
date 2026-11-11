# Trazo Hidráulico — Etapas 1 a 5

Plataforma local para diseñar y simular redes de agua potable. Editor tipo CAD/GIS sobre OpenStreetMap o Google Maps,
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

El mapa base no necesita key: sin key de Google, el editor usa **OpenStreetMap** (MapLibre) con calles de OSM,
satélite opcional de **Esri World Imagery** (cada uno con su atribución) y búsqueda de direcciones con **Nominatim**.
En **Ajustes → Plataforma → Mapa base** el superadministrador elige el proveedor: *Automático* (Google si hay key; si no,
OpenStreetMap), *Google Maps* u *OpenStreetMap*. Si el navegador no tiene WebGL, el editor sigue sobre un lienzo
neutro. Para usar Google Maps:

1. En Google Cloud, habilite **Maps JavaScript API** (y **Geocoding API** para la búsqueda de dirección).
2. Cree una API key con **restricción de aplicación «Sitios web»** (el dominio publicado, o
   `http://localhost:8080/*` en local) y restrinja las APIs a las dos anteriores.
3. Ingrese como **superadministrador** y vaya a **Ajustes → Plataforma → Mapa base**: pegue la key (y, opcional, un
   Map ID vectorial para el tema oscuro), use «Probar» y «Guardar». Se guarda **cifrada** en la base con
   `SETTINGS_SECRET_KEY` (la genera `make env`) y el mapa se activa sin reconstruir contenedores; nunca se muestra
   completa. «Borrar» la quita.

Las variables `VITE_GOOGLE_MAPS_API_KEY` y `VITE_GOOGLE_MAPS_MAP_ID` del `.env` quedan solo como respaldo
(se incorporan al compilar con `make up`). La key es **única para toda la plataforma**; los usuarios no ingresan
keys propias.

### Acceso (usuarios propios)

Desde la etapa 5 la aplicación tiene usuarios, organizaciones y roles (ver [docs/autenticacion.md](docs/autenticacion.md)):

```bash
make create-admin    # superadministrador de plataforma (pide correo y contraseña)
make demo            # solo local: organización «Demo APR» con un usuario por rol (docs/demo.md)
```

Despliegue en una instancia Ubuntu: `deploy/instalar.sh` y [docs/despliegue.md](docs/despliegue.md).

### Basic auth (opcional, desactivado)

Barrera adicional en Caddy, desactivada por defecto (el acceso lo controla el ingreso propio). Para
activarla defina usuario y hash; con `BASIC_AUTH_ENABLED=true` y sin ellos el proxy no arranca.

```bash
docker run --rm -it caddy:2.11.9-alpine caddy hash-password   # pide la contraseña y entrega el hash bcrypt
```

En `.env` (el hash entre **comillas simples**, porque contiene `$`):

```
BASIC_AUTH_ENABLED=true
BASIC_AUTH_USER=equipo
BASIC_AUTH_HASH='$2a$14$...'
```

Además, la API limita las solicitudes a `/api` por IP (`RATE_LIMIT_PER_MINUTE`, 300 por minuto por
defecto; responde 429) y el tamaño del `.inp` importado (`MAX_INP_MB`, 20 MB; Caddy y la API
responden 413). `/healthz` queda sin autenticación para monitores externos.

## Levantar

```bash
make up           # construye y levanta todo; espera a que los 7 servicios estén healthy
```

Abra http://localhost:8080: la pantalla de inicio lista los proyectos recientes y permite crear,
importar `.inp`, ir a Ajustes. Cada proyecto se edita en `/proyecto/<id>`.
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
  digest) sirve las teselas en `/tiles/…`; funcionan sin key de Google. Subida por partes reanudable con progreso (límite `ORTHO_MAX_MB`, 2048 MB), reducción de resolución y
  asistente para ubicar fotos sin coordenadas con puntos de control; ortofotos grandes en [docs/despliegue.md](docs/despliegue.md).
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

## Panel general («Resumen») y paneles plegables

Detalle en [docs/resumen.md](docs/resumen.md): pestaña **Resumen** (primera al abrir un proyecto y botón en la barra
superior) con clientes, red, presiones, zonas por presión, clientes sobre cota, mayores consumidores, consumo y su
proyección, área operacional, pérdidas y agua no contabilizada, mantenimiento y plan de renovación, estanque y pozo,
y alertas; cada número enlaza a su lista y al mapa; exporta a PDF (HTML imprimible) y Excel. El panel derecho se
organiza en secciones plegables (se recuerda por usuario) y la barra de herramientas y el panel inferior se pliegan
para dar más espacio al mapa.

## Ajustes y animaciones

Una sola página **Ajustes** (`/ajustes/<sección>`, menú de usuario arriba a la derecha) con menú lateral según el rol:
**Mi cuenta** (todos: perfil, seguridad con contraseña, segundo factor y sesiones, y preferencias de tema, animaciones y
mapa), **Organización** (administrador: miembros e invitaciones, criterios de diseño por defecto, catálogos con vida
útil y precios por metro para los proyectos sin valores propios, uso y plan, auditoría) y **Plataforma**
(superadministrador: organizaciones y cuentas, mapa base, planes y límites, sistema con versión, motor OWA-EPANET y
SHA, estado de servicios y último respaldo). Las rutas antiguas (`/perfil`, `/organizacion`, `/plataforma`,
`/configuracion`, `/acerca-de`) redirigen a su sección. Animaciones sobrias (transiciones de 150–250 ms, conteo de
indicadores, dibujo de gráficos; en el mapa, flujo animado en el sentido del agua con velocidad según la velocidad del
tramo, pulso en nudos bajo la presión mínima, resaltado al seleccionar y «Reproducir día»): se desactivan en
Preferencias y respetan `prefers-reduced-motion`; solo se anima lo visible (≈ 60 cuadros/s con APR Demo y Net3).

Límite de solicitudes a `/api`: con sesión, por usuario (`RATE_LIMIT_USER_PER_MINUTE`, 1200 por minuto); sin sesión,
por IP (`RATE_LIMIT_PER_MINUTE`, 300) y el ingreso con su propio límite de intentos. Las teselas de ortofotos y las
partes de una subida no cuentan. Un 429 nunca cierra la sesión: la interfaz avisa «Demasiadas solicitudes,
reintentando…» y reintenta respetando `Retry-After`.

## Gestión del APR y coordenadas

Detalle en [docs/gestion.md](docs/gestion.md): página **Gestión** por proyecto (`/proyecto/:id/gestion`, botón en la
barra superior del editor y en cada proyecto del inicio) con 7 pestañas (operación, clientes y consumo, pérdidas,
activos y mantenimiento, cumplimiento, planificación y equipo), filtros de período, sector y ruta, indicadores con
variación y metas configurables («no verificado» hasta revisarlas), gráficos, tablas exportables (Excel/CSV), «ver en
el mapa» e informe mensual (HTML imprimible y Excel). Registros nuevos: energía, cloro, cortes, reclamos,
mantenciones/tareas y lecturas de clientes (formulario, plantilla, importación con vista previa y exportación; viajan
en el `.trazo`). En el mapa: búsqueda y creación por coordenadas (lat/lon, grados-minutos-segundos o UTM, huso 19S por
defecto), edición de las coordenadas de un elemento y barra con la coordenada del cursor.

## Publicar en un dominio con HTTPS

Lo más simple es el instalador para Ubuntu 22.04/24.04 (`deploy/instalar.sh`); la guía completa (instancia
mínima, puertos 22/80/443, DNS, modo sin dominio, actualización, respaldos y restauración en otra instancia) está
en [docs/despliegue.md](docs/despliegue.md). A mano:

1. En `.env`: `SITE_ADDRESS=trazo.midominio.cl`, `PUBLIC_URL=https://trazo.midominio.cl` y
   `MFA_REQUIRED_FOR_ADMINS=true`.
2. **Restrinja la key de Google Maps al dominio** (`https://trazo.midominio.cl/*`, solo Maps JavaScript y
   Geocoding).
3. `make up-public` (compose base + `compose.public.yml` + `compose.prod.yml`: HTTPS automático, HSTS, límites
   de recursos, logs con rotación y respaldo diario) y `make create-admin`.
4. Verifique `https://trazo.midominio.cl/healthz` y que `http://` redirige a `https://`.

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
- Etapa 5: contraseñas (Argon2id y política), sesión y cookie, bloqueo y límite de ingresos, TOTP, recuperación,
  invitaciones, roles, aislamiento entre organizaciones (lectura, edición, exportación, ortofotos y adivinanza de
  IDs), auditoría, uso, límites y suspensión.
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
