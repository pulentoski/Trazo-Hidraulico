# Despliegue en una instancia Ubuntu

## Instancia mínima recomendada

| Uso | vCPU | RAM | Disco |
|---|---|---|---|
| Una APR, pocas ortofotos | 2 | 4 GB | 40 GB SSD |
| Consultora con varias organizaciones y ortofotos | 4 | 8 GB | 100 GB SSD + disco de respaldos |

Ubuntu 22.04 o 24.04 LTS limpio. Las ortofotos (COG) y los respaldos son lo que más disco ocupa.

## Red y DNS

- Puertos de entrada: **22** (SSH, idealmente solo desde su IP), **80** (emisión del certificado y redirección a
  HTTPS) y **443** (TCP y UDP para HTTP/3). Nada más: la base de datos, Redis, la API, el worker y TiTiler quedan
  en redes internas de Docker y no publican puertos.
- DNS: un registro `A` (y `AAAA` si tiene IPv6) del dominio apuntando a la IP pública. Espere a que propague
  antes de instalar (`dig +short trazo.miapr.cl`).

## Instalación

```bash
curl -fsSL https://raw.githubusercontent.com/pulentoski/Trazo-Hidraulico/main/deploy/instalar.sh -o instalar.sh
sudo bash instalar.sh
```

El script instala Docker (repositorio oficial), clona el repositorio en `/opt/trazo-hidraulico`, crea `.env` con
claves aleatorias y le pregunta:

1. **Modo de publicación**
   - *Dominio* (recomendado): HTTPS automático con Let's Encrypt, HSTS activo.
   - *Sin dominio, HTTPS por IP*: certificado interno de Caddy (`TLS_MODE=internal`). El navegador muestra una
     advertencia porque el certificado no es de una autoridad pública. Sirve para pruebas internas.
   - *Sin dominio, HTTP por IP*: **solo pruebas**. Las contraseñas y la cookie de sesión viajan sin cifrar
     (`COOKIE_SECURE=false`). No lo use con datos reales.
2. Key de Google Maps (opcional; restrínjala a `https://su-dominio/*`).
3. Correo y contraseña del superadministrador.
4. Servidor SMTP (opcional): sin correo saliente, los administradores generan enlaces de un solo uso para
   invitar y recuperar contraseñas.

Luego ejecuta `make up-public` (compose base + `compose.public.yml` + `compose.prod.yml`),
`make create-admin` y comprueba `/healthz`.

### Instalación sin preguntas (por ssh, sin terminal)

```bash
git clone https://github.com/pulentoski/Trazo-Hidraulico.git /tmp/trazo && cd /tmp/trazo
sudo TRAZO_MODE=2 TRAZO_MFA_ADMINS=false TRAZO_GOOGLE_KEY= TRAZO_SMTP_HOST= \
     TRAZO_ADMIN_EMAIL=admin@ejemplo.cl bash deploy/instalar.sh --no-interactivo
```

Con `--no-interactivo` (o `TRAZO_NONINTERACTIVE=1`, o si no hay terminal) el script no pregunta: las variables
`TRAZO_*` no definidas toman su valor por defecto y una variable definida vacía cuenta como respondida. Sin
`TRAZO_ADMIN_PASSWORD` genera una contraseña aleatoria fuerte y la muestra **una sola vez** al final. Lista
completa de variables en el encabezado de `deploy/instalar.sh`.

### Acceso por IP sin dominio (`TRAZO_MODE=2`)

Caddy emite un certificado propio para la IP (`TLS_MODE=internal`) y redirige el puerto 80 al 443. El navegador
muestra «La conexión no es privada»: en Chrome/Edge, **Configuración avanzada → Continuar a IP (no seguro)**; en
Firefox, **Avanzado… → Aceptar el riesgo y continuar**. Con curl: `curl -k https://IP/healthz`. La cookie de
sesión sigue siendo `Secure` (la conexión es HTTPS).

**IP pública que cambia** (AWS sin IP elástica: cambia cada vez que la instancia se detiene y arranca, p. ej. en
sesiones de laboratorio de 4 h): si no se indica `TRAZO_IP`, el instalador deja activo `trazo-ip.timer`, que al
arrancar y cada 5 minutos ejecuta `deploy/actualizar-ip.sh`: consulta la IP pública (metadatos de la instancia o
ipify) y, si cambió, reescribe `SITE_ADDRESS` y `PUBLIC_URL` en `.env` y recrea el proxy y la API (Caddy emite el
certificado interno para la IP nueva). Manual: `make actualizar-ip`. Registro: `journalctl -u trazo-ip`.
Tras un cambio de IP el navegador vuelve a pedir que acepte el certificado. Para una dirección estable, asocie una
IP elástica o use un dominio.

