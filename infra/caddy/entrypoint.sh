#!/bin/sh
# Valida la configuración del proxy antes de arrancar Caddy. Desde la etapa 5 el acceso lo controla la
# autenticación propia de la aplicación; el basic auth queda como barrera adicional opcional (desactivada).
set -eu

fail() {
	echo "" >&2
	echo "ERROR (proxy): $1" >&2
	echo "  Revise .env y el README (sección «Publicar»). Para desarrollo local: BASIC_AUTH_ENABLED=false" >&2
	echo "" >&2
	exit 64
}

enabled="${BASIC_AUTH_ENABLED:-false}"
case "$enabled" in
	true | false) ;;
	*) fail "BASIC_AUTH_ENABLED debe ser true o false (valor actual: '$enabled')." ;;
esac

if [ "$enabled" = true ]; then
	missing=""
	[ -n "${BASIC_AUTH_USER:-}" ] || missing="$missing BASIC_AUTH_USER"
	[ -n "${BASIC_AUTH_HASH:-}" ] || missing="$missing BASIC_AUTH_HASH"
	[ -z "$missing" ] || fail "basic auth activo pero falta definir:$missing. Genere el hash con: docker run --rm caddy:2.11.9-alpine caddy hash-password"
	case "$BASIC_AUTH_USER" in
		*[[:space:]]*) fail "BASIC_AUTH_USER no puede contener espacios." ;;
	esac
	case "$BASIC_AUTH_HASH" in
		'$2a$'* | '$2b$'* | '$2y$'*) ;;
		*) fail "BASIC_AUTH_HASH no es un hash bcrypt (debe empezar con \$2a\$, \$2b\$ o \$2y\$). En .env escríbalo entre comillas simples." ;;
	esac
fi

case "${TLS_MODE:-auto}" in
	auto | internal) ;;
	*) fail "TLS_MODE debe ser auto (Let's Encrypt) o internal (certificado propio de Caddy)." ;;
esac
case "${HSTS_ENABLED:-false}" in
	true | false) ;;
	*) fail "HSTS_ENABLED debe ser true o false." ;;
esac

# Nombre del certificado para clientes sin SNI (acceso por IP): host de SITE_ADDRESS sin esquema ni puerto.
sni="${SITE_ADDRESS:-}"
sni="${sni#*://}"; sni="${sni%%/*}"; sni="${sni%:*}"
export CADDY_DEFAULT_SNI="${sni:-localhost}"

export BASIC_AUTH_ENABLED="$enabled"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
