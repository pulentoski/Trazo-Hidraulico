#!/usr/bin/env bash
# Pruebas de deploy/actualizar-ip.sh con curl y docker simulados (sin red ni Docker reales).
# Uso: make test-deploy (corre dentro de un contenedor).
set -euo pipefail
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/actualizar-ip.sh"
fallos=0

preparar() {  # preparar SITE_ADDRESS IP_PUBLICA CONTENEDORES_CREATED
	T=$(mktemp -d)
	mkdir -p "$T/infra/caddy" "$T/bin"
	echo caddy > "$T/infra/caddy/Caddyfile"; echo entry > "$T/infra/caddy/entrypoint.sh"
	printf 'SITE_ADDRESS=%s\nPUBLIC_URL=%s\nOTRA=1\n' "$1" "$1" > "$T/.env"
	cat > "$T/bin/curl" <<EOF
#!/bin/sh
case "\$*" in *api/token*) echo tok ;; *public-ipv4*) echo "$2" ;; *) exit 7 ;; esac
EOF
	cat > "$T/bin/docker" <<EOF
#!/bin/sh
echo "\$*" >> "$T/docker.log"
case "\$*" in *" ps "*) [ -n "$3" ] && printf '%s\n' $3 ;; esac
exit 0
EOF
	chmod +x "$T/bin/curl" "$T/bin/docker"
	: > "$T/docker.log"
}
correr() { PATH="$T/bin:$PATH" TRAZO_DIR="$T" bash "$SCRIPT" > "$T/salida.txt" 2>&1; }
ok() { echo "  ✔ $1"; }
mal() { echo "  ✖ $1"; fallos=$((fallos + 1)); }
levanto() { grep -q " up -d " "$T/docker.log"; }

echo "› actualizar-ip.sh"

preparar https://1.2.3.4 1.2.3.4 ""; correr
if levanto; then mal "misma IP y pila sana: no debe recrear"; else ok "misma IP y pila sana: no hace nada"; fi

preparar https://1.2.3.4 5.6.7.8 ""; correr
if grep -qx 'SITE_ADDRESS=https://5.6.7.8' "$T/.env" && grep -qx 'PUBLIC_URL=https://5.6.7.8' "$T/.env" \
	&& grep -qx 'OTRA=1' "$T/.env" && levanto; then ok "IP nueva: reescribe .env y levanta la pila"; else mal "IP nueva"; cat "$T/salida.txt"; fi

preparar https://1.2.3.4 1.2.3.4 "abc123 def456"; correr
if levanto && grep -q "interrumpida" "$T/salida.txt"; then ok "misma IP con contenedores «created»: levanta la pila"
else mal "actualización interrumpida no se recupera"; cat "$T/salida.txt"; fi

preparar midominio.cl 5.6.7.8 "abc123"; correr
if ! levanto && grep -qx 'SITE_ADDRESS=midominio.cl' "$T/.env"; then ok "con dominio: no hace nada"; else mal "con dominio"; fi

preparar http://1.2.3.4 5.6.7.8 ""; correr
if grep -qx 'SITE_ADDRESS=http://5.6.7.8' "$T/.env" && levanto; then ok "http://IP conserva el esquema"; else mal "http://IP"; fi

[ "$fallos" -eq 0 ] || { echo "✖ $fallos prueba(s) fallaron"; exit 1; }
echo "✔ deploy: todas las pruebas pasaron."