Al primer ingreso, el superadministrador debe configurar el segundo factor (TOTP) en **/perfil** si
`MFA_REQUIRED_FOR_ADMINS=true` (por defecto). Después crea las organizaciones en **/plataforma** e invita a
sus administradores.

## Producción (`infra/compose.prod.yml`)

- Límites de CPU y memoria por servicio (`API_CPUS`, `API_MEMORY`, `DB_MEMORY` ajustables en `.env`).
- `restart: always` y logs `json-file` con rotación (5 × 10 MB por servicio).
- Healthchecks en todos los servicios; `make up-public` espera a que estén sanos.
- Servicio `backup`: respaldo diario a las `BACKUP_TIME` (03:30, hora de `TZ`) con retención de
  `BACKUP_RETENTION_DAYS` días (14) en `BACKUP_DIR` (`/var/backups/trazo-hidraulico`).

## Seguridad

- Autenticación propia (ver [autenticacion.md](autenticacion.md)): Argon2id, bloqueo temporal tras 5 intentos,
  límite de 10 ingresos por minuto e IP, cookie `HttpOnly` + `Secure` + `SameSite=Strict`, TOTP para
  administradores. El basic auth de Caddy quedó como barrera adicional opcional (`BASIC_AUTH_ENABLED=false`).
- Cabeceras (Caddy): `Content-Security-Policy` (solo orígenes propios y los de Google Maps; `frame-ancestors
  'none'`, `object-src 'none'`), `Strict-Transport-Security` de un año con dominio (`HSTS_ENABLED=true`),
  `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy`, `Permissions-Policy` y `Cache-Control: no-store` en `/api`.
  `'unsafe-eval'` en `script-src` lo exige Google Maps JavaScript API; sin key de Google puede quitarse.
- Las teselas de ortofotos pasan por `forward_auth`: la API verifica que la sesión vea el proyecto de la
  ortofoto antes de que Caddy consulte a TiTiler.
- Aislamiento multiempresa: toda consulta a un proyecto se filtra por la organización del usuario; un proyecto
  ajeno responde 404 (igual que uno inexistente). Lo verifican las pruebas de `backend/tests/test_etapa5.py`.

## Monitoreo básico

- **Estado**: `https://su-dominio/healthz` responde `{"api":"ok","db":"ok","cache":"ok"}` (503 si algo falla),
  sin autenticación. Configure un monitor externo (UptimeRobot, Healthchecks.io, Uptime Kuma) cada 1–5 min.
- **Contenedores**: `make ps` (todos «healthy»); `make logs` o `docker compose ... logs -f api`.
- **Disco**: vigile `/var/lib/docker` (ortofotos) y `/var/backups/trazo-hidraulico` (`df -h`).
- **Respaldos**: `docker compose ... logs backup` muestra «listo …» cada día; verifíquelos con
  `make restore-test` (mensual como mínimo).
- **Seguridad**: el registro de auditoría de cada organización (Organización → Auditoría) muestra ingresos,
  ingresos fallidos y bloqueos, cambios de red, importaciones, exportaciones y cambios de permisos.
- **Uso**: el superadministrador ve en **/plataforma** simulaciones, cargas de mapa y ortofotos por
  organización, con los límites del plan.

## Cuentas desde la consola del servidor

```bash
cd /opt/trazo-hidraulico
make create-admin                         # crea o actualiza el superadministrador (pide correo y contraseña)
make unlock-user EMAIL=correo@dominio     # quita el bloqueo por intentos fallidos (423)
make reset-password EMAIL=correo@dominio  # contraseña nueva pedida sin eco; desbloquea y cierra sus sesiones
```

## Problemas de ingreso

