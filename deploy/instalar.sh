#!/usr/bin/env bash
# Instalación de Trazo Hidráulico en Ubuntu 22.04 / 24.04 limpio.
#
#   curl -fsSL https://raw.githubusercontent.com/pulentoski/Trazo-Hidraulico/main/deploy/instalar.sh -o instalar.sh
#   sudo bash instalar.sh
#
# Instala Docker, clona el repositorio en /opt/trazo-hidraulico, crea .env de forma interactiva (dominio o IP,
# key de Google, correo y contraseña del superadministrador, correo saliente), levanta con `make up-public` y
# crea el superadministrador.
#
# Sin preguntas (p. ej. por ssh sin terminal): `sudo -E bash instalar.sh --no-interactivo` (o TRAZO_NONINTERACTIVE=1)
# con las variables TRAZO_*; las que falten toman su valor por defecto:
#   TRAZO_MODE=1|2|3            1 dominio + Let's Encrypt · 2 https://IP con certificado interno · 3 http://IP (pruebas)
#   TRAZO_DOMAIN                dominio (modo 1)
#   TRAZO_IP                    IP pública (modos 2 y 3; por defecto se detecta)
#   TRAZO_MFA_ADMINS=true|false segundo factor obligatorio para administradores (por defecto true)
#   TRAZO_GOOGLE_KEY            key de Google Maps (opcional)
#   TRAZO_ADMIN_EMAIL           correo del superadministrador (obligatorio)
#   TRAZO_ADMIN_PASSWORD        su contraseña; sin ella, en modo no interactivo se genera una aleatoria y se
#                               muestra UNA vez al final
#   TRAZO_SMTP_HOST/PORT/USER/PASSWORD/FROM   correo saliente (opcional)
set -euo pipefail

NONINTERACTIVE="${TRAZO_NONINTERACTIVE:-0}"
for arg in "$@"; do
	case "$arg" in
		--no-interactivo | --non-interactive | -y) NONINTERACTIVE=1 ;;
		*) echo "Opción desconocida: $arg" >&2; exit 2 ;;
	esac
done
[ -r /dev/tty ] && { : </dev/tty; } 2>/dev/null || NONINTERACTIVE=1  # sin terminal: no se puede preguntar

REPO_URL="${TRAZO_REPO_URL:-https://github.com/pulentoski/Trazo-Hidraulico.git}"
DIR="${TRAZO_DIR:-/opt/trazo-hidraulico}"
BRANCH="${TRAZO_BRANCH:-main}"

say() { printf '\n\033[1;34m› %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*" >&2; }
die() { printf '\033[1;31m✖ %s\033[0m\n' "$*" >&2; exit 1; }
ask() {  # ask VAR "Pregunta" "valor por defecto"
	local __var=$1 __q=$2 __def=${3:-} __val
	if [ -n "${!__var+x}" ]; then return; fi  # definida (aunque sea vacía): no se pregunta
	if [ "$NONINTERACTIVE" = 1 ]; then printf -v "$__var" '%s' "$__def"; return; fi
	read -r -p "$__q${__def:+ [$__def]}: " __val </dev/tty || true
	printf -v "$__var" '%s' "${__val:-$__def}"
}
ask_secret() {  # ask_secret VAR "Pregunta" (con confirmación)
	local __var=$1 __q=$2 a b
	if [ -n "${!__var:-}" ]; then return; fi
	[ "$NONINTERACTIVE" = 0 ] || die "Falta $__var (modo no interactivo)."
	while :; do
		read -r -s -p "$__q: " a </dev/tty; echo
		read -r -s -p "Repita: " b </dev/tty; echo
		[ "$a" = "$b" ] && [ ${#a} -ge 10 ] && break
		warn "No coinciden o tiene menos de 10 caracteres (use letras y números)."
	done
	printf -v "$__var" '%s' "$a"
}
set_env() {  # set_env CLAVE VALOR  (reemplaza o agrega en .env; valores con $ entre comillas simples)
	local k=$1 v=$2 line
	if [[ "$v" == *'$'* || "$v" == *' '* ]]; then line="$k='$v'"; else line="$k=$v"; fi
	if grep -qE "^$k=" .env; then
		local tmp; tmp=$(mktemp)
		awk -v k="$k" -v l="$line" 'BEGIN{FS="="} $1==k {print l; next} {print}' .env > "$tmp" && cat "$tmp" > .env && rm -f "$tmp"
	else
		echo "$line" >> .env
	fi
}

[ "$(id -u)" -eq 0 ] || die "Ejecute con sudo: sudo bash instalar.sh"
. /etc/os-release
case "${VERSION_ID:-}" in 22.04|24.04) ;; *) warn "Probado en Ubuntu 22.04 y 24.04 (detectado: ${PRETTY_NAME:-desconocido})." ;; esac

say "Paquetes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git make openssl gnupg >/dev/null

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
	say "Docker Engine y Compose (repositorio oficial de Docker)"
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
		> /etc/apt/sources.list.d/docker.list
	apt-get update -qq
	apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
	systemctl enable --now docker
fi
docker compose version

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
	say "Cortafuegos (ufw): puertos 22, 80 y 443"
	ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
fi

say "Código en $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone --branch "$BRANCH" "$REPO_URL" "$DIR"; fi
cd "$DIR"

say "Configuración (.env)"
make env >/dev/null
chmod 600 .env
IP="${TRAZO_IP:-$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')}"
echo "Modos de publicación:"
echo "  1) Dominio con HTTPS automático (Let's Encrypt) — recomendado; el DNS debe apuntar a $IP"
echo "  2) Sin dominio: HTTPS por IP con certificado interno de Caddy (el navegador mostrará una advertencia)"
echo "  3) Sin dominio: HTTP por IP — SOLO PRUEBAS: contraseñas y sesiones viajan sin cifrar"
ask TRAZO_MODE "Modo (1, 2 o 3)" "1"
case "$TRAZO_MODE" in
	1) ask TRAZO_DOMAIN "Dominio (p. ej. trazo.miapr.cl)" ""
	   [ -n "$TRAZO_DOMAIN" ] || die "Indique el dominio."
	   SITE="$TRAZO_DOMAIN"; URL="https://$TRAZO_DOMAIN"
	   set_env TLS_MODE auto; set_env HSTS_ENABLED true; set_env COOKIE_SECURE true ;;
	2) SITE="https://$IP"; URL="https://$IP"
	   set_env TLS_MODE internal; set_env HSTS_ENABLED false; set_env COOKIE_SECURE true ;;
	3) SITE="http://$IP"; URL="http://$IP"
	   warn "Modo HTTP sin cifrado: úselo solo para pruebas en una red de confianza."
	   set_env TLS_MODE auto; set_env HSTS_ENABLED false; set_env COOKIE_SECURE false ;;
	*) die "Modo no válido." ;;
