# H3.3.2 — Modelo de superusuarios CEO/CTO e identidades DEV

## Objetivo

Establecer `diego.operaciones` como CEO y `alvaro.operaciones` como CTO, superusuarios
funcionales del backoffice TPI con un **superset** de los permisos RBAC existentes. Esta tarea
absorbe la validacion funcional diferida en el cierre administrativo de H3.3.1
(`evidence/H3.3.1/approvals/acceptance-02.json`).

## Modelo de superusuarios (codigo)

La fuente unica de verdad es `app/auth/models.py`:

- `SUPERUSER_ROLES = frozenset({"ceo", "cto"})`
- `is_superuser(role)` -> `True` solo para `ceo`/`cto`

Se aplica de forma consistente en las dos capas:

| Capacidad | Ubicacion | Regla efectiva |
| --- | --- | --- |
| PII completa (bandeja y detalle) | `SolicitudService.can_view_full_pii` | superusuario |
| Asignacion manual de leads | `SolicitudService.can_assign_lead` | superusuario o `admin`/`executive` |
| Escritura (cambio de estado, seguimiento) | `app/web/routes/leads.py::_can_write` | superusuario o `tester`/`advisor`/`operations`/`admin` |
| Cleanup de leads de prueba | `app/web/routes/leads.py::_can_cleanup` | superusuario o `tester`/`admin` |

**Alcance estricto:** esta regla aplica exclusivamente al backoffice TPI y **no** concede
permisos AWS, IAM, Harness ni de deployment. Los permisos de los demas roles **no se reducen**.

## Identidades DEV (accion pendiente para rol autorizado)

La configuracion de identidades vive en el secreto `AUTH_USERS_JSON` (clase E, secreto vivo del
environment, fuera del artefacto y del repo). El rol Developer **no puede** leerlo ni modificarlo
y no evade esa politica: deja la accion preparada.

Cambios requeridos sobre la version viva de `AUTH_USERS_JSON` (sin exponer aqui hashes,
passwords ni secretos):

1. `diego.operaciones`: cambiar `role` de `operations` a `ceo` (preservar
   `subject`, `username` y `display_name` existentes).
2. `alvaro.operaciones`: crear la entrada con `role` `cto` (nuevo `subject` estable,
   `username` `alvaro.operaciones`).

Contrato de cada entrada (validado por `app/auth/simple_dev.py::_parse_user`):

- `subject`: identificador tecnico estable; es el valor de `asignado_por` en
  `tpi.asignaciones` y debe caber en `VARCHAR(150)`.
- `username`: nombre de login.
- `display_name`: solo presentacion; nunca se usa como `asignado_por`.
- `role`: debe ser uno de los roles permitidos (`ceo`/`cto` ya soportados).
- `password_hash`: Argon2id generado interactivamente por el operador autorizado (nunca en Git,
  logs ni evidencia).

Procedimiento seguro (lo ejecuta el rol autorizado — humano, secret path, fuera del Harness):

1. Generar el hash Argon2id de cada password de forma interactiva (ver
   `docs/DEVELOPMENT_GUIDE.md`, seccion "Local demo", para el patron de generacion; usar
   `getpass` y no volcar el hash en la consola ni en archivos versionados).
2. Reconstruir el payload `AUTH_USERS_JSON` **preservando todos los usuarios existentes** y
   aplicando los dos cambios de arriba.
3. Publicar la nueva version en el mecanismo de secretos del environment (Secrets Manager /
   EB environment secrets) y aplicar el cambio en el runtime segun el procedimiento operativo
   vigente (sin reejecutar migraciones 005/006).
4. Verificar con el smoke autenticado humano (AC-8) usando `diego.operaciones` (CEO) y
   `alvaro.operaciones` (CTO).

## Criterios de aceptacion

- AC-1 (humano): `diego.operaciones` autentica en DEV con rol `ceo` — depende de la accion
  pendiente de identidad.
- AC-2 (humano): `alvaro.operaciones` existe y autentica en DEV con rol `cto` — depende de la
  accion pendiente de identidad.
- AC-3 (both): CEO/CTO ven PII completa — cubierto por `tests/unit/test_h3_3_1_rbac_pii_assignment.py`
  y `tests/unit/test_web_app.py`.
- AC-4 (both): CEO/CTO pueden asignar — cubierto por `tests/unit/test_rbac_superusers.py` y
  `tests/unit/test_solicitud_assignment_service.py`.
- AC-5 (both): CEO/CTO pueden ejecutar todas las capacidades funcionales/administrativas sujetas a
  RBAC — cubierto por `tests/unit/test_rbac_superusers.py` y
  `tests/unit/test_web_app.py::test_ceo_and_cto_can_execute_superuser_actions`.
- AC-6 (both): roles no privilegiados siguen enmascarados — cubierto por H3.3.1 (sin regresion).
- AC-7 (both): garantias de asignacion intactas — cubierto por tests de H3.3.1 (sin regresion).
- AC-8 (humano): smoke autenticado en AWS DEV — pendiente de la accion de identidad.