| Síntoma | Causa | Solución |
|---|---|---|
| «Cuenta bloqueada temporalmente…» (HTTP 423) | 5 intentos fallidos (`LOGIN_MAX_ATTEMPTS`) bloquean la cuenta `LOGIN_LOCKOUT_MINUTES` (15) min. El bloqueo se guarda en la base (`app_user.locked_until`), por eso **reiniciar la API no lo quita**. | Esperar, o `make unlock-user EMAIL=…` |
| Contraseña olvidada sin correo saliente | Sin SMTP no llega el enlace de recuperación | Otro administrador genera un enlace, o `make reset-password EMAIL=…` |
| El ingreso «se queda pegado» o vuelve al formulario | Sitio abierto por `http://` con `COOKIE_SECURE=true`: el navegador descarta la cookie `Secure` y cada consulta posterior responde 401. | Entrar por `https://`. Para modo HTTP de pruebas, `COOKIE_SECURE=false` (el instalador lo pone en el modo 3; `make up-public` ahora se niega a arrancar con `http://` y cookie `Secure`, y la API deja una advertencia en su log cuando la cookie no es `Secure`). La pantalla de ingreso ahora lo explica en vez de quedarse esperando. |
| «Demasiados intentos de ingreso desde esta dirección» (429) | Más de `LOGIN_RATE_PER_MINUTE` (10) ingresos por minuto desde la misma IP | Esperar un minuto |
| Consultas SQL directas fallan con «relation "users" does not exist» | La tabla de usuarios se llama **`app_user`** (sesiones: `user_session`, membresías: `membership`) | Use los comandos `make` de arriba en lugar de SQL a mano |

La pantalla de ingreso muestra un mensaje específico para 401 (credenciales o sesión perdida), 423 (bloqueo),
código TOTP incorrecto, servidor inaccesible y cookie de sesión no guardada.

## Correcciones de la primera instalación real (noviembre 2026)

Primera prueba de `deploy/instalar.sh` en una instancia AWS limpia (Ubuntu, acceso por IP con certificado interno):

- **Modo no interactivo**: el script preguntaba por `/dev/tty` incluso cuando la variable estaba definida vacía
  (key de Google, SMTP), y fallaba sin terminal. Ahora acepta `--no-interactivo`, detecta la falta de terminal,
  respeta variables vacías y genera la contraseña del superadministrador si no se entrega.
- **Contraseña del superadministrador**: se pasaba como argumento de `make` (se rompía con `$`, comillas o
  espacios y quedaba visible en la lista de procesos). Ahora va por variable de entorno y `make create-admin`
  usa `exec -T` cuando no hay terminal.
- **Bloqueo y contraseña**: nuevos `make unlock-user` y `make reset-password` (antes había que editar la tabla a
  mano, y la tabla no se llama `users` sino `app_user`).
- **Cookie en HTTP**: verificación en `make up-public`, advertencia en el log de la API y mensaje claro en la
  pantalla de ingreso.
- **IP dinámica**: la instancia cambia de IP pública cada 4 h; `trazo-ip.timer` + `deploy/actualizar-ip.sh`
  mantienen `SITE_ADDRESS` y `PUBLIC_URL` al día sin intervención.
- **Verificación**: el instalador comprueba `/healthz` al terminar e indica los comandos de cuentas.
- **e2e contra una instancia**: `make test-e2e BASE_URL=https://IP E2E_SHOTS=/tmp/capturas` acepta el
  certificado interno y no ensucia `docs/capturas` del servidor.

## Actualización

```bash
cd /opt/trazo-hidraulico
git pull
make up-public        # reconstruye, aplica migraciones al arrancar la API y espera a que todo esté sano
```

Antes de actualizar, haga un respaldo inmediato: `make backup-now`.

## Respaldos y restauración

- Automático: servicio `backup` (diario, con retención). Inmediato: `make backup-now`.
- Completo manual (incluye imágenes Docker, `.env` y el código): `make backup` → `~/Documentos/respaldos/…` con
  un `RESTAURAR.md` paso a paso.
- **Prueba de restauración** (documentada y automatizada): `make restore-test` toma el último respaldo,
  verifica sus sumas SHA-256, lo restaura en una base temporal `trazo_restore_test`, cuenta proyectos,
  versiones y usuarios, comprueba que el archivo de ortofotos se pueda leer y elimina la base temporal.
  Resultado esperado: «restauración verificada desde … N proyectos, M versiones, K usuarios».

### Restaurar en otra instancia

1. Instale la nueva instancia con `deploy/instalar.sh` (mismo modo de publicación).
2. Copie el respaldo: `rsync -a vieja:/var/backups/trazo-hidraulico/<fecha>/ /tmp/respaldo/`.
3. Copie también `.env` de la instancia anterior (contiene las claves) o mantenga el nuevo y restaure solo datos.
4. Restaure la base y las ortofotos:
   ```bash
   cd /opt/trazo-hidraulico
   C="docker compose --env-file .env -f infra/compose.yml"
   $C stop api worker
   $C exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < /tmp/respaldo/trazo.dump
   $C run --rm --no-deps -T --entrypoint tar api -C /data/ortho -xzf - < /tmp/respaldo/ortofotos.tar.gz
   make up-public
   ```
5. Ingrese y revise proyectos, ortofotos y el registro de auditoría.
