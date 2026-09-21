# H3.3.5 — Runbook DEV: Seed de asesores y cutover RBAC por cartera

Tarea: `H3.3.5 Asesores DEV y cartera propia`
Clase de cambio: `D` (base de datos) + `A` (aplicación) + `E` (secretos, fuera del Harness).
Baseline: `origin/main@3051a6271e1626b40fe24a744abe097cab1ab0fe`.

> Este documento describe los pasos operativos. **El Developer/Deployer no ejecuta el seed ni
> escribe en AWS RDS.** El seed lo ejecuta el operador humano tras el preflight D5. El Deployer
> realiza exclusivamente postflight DB read-only. Este runbook no se ejecuta: es el contrato.

## 0. Fuentes canónicas de cada valor

| Valor | Fuente canónica | Nota |
| --- | --- | --- |
| Cuenta `821656895812` | `environments/dev.yaml` (`account_id`) | verificado contra `AGENTS.md` y `validate_repo.py` |
| Región `us-east-2` | `environments/dev.yaml` (`region`) y `harness/policies.yaml` (`aws.region`) | — |
| Perfil lógico `tpi-dev` | `environments/dev.yaml` (`profile`) y `harness/policies.yaml` (`aws.profile`) | — |
| Environment `tpi-backoffice-dev-green` | `environments/dev.yaml` (`deployment_target.environment_name`) | — |
| Aplicación `tpi-backoffice` | `environments/dev.yaml` (`application`) | — |
| Endpoint/base `tpi` (RDS `tpi-postgres-dev`) | `docs/AWS_RDS_CONNECTION.md` y `docs/database/06_OPERATIONS_RUNBOOK.md` | base `tpi`, esquema `tpi` |
| Usuario DB autorizado | `docs/AWS_RDS_CONNECTION.md` (rol `tpi_app` SELECT-only; admin `tpi_admin`) y `docs/database/06_OPERATIONS_RUNBOOK.md` | el seed exige INSERT sobre `tpi.asesores` |
| Columnas de `tpi.asesores` | `docs/database/02_PHYSICAL_SCHEMA.md` y `scripts/init_test_database.py` | `id_asesor` PK UUID; `nombre` NOT NULL UNIQUE `lower(nombre)`; `rol` default `asesor`; `estado_disponibilidad` default `activo` |
| Grants de `tpi_app` | `scripts/sql/006_grant_h3_3_assignment_privileges.sql` y `docs/database/06_OPERATIONS_RUNBOOK.md` | `tpi_app`: SELECT-only sobre `tpi.asesores` |

Todo valor no documentado canónicamente se registra como BLOCKER; no se inventa.

## 1. Preflight del operador humano (D5) — antes de ejecutar el seed

Ejecutar en la terminal del operador, **nunca** vía Harness:

1. **STS / identidad AWS**: `aws sts get-caller-identity --profile tpi-dev --region us-east-2`
   (o `python scripts/harness/aws_guard.py sts get-caller-identity` solo si el rol lo autoriza;
   el operador humano usa su propio terminal). Verificar que el `Account` sea `821656895812`.
   Si no es esa cuenta → STOP.
2. **Cuenta y región**: confirmar `821656895812` y `us-east-2` (fuentes: `environments/dev.yaml`,
   `harness/policies.yaml`).
3. **Environment AWS DEV**: confirmar `tpi-backoffice-dev-green` y su estado de salud
   (`Ready / Green / Ok`) con lecturas controladas. Si no está sano → STOP.
4. **Endpoint / base esperados**: RDS `tpi-postgres-dev`, base `tpi`, esquema `tpi`, puerto `5432`
   (`docs/AWS_RDS_CONNECTION.md`, `docs/database/06_OPERATIONS_RUNBOOK.md`).
5. **Usuario DB autorizado**: conectar como rol administrativo (ej. `tpi_admin`), nunca `tpi_app`.
   El seed verifica además `has_table_privilege(current_user, 'tpi.asesores', 'INSERT')`.
6. **Salud del environment**: no iniciar la transacción SQL si el environment no está sano.

Si cualquier comprobación falla → **STOP, no ejecutar el seed**.

## 2. Aplicación humana del seed

1. Conectar a la base DEV como rol administrativo (`tpi_admin` u otro rol con INSERT en
   `tpi.asesores`), apuntando a `tpi-postgres-dev` / base `tpi`.
2. Ejecutar, en una única sesión:
   `\i scripts/sql/dev/seed_asesores_desarrollo.sql`
3. El script abre `BEGIN`, valida base/esquema/usuario, procesa cada nombre normalizado
   (`lower(nombre)`) con la política D6, y hace `COMMIT` solo si todo es correcto.
4. El script emite `RAISE NOTICE` con el `id_asesor` **creado o adoptado** de cada asesor.
   Registrar esos UUID (son la base del `advisor_id` en `AUTH_USERS_JSON`), sin PII.

Resultado esperado:
- `Asesor Desarrollo 1` → exactamente un `tpi.asesores` activo (`rol='asesor'`, `estado_disponibilidad='activo'`).
- `Asesor Desarrollo 2` → exactamente un `tpi.asesores` activo.
- `tpi.asignaciones` no se modifica; grants de `tpi_app` no cambian.

## 3. Ejecución idempotente por segunda vez

