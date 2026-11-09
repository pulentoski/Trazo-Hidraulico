# Restaurar Trazo Hidráulico — respaldo @STAMP@

Respaldo creado con `make backup` (commit `@COMMIT@`).

| Archivo | Contenido |
|---|---|
| `trazo.dump` | Base de datos PostgreSQL/PostGIS (`pg_dump -Fc`) |
| `trazo.dump.list` | Índice del dump (`pg_restore --list`), para revisión |
| `ortofotos.tar.gz` | Archivos de las ortofotos (originales y COG) del volumen `ortho` |
| `imagenes-docker.tar.gz` | Imágenes api, web, worker, titiler, caddy, postgis y redis (`docker save`); listado en `imagenes-docker.txt` |
| `trazo-hidraulico.bundle` | Repositorio git completo, con todo el historial |
| `env` | Copia del `.env` (claves de PostgreSQL y Redis, key de Google, basic auth). **Confidencial** |
| `compose.offline.yml` | Override para levantar sin Internet (PostGIS por etiqueta en vez de digest) |
| `SHA256SUMS` | Sumas de verificación |

Requisitos del PC de destino: Docker Engine ≥ 24 con Compose v2, `git` y `make`.
En los comandos, `R` es la carpeta de este respaldo.

## 0. Verificar el respaldo

```bash
R=@DEST@          # o la ruta donde copió esta carpeta
cd "$R" && sha256sum -c SHA256SUMS
```

## 1. Código

```bash
git clone "$R/trazo-hidraulico.bundle" ~/Documentos/paginas/trazo-hidraulico
cd ~/Documentos/paginas/trazo-hidraulico
git remote set-url origin https://github.com/pulentoski/Trazo-Hidraulico.git
```

(Si la carpeta ya existe en este PC, puede omitir este paso o actualizarla con
`git fetch "$R/trazo-hidraulico.bundle" 'refs/heads/*:refs/remotes/respaldo/*'`.)

## 2. Configuración

```bash
cp "$R/env" .env && chmod 600 .env
```

Si cambia de dominio o de PC, revise en `.env`: `HTTP_PORT`, `SITE_ADDRESS`, `BASIC_AUTH_*` y la
restricción por dominio de la key de Google Maps.

## 3. Imágenes Docker

```bash
gunzip -c "$R/imagenes-docker.tar.gz" | docker load
```

## 4. Base de datos

La base se restaura sobre un volumen vacío (`trazo-hidraulico_pgdata`). **En este mismo PC esto borra
los datos actuales**: haga antes otro `make backup` si los necesita.

```bash
docker compose --env-file .env -f infra/compose.yml down
docker volume rm trazo-hidraulico_pgdata        # solo si existe y se quiere reemplazar
docker compose --env-file .env -f infra/compose.yml up -d --wait db
docker compose --env-file .env -f infra/compose.yml exec -T db \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' \
  < "$R/trazo.dump"
```

Sin Internet, agregue `-f "$R/compose.offline.yml"` después de `-f infra/compose.yml` en estos comandos
(y en el paso 5).

Ortofotos (volumen `trazo-hidraulico_ortho`):

```bash
docker compose --env-file .env -f infra/compose.yml run --rm --no-deps -T --entrypoint tar \
  api -C /data/ortho -xzf - < "$R/ortofotos.tar.gz"
```

Comprobación rápida:

```bash
docker compose --env-file .env -f infra/compose.yml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name, updated_at FROM project ORDER BY updated_at DESC"'
```

## 5. Levantar la aplicación

Con Internet (reconstruye a partir del código; lo habitual):

```bash
make up
```

Sin Internet (usa las imágenes cargadas, sin construir ni descargar):

```bash
docker compose --env-file .env -f infra/compose.yml -f "$R/compose.offline.yml" up -d --no-build --pull never --wait
```

Abra `http://localhost:<HTTP_PORT>` (8080 por defecto). Las migraciones pendientes, si el código es más
nuevo que el respaldo, se aplican solas al arrancar la API.

## 6. Pruebas (opcional)

```bash
make test   # reconstruye las imágenes de prueba (requiere Internet la primera vez)
```
