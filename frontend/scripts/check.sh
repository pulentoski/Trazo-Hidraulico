#!/bin/sh
# Verificación del frontend dentro del contenedor (sin red, sistema de archivos de solo lectura).
set -eu
echo "› tsc --noEmit"
./node_modules/.bin/tsc --noEmit
echo "› Tipos OpenAPI generados al día"
./node_modules/.bin/openapi-typescript src/api/openapi.json -o /tmp/schema.d.ts >/dev/null
diff -u src/api/schema.d.ts /tmp/schema.d.ts
echo "Frontend OK: tipos correctos y schema.d.ts al día."