Volver a ejecutar `seed_asesores_desarrollo.sql`:
- cada nombre normalizado ya existe exactamente una vez con atributos compatibles → se adopta su
  UUID (no-op, sin `UPDATE`, sin `INSERT`, sin duplicado);
- el resultado es idéntico al de la primera ejecución;
- el script termina con `COMMIT` y los mismos `RAISE NOTICE`.

Si la segunda ejecución no produce exactamente el mismo resultado → STOP y revisar drift.

## 4. Postflight DB read-only (lo ejecuta el Deployer)

El Deployer **no escribe** en AWS RDS. Solo lee:

```sql
SELECT id_asesor, nombre, rol, estado_disponibilidad
FROM tpi.asesores
WHERE lower(nombre) IN ('asesor desarrollo 1', 'asesor desarrollo 2')
ORDER BY nombre;
```

- Debe devolver exactamente 2 filas, ambas `rol='asesor'` y `estado_disponibilidad='activo'`.
- Verificar unicidad y que no se crearon duplicados.
- Registrar evidencia read-only **sin PII ni secretos** (UUID + nombre + rol + estado son
  suficientes; no se registra `email` ni datos de negocio).

## 5. Comportamiento ante conflicto o fallo

- Si el seed aborta (nombre incompatible, ambiguo, base/esquema/usuario incorrectos) → el
  `RAISE EXCEPTION` revierte toda la transacción (rollback automático; no se dejan filas parciales).
- **STOP**: registrar evidencia del fallo (`STOP` + causa) y **no desplegar la aplicación**.
- No reintentar a ciegas; no parchear drift manual; no ampliar grants.

## 6. Carga real de `AUTH_USERS_JSON` (evidencia de código/configuración, no suposición)

Determinado a partir del código y la configuración versionados:

- **Dónde se lee**: `app/config/settings.py` declara `auth_users_json: SecretStr` con alias
  `AUTH_USERS_JSON` (variable de entorno). El bundle AWS
  `deployment/aws/docker-compose.domainlocked.yml` la inyecta como
  `${AUTH_USERS_JSON:?AUTH_USERS_JSON is required when authentication is enabled}` (fail-closed si falta).
- **Cuándo se parsea**: `app/auth/simple_dev.py::SimpleDevAuth.__init__` invoca
  `_parse_users(settings.auth_users_json.get_secret_value())` una única vez, durante la creación de
  la aplicación en `app/web/main.py::create_web_app()` (`build_auth_provider(settings)`).
- **Si queda cacheado**: sí. Los usuarios parseados quedan en `self._users` de la instancia
  `SimpleDevAuth`, que se almacena en `app.state.auth_provider` durante toda la vida del proceso.
  `get_settings()` usa `@lru_cache(maxsize=1)`. No hay relectura por request.
- **Qué operación real necesita para refrescarlo**: un cambio en `AUTH_USERS_JSON` solo toma
  efecto cuando el proceso vuelve a arrancar y relee la variable de entorno. El refresh requiere:
  (1) publicar la nueva versión del secreto en el mecanismo de secretos del environment
  (Secrets Manager / EB environment secrets) — lo hace el humano, secret path, fuera del Harness — y
  (2) un reinicio controlado del runtime (nuevo arranque del contenedor). El Harness prohíbe
  `restart-app-server` y `--option-settings`, por lo que **este refresh lo ejecuta el humano**.
- Evidencia adicional: `docs/DECISIONES_TECNICAS.md` («mantener AUTH_USERS_JSON como secreto vivo
  del environment») y `docs/H3_3_2_SUPERUSUARIOS_CEO_CTO.md` (procedimiento de reconstrucción del
  payload preservando usuarios existentes).

## 7. Orden de cutover obligatorio (D7)

Invariante: **ninguna credencial advisor puede quedar utilizable mientras esté corriendo una
versión que no aplique el alcance por cartera.**

1. **Datos DEV**: el operador humano ejecuta el preflight (sección 1) y el seed (sección 2).
2. **Postflight**: el Deployer ejecuta el postflight DB read-only (sección 4).
3. **Deploy RBAC**: desplegar la versión de aplicación con RBAC por cartera (fast path version-only,
   `update-environment --version-label <aprobada>`, sin `--option-settings`).
4. **Ready/Green/Ok**: esperar y verificar `VersionLabel` exacta + salud del environment.
5. **Identidades configuradas por humano**: el humano añade las dos identidades
   `asesor.desarrollo1` / `asesor.desarrollo2` (rol `advisor`, con `advisor_id` = UUID adoptado)
   al payload vivo de `AUTH_USERS_JSON`, preservando los usuarios existentes.
6. **Refresh controlado**: el humano ejecuta el mecanismo real de refresco de la sección 6
   (publicar secreto + reinicio controlado).
7. **Nueva comprobación de salud y release**: reverificar salud y release desplegado.
8. **Smoke autenticado**: smoke humano (AC-17) con ambas cuentas advisor.

## 8. Prohibición

- **Prohibido** habilitar/activar credenciales advisor en `AUTH_USERS_JSON` antes de que la versión
  con RBAC por cartera esté desplegada y saludable (pasos 3-4 del cutover).
- **Prohibido** que el Harness/Deployer escriba en RDS, ejecute el seed, lea `AUTH_USERS_JSON`,
  genere hashes o use `--option-settings` / `restart-app-server`.
- Si el mecanismo de refresh no pudiera determinarse con evidencia → BLOCKER (aquí queda
  determinado con evidencia de código).
