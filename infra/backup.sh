#!/usr/bin/env bash
# Respaldo local completo de Trazo Hidráulico: base de datos, imágenes Docker, código (git bundle) y .env.
#
# Uso: make backup   (o BACKUP_ROOT=/otra/ruta make backup)
# Destino: $BACKUP_ROOT/<AAAA-MM-DD_HHMMSS>/  (por defecto /home/luna/Documentos/respaldos/trazo-hidraulico)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-/home/luna/Documentos/respaldos/trazo-hidraulico}"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"
COMPOSE=(docker compose --env-file .env -f infra/compose.yml)
# Imágenes necesarias para levantar la pila sin construir ni descargar (las de prueba se reconstruyen con make test).
IMAGES=(trazo-hidraulico/api:local trazo-hidraulico/web:local trazo-hidraulico/worker:local caddy:2.11.9-alpine
        postgis/postgis:16-3.4 redis:7.4.12-alpine ghcr.io/developmentseed/titiler:2.3.0)

step() { printf '\n› %s\n' "$*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

[ -f .env ] || fail "no existe .env (ejecute make env)"
umask 077
mkdir -p "$DEST"
chmod 700 "$BACKUP_ROOT" "$DEST" 2>/dev/null || true

step "Base de datos (pg_dump formato custom)"
"${COMPOSE[@]}" up -d --wait db >/dev/null
"${COMPOSE[@]}" exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$DEST/trazo.dump"
[ -s "$DEST/trazo.dump" ] || fail "el dump quedó vacío"
# Verificación: el dump se puede leer (lista de contenido) y contiene las tablas principales.
"${COMPOSE[@]}" exec -T db pg_restore --list < "$DEST/trazo.dump" > "$DEST/trazo.dump.list"
for t in project project_version network_node network_link network_client network_hydrant network_well orthophoto \
         saved_query catalog_pipe simulation_run; do
  grep -qE "TABLE DATA public $t " "$DEST/trazo.dump.list" || fail "el dump no contiene la tabla $t"
done
echo "  $(grep -c ';' "$DEST/trazo.dump.list") entradas en el índice; tablas principales presentes."

step "Ortofotos (volumen de almacenamiento, tar.gz)"
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint tar api -C /data/ortho -czf - . > "$DEST/ortofotos.tar.gz"
gzip -t "$DEST/ortofotos.tar.gz" || fail "el archivo de ortofotos está dañado"
echo "  $(tar -tzf "$DEST/ortofotos.tar.gz" | grep -c 'cog.tif$' || true) ortofotos procesadas; $(du -h "$DEST/ortofotos.tar.gz" | cut -f1)."

step "Imágenes Docker (docker save | gzip)"
for img in "${IMAGES[@]}"; do
  docker image inspect "$img" >/dev/null 2>&1 || fail "no existe la imagen $img (ejecute make up)"
done
docker save "${IMAGES[@]}" | gzip -6 > "$DEST/imagenes-docker.tar.gz"
gzip -t "$DEST/imagenes-docker.tar.gz"
docker image inspect --format '{{index .RepoTags 0}} {{.Id}}' "${IMAGES[@]}" > "$DEST/imagenes-docker.txt"

step "Código (git bundle con todo el historial)"
git bundle create "$DEST/trazo-hidraulico.bundle" --all 2>/dev/null
git bundle verify "$DEST/trazo-hidraulico.bundle" >/dev/null 2>&1 || fail "git bundle verify falló"
COMMIT="$(git rev-parse --short HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  echo "  Aviso: hay cambios sin commit; el bundle contiene solo lo confirmado (HEAD $COMMIT)."
fi

step "Configuración (.env, permisos 600)"
cp .env "$DEST/env"
chmod 600 "$DEST/env"

# Override para restaurar sin Internet: docker load no conserva el digest con que compose.yml fija PostGIS.
cat > "$DEST/compose.offline.yml" <<'EOF'
# Usar solo al restaurar sin acceso a Internet (imágenes cargadas con docker load).
services:
  db:
    image: postgis/postgis:16-3.4
EOF

step "Instrucciones (RESTAURAR.md)"
sed -e "s|@STAMP@|$STAMP|g" -e "s|@COMMIT@|$COMMIT|g" -e "s|@DEST@|$DEST|g" infra/RESTAURAR.template.md > "$DEST/RESTAURAR.md"

(cd "$DEST" && sha256sum trazo.dump ortofotos.tar.gz imagenes-docker.tar.gz trazo-hidraulico.bundle env compose.offline.yml > SHA256SUMS)
chmod 600 "$DEST"/*

# Si se ejecuta como root (p. ej. con sudo), los archivos quedan del dueño del repositorio.
if [ "$(id -u)" = 0 ]; then
  OWNER="$(stat -c %u:%g "$ROOT")"
  chown "$OWNER" "$BACKUP_ROOT" && chown -R "$OWNER" "$DEST"
fi

step "Respaldo listo en $DEST"
(cd "$DEST" && ls -l --block-size=K | awk 'NR>1 {printf "  %-28s %10s\n", $9, $5}')
echo "  Total: $(du -sh "$DEST" | cut -f1)"
