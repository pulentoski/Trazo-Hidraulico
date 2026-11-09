#!/usr/bin/env bash
# Mantiene SITE_ADDRESS y PUBLIC_URL al día cuando la instancia no tiene IP fija (sin dominio ni IP elástica:
# en AWS la IP pública cambia cada vez que la instancia se detiene y vuelve a arrancar).
# Lo ejecuta el temporizador systemd trazo-ip.timer (al arrancar y cada 5 min) o `make actualizar-ip`.
# Solo actúa si SITE_ADDRESS es https://IP o http://IP; con dominio no hace nada.
set -euo pipefail
DIR="${TRAZO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$DIR"
cur=$(grep -E '^SITE_ADDRESS=' .env | cut -d= -f2- | tr -d "'\"" || true)
case "$cur" in https://* | http://*) scheme=${cur%%://*}; host=${cur#*://} ;; *) exit 0 ;; esac
[[ "$host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 0

tok=$(curl -fsS -X PUT --max-time 2 -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
	http://169.254.169.254/latest/api/token 2>/dev/null || true)
ip=$(curl -fsS --max-time 2 ${tok:+-H "X-aws-ec2-metadata-token: $tok"} \
	http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)
[[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)
[[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "trazo-ip: no se pudo detectar la IP pública" >&2; exit 1; }
[ "$ip" = "$host" ] && exit 0

sed -i -E "s|^SITE_ADDRESS=.*|SITE_ADDRESS=$scheme://$ip|; s|^PUBLIC_URL=.*|PUBLIC_URL=$scheme://$ip|" .env
echo "trazo-ip: la IP pública cambió de $host a $ip; actualizando el proxy y la API"
CADDY_CONFIG_HASH=$(cat infra/caddy/Caddyfile infra/caddy/entrypoint.sh | sha256sum | cut -c1-16)
export CADDY_CONFIG_HASH
docker compose --env-file .env -f infra/compose.yml -f infra/compose.public.yml -f infra/compose.prod.yml \
	up -d --no-build --wait --wait-timeout 300
