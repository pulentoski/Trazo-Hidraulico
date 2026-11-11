#!/usr/bin/env bash
# Prueba de una ortofoto grande (≈ 800 MB): genera un GeoTIFF sintético con GDAL en un contenedor, lo sube por
# partes a la pila levantada, espera el procesamiento y mide tiempos y memoria: la de los procesos (memoria anónima
# del cgroup, muestreada cada 0,5 s) y memory.peak (incluye la caché de disco). La API y el worker se reinician
# antes para medir solo esta prueba.
# Uso: make test-ortho-grande   (resultado en docs/validation/ortofoto-grande.md)
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose --env-file .env -f infra/compose.yml"
TMP=e2e/tmp
SIDE=${ORTHO_TEST_SIDE:-16700}  # 16700² píxeles RGB sin comprimir ≈ 798 MB
NAME=ortofoto-grande-$SIDE.tif
TIF=$TMP/$NAME
mkdir -p "$TMP" docs/validation docs/capturas
if [ ! -s "$TIF" ]; then
  echo "› generando $TIF (${SIDE}×${SIDE} RGB, 5 cm/píxel) con GDAL"
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD/$TMP:/out" -e PYTHONPATH=/app --entrypoint python trazo-hidraulico/worker:local -c "
import subprocess, numpy as np
from pyproj import Transformer
e, n = Transformer.from_crs('EPSG:4326', 'EPSG:32719', always_xy=True).transform(-71.1450, -29.9420)
y, x = np.mgrid[0:1024, 0:1024]
r = (128 + 90 * np.sin(x / 37.0) * np.cos(y / 53.0)).astype(np.uint8)
g = (128 + 80 * np.sin((x + y) / 71.0)).astype(np.uint8)
b = (110 + 60 * np.cos(x / 23.0 - y / 41.0)).astype(np.uint8)
open('/out/semilla.ppm', 'wb').write(b'P6 1024 1024 255\n' + np.dstack([r, g, b]).tobytes())
side, res = $SIDE, 0.05
subprocess.run(['gdal_translate', '-q', '-of', 'GTiff', '-outsize', str(side), str(side), '-r', 'bilinear',
                '-a_srs', 'EPSG:32719', '-a_ullr', str(e - 200), str(n + 200), str(e - 200 + side * res), str(n + 200 - side * res),
                '-co', 'BIGTIFF=YES', '-co', 'TILED=YES', '/out/semilla.ppm', '/out/$NAME'], check=True)
"
  rm -f "$TMP/semilla.ppm"
fi
SIZE_MB=$(( $(stat -c %s "$TIF") / 1024 / 1024 ))
echo "› archivo de prueba: $SIZE_MB MB"
echo "› reiniciando api y worker (memoria pico desde cero)"
$COMPOSE restart api worker >/dev/null
$COMPOSE up -d --wait api worker >/dev/null
$COMPOSE exec -T api python -m app.cli ensure-user --email "${E2E_EMAIL:-e2e@trazo.local}" --password "${E2E_PASSWORD:-Recorrido-e2e-2026}" --org "Recorrido e2e" --role admin >/dev/null
docker build -q -t trazo-hidraulico/e2e:local e2e >/dev/null

anon() { docker exec "trazo-hidraulico-$1-1" sh -c 'grep -E "^anon " /sys/fs/cgroup/memory.stat' 2>/dev/null | awk '{printf "%.0f", $2/1048576}'; }
peak() { docker exec "trazo-hidraulico-$1-1" cat /sys/fs/cgroup/memory.peak 2>/dev/null | awk '{printf "%.0f", $1/1048576}'; }
SAMPLES=$TMP/memoria.txt
: > "$SAMPLES"
( while true; do echo "$(anon worker) $(anon api)" >> "$SAMPLES"; sleep 0.5; done ) &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null || true' EXIT

START=$(date +%s)
LOG=$(docker run --rm --network host --ipc=host -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/repo" -w /repo \
  trazo-hidraulico/e2e:local python3 e2e/ortofoto_grande.py "$TIF" docs/capturas/ortofoto-grande.png | tee /dev/stderr)
TOTAL=$(( $(date +%s) - START ))
kill $SAMPLER 2>/dev/null || true
ANON_W=$(awk '$1>m{m=$1} END{print m+0}' "$SAMPLES")
ANON_A=$(awk '$2>m{m=$2} END{print m+0}' "$SAMPLES")
RES=$(echo "$LOG" | sed -n 's/^RESULTADO //p')
FREE=$(df -BG --output=avail /var/lib/docker 2>/dev/null | tail -1 | tr -d ' ')
cat > docs/validation/ortofoto-grande.md <<MD
# Prueba de ortofoto grande

Fecha: $(date '+%Y-%m-%d %H:%M') · equipo: $(nproc) CPU, $(free -g | awk '/Mem:/{print $2}') GB RAM · \`make test-ortho-grande\`

GeoTIFF sintético generado con GDAL (${SIDE}×${SIDE} píxeles RGB, 5 cm/píxel, sin comprimir): **${SIZE_MB} MB**.
Subida por partes a través de Caddy (con un corte simulado al 30 % y retoma desde la última parte confirmada),
procesamiento en el worker (gdalwarp → COG EPSG:3857, WEBP calidad 85 con overviews, GDAL_CACHEMAX y -wm de
${ORTHO_GDAL_CACHEMAX_MB:-256} MB) y teselas servidas por TiTiler.

| Medida | Valor |
|---|---|
| Resultado (JSON) | \`$RES\` |
| Duración total de la prueba | ${TOTAL} s |
| Pico de memoria de procesos del worker (GDAL; anónima, muestreo 0,5 s) | ${ANON_W} MB |
| Pico de memoria de procesos de la API (recepción de partes) | ${ANON_A} MB |
| Pico del cgroup del worker con caché de disco (memory.peak) | $(peak worker) MB |
| Pico del cgroup de la API con caché de disco (memory.peak) | $(peak api) MB |
| Espacio libre tras la prueba | ${FREE} |

La caché de disco (escritura del original y del COG) se cuenta en memory.peak, pero el kernel la libera cuando
falta memoria: el límite de memoria de cada contenedor debe cubrir la memoria de procesos con holgura.

Captura: [ortofoto-grande.png](../capturas/ortofoto-grande.png)
MD
echo "› resultado en docs/validation/ortofoto-grande.md"
cat docs/validation/ortofoto-grande.md
