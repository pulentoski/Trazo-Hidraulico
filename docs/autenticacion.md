# Autenticación, organizaciones y permisos (etapa 5)

## Usuarios y sesión

- Cuentas con correo y contraseña **Argon2id** (64 MiB, 3 pasadas, 4 hilos; se rehace el hash si cambian los
  parámetros). Política: al menos 10 caracteres (`PASSWORD_MIN_LENGTH`), letras y números, no común ni
  repetitiva, sin el correo.
- **Bloqueo temporal**: tras `LOGIN_MAX_ATTEMPTS` (5) intentos fallidos la cuenta se bloquea
  `LOGIN_LOCKOUT_MINUTES` (15). Además, máximo `LOGIN_RATE_PER_MINUTE` (10) intentos de ingreso por IP y
  minuto (Redis). El mensaje no revela si el correo existe.
- **Sesión**: cookie `trazo_session` `HttpOnly`, `Secure`, `SameSite=Strict`, expira en `SESSION_HOURS` (12 h).
  El token es opaco; en la base (`user_session`) solo se guarda su SHA-256. Se puede cerrar la sesión, una sesión
  concreta o todas (perfil). Cambiar o restablecer la contraseña cierra las demás sesiones. `SameSite=Strict`
  impide el envío de la cookie desde otros sitios (CSRF).
- **Segundo factor TOTP** (RFC 6238, compatible con Google/Microsoft Authenticator): opcional por usuario y
  obligatorio para administradores de organización y superadministradores (`MFA_REQUIRED_FOR_ADMINS`). Sin
  configurarlo, la API solo permite `/api/auth/*` y la interfaz lleva a **Ajustes → Seguridad** (`/ajustes/seguridad`).
- **Recuperación**: con SMTP configurado, `/recuperar` envía un enlace de un solo uso (24 h). Sin SMTP, el
  administrador de la organización (o el superadministrador) genera el enlace y lo entrega por otro medio.
- **Primer superadministrador**: `make create-admin` (pide correo y contraseña; o `EMAIL=… PASSWORD=…`).

## Organizaciones y roles

Cada proyecto pertenece a una organización (APR, consultora o sanitaria). Un usuario puede pertenecer a varias
y elige la activa en el menú de usuario. Roles por organización:

| Rol | Ver y exportar | Simular | Editar e importar | Revisar versiones | Miembros, auditoría, uso |
|---|:-:|:-:|:-:|:-:|:-:|
| lector | ✔ | ✔ | | | |
| revisor | ✔ | ✔ | | ✔ | |
| proyectista | ✔ | ✔ | ✔ | | |
| administrador | ✔ | ✔ | ✔ | ✔ | ✔ |

- **Aislamiento estricto**: una dependencia global resuelve la sesión y `get_project_or_404` verifica la
  membresía en la organización del proyecto en cada ruta. Un proyecto ajeno responde **404** (igual que uno
  inexistente: no se pueden adivinar IDs) y un rol sin permiso, **403**. Las ortofotos, sus archivos, las
  teselas (vía `forward_auth` de Caddy) y todas las exportaciones pasan por el mismo filtro. Las pruebas de
  `backend/tests/test_etapa5.py` recorren lectura, edición, exportación y adivinanza de IDs entre dos
  organizaciones.
- **Invitaciones** por correo o enlace de un solo uso: vencen a los **7 días**, se listan las vigentes y se pueden
  anular. Máximo de invitaciones por día por organización (10 por defecto, configurable por plan).
- **Usuarios por plan**: tope de usuarios activos (más invitaciones vigentes). Al llegar al tope, «Invitar» queda
  deshabilitado con el aviso «Su plan permite N usuarios»; la API responde 403 al invitar, aceptar una invitación o
  reactivar a un miembro por sobre el tope.

### Roles y permisos (validados en cada endpoint)

| Acción | Super Admin | Admin de organización | Proyectista / revisor / lector |
|---|---|---|---|
| Crear, suspender y eliminar organizaciones | sí (suspender y eliminar exigen escribir el nombre) | no (404) | no |
| Planes y límites (de cada plan y por organización) | sí | no (422/404) | no |
| Mapa base de la plataforma | sí | no | no |
| Entrar a una organización como soporte | sí, queda en la auditoría (`soporte.entrada/salida`, cada acción con `soporte: true`) | no | no |
| Nombrar o quitar Super Admin | sí (no a sí mismo) | no | no |
| Invitar, desactivar y cambiar roles | en cualquier organización | solo la suya, hasta Admin | no (403) |
| Editar nombre y datos de la organización | sí | sí (`PATCH /api/orgs/{id}`: nombre, tipo, RUT, contacto…) | no (403) |

Reglas comunes: nadie asigna ni invita con un rol superior al propio (jerarquía lector < revisor < proyectista <
admin); siempre queda al menos un Admin activo (no se puede degradar, desactivar ni suspender la cuenta del último);
el administrador de una organización no puede cambiar el rol ni desactivar a un Super Admin; todo cambio queda en la
auditoría. Las pruebas de cada regla, incluidos los intentos de escalar privilegios, están en
`backend/tests/test_roles_limites.py`.

- **Super Admin** (**Panel admin**, `/panel-admin`; antes «Ajustes → Plataforma», la ruta `/plataforma` redirige):
  resumen (organizaciones activas y suspendidas, usuarios, disco y ortofotos, organizaciones cerca de su límite,
  últimos eventos de auditoría), organizaciones con su ficha (datos, plan, uso contra límites, usuarios con rol y
  último ingreso; cambiar plan, suspender, eliminar y entrar como soporte), planes y límites, usuarios, mapa base y
  sistema. No ve proyectos de una organización si no es miembro, salvo en modo soporte (aviso fijo arriba con
  «Salir del modo soporte»).

## Auditoría y uso

- `audit_log`: ingresos (correctos, fallidos, bloqueos, segundo factor), cierres de sesión, cada versión nueva
  de la red (quién, versión, tipo, etiqueta), importaciones y exportaciones (ruta), invitaciones, cambios de rol
  y estado, enlaces de recuperación y revisiones. Visible para el administrador de la organización.
- Uso por organización y mes: simulaciones ejecutadas (no las reutilizadas de caché), cargas del mapa de
  Google (contadas por el frontend) y almacenamiento de ortofotos. Límites por plan (básico, profesional,
  ilimitado) con valores personalizables; al superarlos la API responde 403 y el mapa usa el lienzo neutro.

## API

`/api/auth/{login,mfa,logout,logout-all,me,org,support/exit,password,mfa/setup,mfa/enable,mfa/disable,sessions,recover,reset,
invitation/{token}}`, `/api/orgs/{id}` (GET/PATCH), `/api/orgs/{id}/{members,invitations,audit,usage}`,
`/api/admin/{overview,plans,orgs,orgs/{id},orgs/{id}/support,users}`,
`/api/usage/map-load` y `/api/projects/{id}/versions/{n}/reviews`. Documentación interactiva en `/api/docs`.
