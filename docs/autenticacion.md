# Plan de autenticación (etapa 5)

## Situación actual (temporal)

- Todo el sitio está detrás de **basic auth en Caddy** (un usuario compartido definido en `.env`).
  Sin credenciales el proxy no arranca; en desarrollo local puede desactivarse con `BASIC_AUTH_ENABLED=false`.
- La API limita solicitudes por IP (`RATE_LIMIT_PER_MINUTE`) y el tamaño del `.inp` (`MAX_INP_MB`).
- No hay usuarios en la base de datos: todos los proyectos son visibles para quien pasa el basic auth.
- La key de Google Maps es única para la plataforma (servidor) y está restringida por dominio.

## Objetivo de la etapa 5

Usuarios propios con sesión, proyectos con dueño y permisos, sin depender del basic auth.

### Backend

1. **Modelo**: tablas `app_user` (id, email único, nombre, hash de contraseña Argon2id, rol
   `admin | usuario`, activo, creado, último ingreso) y `project_member` (proyecto, usuario,
   rol `dueño | editor | lector`). `project.owner_id` para los proyectos nuevos; migración que
   asigna los proyectos existentes a un administrador inicial.
2. **Sesión**: cookie `HttpOnly`, `Secure`, `SameSite=Lax` con identificador de sesión opaco
   guardado en Redis (expiración deslizante, p. ej. 12 h; revocable). Se prefiere a JWT porque
   permite cerrar sesión y revocar de inmediato. Protección CSRF con encabezado propio
   (`X-Trazo-CSRF`) validado contra la sesión en métodos que modifican datos.
3. **Rutas**: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`,
   `POST /api/auth/password` (cambio). Alta de usuarios solo por administradores
   (`/api/admin/users`); sin registro abierto.
4. **Autorización**: dependencia FastAPI `current_user` en todos los routers; filtros por
   pertenencia en proyectos, versiones, corridas y exportación. 404 (no 403) para proyectos ajenos.
5. **Abuso**: límite de intentos de ingreso por IP y por cuenta (Redis), retardo progresivo y
   registro de eventos de seguridad. Se mantiene el límite general de `/api`.

### Frontend

- La estructura ya está preparada (`frontend/src/routes.tsx`): las rutas de trabajo cuelgan de
  `<RequireAuth>`, que hoy deja pasar todo. En la etapa 5:
  - se agrega la ruta pública `/login` (`PATHS.login`);
  - `RequireAuth` consulta `GET /api/auth/me` (estado en el store) y redirige a
    `/login?volver=<ruta>` si no hay sesión;
  - la pantalla de inicio muestra «Mis proyectos» y «Compartidos conmigo»;
  - Configuración → Administración pasa de informativa a gestión de usuarios (solo `admin`).
- El cliente API trata 401 redirigiendo a `/login` y conserva el trabajo no guardado.

### Transición

1. Desplegar usuarios con basic auth aún activo (doble barrera) y crear las cuentas.
2. Verificar permisos con pruebas de API (usuario sin acceso a proyecto ajeno, lector sin escritura).
3. Desactivar el basic auth (`BASIC_AUTH_ENABLED=false` solo cuando el login esté en producción) y
   mantener HTTPS obligatorio.

### Pendientes de decisión

- Recuperación de contraseña (requiere correo saliente) o solo restablecimiento por administrador.
- Segundo factor (TOTP) para administradores.
- Ingreso con Google Workspace (OIDC) si la organización lo usa.