esac
set_env SITE_ADDRESS "$SITE"
set_env PUBLIC_URL "$URL"
set_env BASIC_AUTH_ENABLED false
set_env MFA_REQUIRED_FOR_ADMINS "${TRAZO_MFA_ADMINS:-true}"

ask TRAZO_GOOGLE_KEY "Key de Google Maps (opcional; restrinja la key a $URL/*)" ""
[ -z "$TRAZO_GOOGLE_KEY" ] || set_env VITE_GOOGLE_MAPS_API_KEY "$TRAZO_GOOGLE_KEY"
ask TRAZO_ADMIN_EMAIL "Correo del superadministrador" ""
[ -n "$TRAZO_ADMIN_EMAIL" ] || die "Indique el correo del superadministrador."
GENERATED_PW=0
if [ -z "${TRAZO_ADMIN_PASSWORD:-}" ] && [ "$NONINTERACTIVE" = 1 ]; then
	TRAZO_ADMIN_PASSWORD="Th-$(openssl rand -base64 33 | tr -dc 'A-Za-z0-9' | head -c 24)-9"; GENERATED_PW=1
fi
ask_secret TRAZO_ADMIN_PASSWORD "Contraseña del superadministrador (mín. 10, letras y números)"
ask TRAZO_SMTP_HOST "Servidor SMTP para correos (opcional; vacío = enlaces generados por el administrador)" ""
if [ -n "$TRAZO_SMTP_HOST" ]; then
	ask TRAZO_SMTP_PORT "Puerto SMTP" "587"
	ask TRAZO_SMTP_USER "Usuario SMTP" ""
	ask_secret TRAZO_SMTP_PASSWORD "Contraseña SMTP"
	ask TRAZO_SMTP_FROM "Remitente" "$TRAZO_ADMIN_EMAIL"
	set_env SMTP_HOST "$TRAZO_SMTP_HOST"; set_env SMTP_PORT "$TRAZO_SMTP_PORT"; set_env SMTP_USER "$TRAZO_SMTP_USER"
	set_env SMTP_PASSWORD "$TRAZO_SMTP_PASSWORD"; set_env SMTP_FROM "$TRAZO_SMTP_FROM"
fi

say "Respaldos diarios en /var/backups/trazo-hidraulico"
mkdir -p /var/backups/trazo-hidraulico
chown 999:999 /var/backups/trazo-hidraulico
chmod 700 /var/backups/trazo-hidraulico
set_env BACKUP_DIR /var/backups/trazo-hidraulico
chown -R "$(stat -c %u:%g "$DIR")" "$DIR" 2>/dev/null || true

say "Construyendo y levantando (varios minutos la primera vez)"
make up-public

say "Superadministrador"
# Por el entorno (no como argumento de make): admite cualquier carácter y no queda en la lista de procesos.
TRAZO_ADMIN_EMAIL="$TRAZO_ADMIN_EMAIL" TRAZO_ADMIN_PASSWORD="$TRAZO_ADMIN_PASSWORD" make create-admin </dev/null

say "Verificación"
CURL_K=; [ "$TRAZO_MODE" = 2 ] && CURL_K=-k
for i in $(seq 1 30); do
	if curl -fsS $CURL_K --max-time 5 "$URL/healthz" >/dev/null 2>&1; then echo "  $URL/healthz responde"; break; fi
	[ "$i" = 30 ] && warn "$URL/healthz no responde todavía: revise 'make ps' y 'make logs'."
	sleep 2
done

say "Listo"
echo "  Sitio:      $URL"
echo "  Estado:     $URL/healthz"
echo "  Ingreso:    $TRAZO_ADMIN_EMAIL$([ "${TRAZO_MFA_ADMINS:-true}" = true ] && echo ' (configure el segundo factor al ingresar)')"
[ "$GENERATED_PW" = 1 ] && echo "  Contraseña: $TRAZO_ADMIN_PASSWORD   ← generada; se muestra solo esta vez: cámbiela en /perfil"
echo "  Desbloquear una cuenta:  cd $DIR && make unlock-user EMAIL=correo"
echo "  Cambiar una contraseña:  cd $DIR && make reset-password EMAIL=correo"
echo "  Respaldos:  /var/backups/trazo-hidraulico (diario a las 03:30; verifique con: cd $DIR && make restore-test)"
echo "  Actualizar: cd $DIR && git pull && make up-public"
[ "$TRAZO_MODE" = 3 ] && warn "Recuerde: modo HTTP sin cifrado. Pase a un dominio con HTTPS antes de usarlo en producción."
[ "$TRAZO_MODE" = 2 ] && warn "Certificado interno: el navegador mostrará una advertencia de seguridad hasta que use un dominio."
exit 0
