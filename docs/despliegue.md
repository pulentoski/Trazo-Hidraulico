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

Luego ejecuta `make up-public` (compose base + `compose.public.yml` + `compose.prod.yml`) y
`make create-admin`. Para instalar sin preguntas defina `TRAZO_MODE`, `TRAZO_DOMAIN`, `TRAZO_ADMIN_EMAIL`,
`TRAZO_ADMIN_PASSWORD`, etc. (ver el encabezado del script).

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
