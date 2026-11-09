# Demostración local («Demo APR»)

**Solo para el entorno local de desarrollo.** Estas credenciales son públicas: no ejecute `make demo` en una
instancia publicada.

```bash
make up
make demo        # crea la organización «Demo APR», un usuario por rol y le asigna el proyecto «APR Demo»
```

| Rol | Correo | Contraseña | Puede |
|---|---|---|---|
| Administrador | admin@demo-apr.cl | Apr-Gestion-2026 | todo + miembros, invitaciones, auditoría y uso |
| Proyectista | proyectista@demo-apr.cl | Apr-Diseno-2026 | editar, simular, importar y exportar |
| Revisor | revisor@demo-apr.cl | Apr-Revision-2026 | ver, exportar, comentar y aprobar versiones |
| Lector | lector@demo-apr.cl | Apr-Consulta-2026 | ver y exportar (el editor queda en solo lectura) |

Si `make demo` no encuentra un proyecto «APR Demo», lo crea desde `examples/apr-demo.xlsx`.

En el `.env` local se usa `MFA_REQUIRED_FOR_ADMINS=false` para no pedir TOTP al administrador de la demo. Con
`true` (valor de producción), el administrador debe configurarlo en **/perfil** al ingresar.

El superadministrador de plataforma se crea aparte: `make create-admin` (pide correo y contraseña).
El recorrido visual (`make test-e2e`) usa su propio usuario `e2e@trazo.local` en la organización «Recorrido e2e».
