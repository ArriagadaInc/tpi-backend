Estado: vigente
Ambiente de referencia: AWS DEV
Validacion fisica AWS DEV: completa para las migraciones H3.3 ejecutadas
Ultima inspeccion: 2026-09-03
Fuente: scripts versionados + `init_test_database.py` + evidencia AWS DEV

# 04 Migraciones

## Alcance

Este documento inventaria los scripts SQL versionados y los artefactos de
bootstrap que definen el contrato reproducible del esquema.

No describe cambios manuales ad hoc. Si un cambio no puede reproducirse mediante
scripts versionados, debe tratarse como drift.

## Inventario cronologico

| Script | Proposito | Dependencia | Estado | Ambiente | Rollback |
| ------ | --------- | ----------- | ------ | -------- | -------- |
| `scripts/sql/001_create_tpi_app_role.sql` | Crear el rol de aplicacion con base minima | Base de datos y esquema `tpi` existentes | Versionado y alineado con el bootstrap minimo de H3.3 para ambientes nuevos | Bootstrap nuevo / administracion | Revocacion manual o deshabilitacion del rol |
| `scripts/sql/003_create_api_idempotency.sql` | Crear la tabla de idempotencia de la API publica | `tpi.leads` | Versionado | Despliegue administrado | `scripts/sql/003_drop_api_idempotency.sql` |
| `scripts/sql/003_drop_api_idempotency.sql` | Revertir la tabla de idempotencia | `tpi.api_idempotency` existente | Versionado | Despliegue administrado | Eliminar tabla y revocar grants |
| `scripts/sql/004_create_lead_assignments.sql` | Crear `tpi.asignaciones` e indices basicos | `tpi.leads`, `tpi.asesores` | Versionado y alineado con el contrato fisico observado | Despliegue administrado | Drop controlado de tabla/indices si hiciera falta |
| `scripts/sql/005_enforce_single_active_assignment.sql` | Garantizar una asignacion activa por lead | `tpi.asignaciones` con datos existentes | Ejecutado y verificado en AWS DEV el 2026-09-03; preflight: 0 duplicados activos | AWS DEV | `DROP INDEX IF EXISTS tpi.asignaciones_one_active_per_lead_uq` |
| `scripts/sql/006_grant_h3_3_assignment_privileges.sql` | Agregar los privilegios minimos que requiere H3.3 inicial | `tpi_app`, `tpi.asesores`, `tpi.asignaciones`, `tpi.auditoria`, `tpi.leads` | Ejecutado y verificado en AWS DEV el 2026-09-03 | AWS DEV existente | Revoke solo de los privilegios agregados por este script, conforme al preflight |
| `scripts/sql/007_create_audit_assignment_view.sql` | Crear la trusted view `tpi.v_asignacion_auditoria` (read model sanitizado sobre `tpi.auditoria`) y conceder `SELECT` solo a `tpi_app` | `tpi.auditoria`, `tpi_app` | Versionado; **NO aplicado en AWS RDS DEV al cierre de la etapa de desarrollo** (change_class D requiere Human Gate explicito) | AWS DEV (post-merge, Human Gate) | `scripts/sql/007_drop_audit_assignment_view.sql` |
| `scripts/sql/008_create_lead_state_history.sql` | Crear la trusted view `tpi.v_historial_estado_lead` (read model sanitizado de cambios generales de `estado_lead`) con `security_barrier`, el indice de apoyo `auditoria_state_history_idx` justificado por EXPLAIN y `GRANT SELECT` solo a `tpi_app` | `tpi.auditoria`, `tpi_app` | Versionado; **NO aplicado en AWS RDS DEV al cierre de la etapa de desarrollo** (change_class D requiere Human Gate explicito) | AWS DEV (post-merge, Human Gate) | `scripts/sql/008_drop_lead_state_history.sql` |
| `scripts/sql/009_create_historial_simulaciones.sql` | Crear la trusted view `tpi.v_historial_simulaciones` (read model sanitizado del historial de simulaciones de renta vitalicia) con `security_barrier`, exponiendo la evidencia completa (`entradas` y `resultado` en JSONB) y `GRANT SELECT` solo a `tpi_app`; sin indice nuevo (reutiliza el de 008) | `tpi.auditoria`, `tpi_app` | Versionado; **NO aplicado en AWS RDS DEV al cierre de la etapa de desarrollo** (change_class D requiere Human Gate explicito) | AWS DEV (post-merge, Human Gate) | `scripts/sql/009_drop_historial_simulaciones.sql` |
| `scripts/sql/010_extend_citas_agenda.sql` | Ampliar `tpi.citas` (responsable obligatorio, `fecha_hora_fin`, quien agendo, nota, motivo de cancelacion, `updated_at`, estados permitidos, una agendada por lead y exclusion de superposicion por responsable) y `tpi.asesores.atiende_reuniones`; `tpi_app` recibe `SELECT, INSERT, UPDATE` sobre `tpi.citas` (sin `DELETE`) | `tpi.citas`, `tpi.asesores`, `btree_gist`, `tpi_app` | Versionado; **NO aplicado en AWS RDS DEV al cierre de la etapa de desarrollo** (change_class D requiere Human Gate explicito) | AWS DEV (post-merge, Human Gate) | `scripts/sql/010_drop_citas_agenda.sql` |
| `scripts/sql/010_drop_citas_agenda.sql` | Revertir la ampliacion de `tpi.citas` y `tpi.asesores` (columnas, restricciones, indices y privilegios nuevos) | `tpi.citas`, `tpi.asesores` | Versionado | AWS DEV (solo tras evaluar el rollback) | Re-aplicar el forward |
| `scripts/sql/011_create_historial_agenda.sql` | Crear la trusted view `tpi.v_historial_agenda` (read model sanitizado de los eventos de la agenda) con `security_barrier`, filtro fijo sobre las cinco acciones de agenda, columnas tipadas (`id_cita` y `responsable_id` como UUID, fechas como TIMESTAMPTZ) y `GRANT SELECT` solo a `tpi_app`; sin indice nuevo (reutiliza el de 008) | `tpi.auditoria`, `tpi_app` | Versionado; **NO aplicado en AWS RDS DEV al cierre de la etapa de desarrollo** (change_class D requiere Human Gate explicito) | AWS DEV (post-merge, Human Gate) | `scripts/sql/011_drop_historial_agenda.sql` |
| `scripts/sql/011_drop_historial_agenda.sql` | Revertir la vista `tpi.v_historial_agenda` (REVOKE SELECT + DROP VIEW idempotente) | `tpi.v_historial_agenda` | Versionado | AWS DEV (solo tras evaluar el rollback) | Re-aplicar el forward |
| `scripts/sql/dev/002_enable_test_cleanup.sql` | Conceder DELETE solo para limpieza controlada en DEV | `tpi.leads`, `tpi.consentimientos` | Ayuda DEV-only | AWS DEV solamente | `scripts/sql/dev/002_disable_test_cleanup.sql` |
| `scripts/sql/dev/002_disable_test_cleanup.sql` | Revocar el DELETE DEV-only | Script de habilitacion previo | Ayuda DEV-only | AWS DEV solamente | Revocar DELETE |

## Estado actual vs estado objetivo

### AWS DEV actual

- `tpi.asignaciones` existe
- existe `tpi.asignaciones_one_active_per_lead_uq`, UNIQUE sobre `id_lead` cuando `estado_asignacion = 'activa'`
- `tpi_app` tiene los privilegios H3.3 verificados sobre `tpi.asesores`, `tpi.asignaciones` y `tpi.auditoria`
- `tpi_app` conserva privilegios efectivos adicionales sobre `tpi.leads` y
  `tpi.personas` que forman parte del estado historico del ambiente

### Estado observado H3.3 en AWS DEV

- al menos para el flujo de asignacion inicial:
  - `tpi.asesores`: `SELECT`
  - `tpi.asignaciones`: `SELECT`, `INSERT`
  - `tpi.auditoria`: `INSERT`
  - `tpi.leads`: `SELECT`, `UPDATE`
- una sola asignacion activa por `id_lead`
- trazabilidad sin ampliar privilegios mas de lo necesario

Evidencia postflight del 2026-09-03:

- `005`: preflight sin duplicados activos; indice parcial creado y verificado
- `006`: privilegios postflight coinciden con el contrato H3.3
- no se modificaron datos de negocio

Operador y commit SHA de la ejecucion: Pendiente de registro operativo.

## Notas sobre `005`

La migracion `005` no cambia datos de negocio. Solo agrega integridad.

Modelo:

1. preflight para detectar duplicados activos
2. aborto si ya existen filas duplicadas
3. creacion del indice parcial unico
4. validacion posterior de que ya no existen conflictos estructurales

Resultado AWS DEV 2026-09-03: aplicado correctamente; indice
`tpi.asignaciones_one_active_per_lead_uq` verificado.

## Notas sobre `007`

La migracion `007` crea un read model SQL sanitizado (vista, no tabla) sobre
`tpi.auditoria` para exponer la trazabilidad de la asignacion de leads sin
conceder acceso directo a la tabla y sin duplicar `estado_anterior`/`estado_nuevo`
en `tpi.asignaciones`.

Contrato versionado:

- Vista `tpi.v_asignacion_auditoria` con `security_barrier`.
- Filtro fijo: `accion = 'asignacion_lead'` y `tabla_afectada = 'tpi.asignaciones'`.
- Columnas permitidas unicamente: `id_auditoria`, `id_lead`, `fecha_hora`,
  `actor_subject`, `id_asesor`, `estado_anterior`, `estado_nuevo`.
- `id_asesor` se valida con `CASE` + expresion regular canonica de UUID
  case-insensitive antes del cast; un valor no-UUID proyecta `NULL` solo en esa
  fila sin inutilizar la vista.
- `REVOKE ALL ... FROM PUBLIC` y `GRANT SELECT` unicamente a `tpi_app`.
- No amplia los privilegios de `tpi_app` sobre `tpi.auditoria`
  (`SELECT/UPDATE/DELETE` continuan `false`; append-only vigente desde `006`).
- Orden estable aplicado por la consulta del repositorio
  (`fecha_hora DESC, id_auditoria DESC`), no por la vista.

Estado de aplicacion:

- **No aplicada en AWS RDS DEV** al cierre de la etapa de desarrollo. La aplicacion
  en AWS DEV es `change_class D` (db_path) y requiere Human Gate explicito: congelar
  el migration candidate (SHA exacto de main + forward/rollback con sus SHA-256),
  preflight DB, aprobacion humana, aplicacion unica y postflight de privilegios.
- El forward/rollback se probaron en PostgreSQL local/integracion (rollback:
  `REVOKE SELECT` + `DROP VIEW`).

## Notas sobre `008`

La migracion `008` crea un read model SQL sanitizado (vista, no tabla) sobre
`tpi.auditoria` para exponer la trazabilidad de los cambios generales de
`estado_lead` sin conceder acceso directo a la tabla y sin duplicar
`estado_anterior`/`estado_nuevo` en `tpi.leads`.

Contrato versionado:

- Vista `tpi.v_historial_estado_lead` con `security_barrier`.
- Filtro fijo: `accion = 'cambio_estado_lead'` y `tabla_afectada = 'tpi.leads'`.
- Columnas permitidas unicamente: `id_auditoria`, `id_lead`, `fecha_hora`,
  `actor_subject`, `estado_anterior`, `estado_nuevo`.
- `REVOKE ALL ... FROM PUBLIC` y `GRANT SELECT` unicamente a `tpi_app`.
- No amplia los privilegios de `tpi_app` sobre `tpi.auditoria`
  (`SELECT/UPDATE/DELETE` continuan `false`; append-only vigente desde `006`).
- Indice de apoyo `auditoria_state_history_idx (accion, tabla_afectada, id_lead,
  fecha_hora)` justificado por EXPLAIN. La **aplicabilidad** del indice se demuestra en
  `tests/integration/test_executive_dashboard_repository.py::test_explain_state_history_uses_support_index`
  forzando `SET LOCAL enable_seqscan = off` (con la tabla de integracion pequena el
  planificador prefiere el seq scan). Las cifras de la comparacion a 100k filas (timeline de
  un lead: Seq Scan ~17.9 ms -> Index Scan ~0.4 ms; agregacion por fecha/accion:
  Seq Scan ~35.6 ms -> Bitmap Index Scan ~25.4 ms) provienen de esa comparacion **forzada**,
  no del plan normal de PostgreSQL; el `EXPLAIN (ANALYZE, BUFFERS)` real sin forzar a volumen
  representativo queda como follow-up (F2 de `evidence/H3.3.4/reviewer/review-01.json`) a
  adjuntar antes del cierre de la tarea.
- Orden estable aplicado por la consulta del repositorio
  (`fecha_hora DESC, id_auditoria DESC`), no por la vista.
- Aviso de cobertura honesto en la ficha: la variable de entorno
  `LEAD_STATE_HISTORY_CUTOVER` (fecha ISO `YYYY-MM-DD`, sin zona horaria; un valor
  invalido o con hora/zona falla la configuracion de forma explicita) controla desde
  que fecha se comunica la cobertura completa de cambios generales. Si no esta
  configurada, la UI no inventa ninguna fecha. Se establece en el deployment como una
  variable de entorno comun de la aplicacion (igual que `TPI_PUBLIC_SITE_URL`), nunca
  via `--option-settings`; no se fija aqui ninguna fecha de AWS DEV.

Estado de aplicacion:

- **No aplicada en AWS RDS DEV** al cierre de la etapa de desarrollo. La aplicacion
  en AWS DEV es `change_class D` (db_path) y requiere Human Gate explicito: congelar
  el migration candidate (SHA exacto de main + forward/rollback con sus SHA-256),
  preflight DB, aprobacion humana, aplicacion unica y postflight de privilegios.
- El forward/rollback se probaron en PostgreSQL local/integracion (rollback:
  `REVOKE SELECT` + `DROP VIEW` + `DROP INDEX`; no elimina datos de auditoria ni
  afecta la vista/objetos de `007`).

## Notas sobre `009`

La migracion `009` crea un read model SQL sanitizado (vista, no tabla) sobre
`tpi.auditoria` para exponer la trazabilidad de las simulaciones de renta vitalicia
(`SIM-HISTORIAL-LINEA-TIEMPO`) sin conceder acceso directo a la tabla y sin duplicar
estado en `tpi.leads`.

Contrato versionado:

- Vista `tpi.v_historial_simulaciones` con `security_barrier`.
- Filtro fijo: `accion = 'simulacion_renta_vitalicia'` y `tabla_afectada = 'tpi.leads'`.
- Columnas: `id_auditoria`, `id_lead`, `fecha_hora`, `actor_subject`, `tipo_escenario`,
  `version_modelo`, `codigo_verificacion`, `entradas` (JSONB) y `resultado` (JSONB).
  La evidencia se expone completa (decision del humano, 2026-10-19): no se censura ningun
  dato registrado; `entradas` y `resultado` conservan causante y beneficiarios con todos
  sus campos y el resultado completo.
- `REVOKE ALL ... FROM PUBLIC` y `GRANT SELECT` unicamente a `tpi_app`.
- No amplia los privilegios de `tpi_app` sobre `tpi.auditoria`
  (`SELECT/UPDATE/DELETE` continuan `false`; append-only vigente desde `006`).
- Sin indice nuevo: la consulta de timeline queda servida por el indice de apoyo
  `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)` de la
  migracion `008`, cuyas columnas lideres coinciden con el filtro de la vista.
- Orden estable aplicado por la consulta del repositorio
  (`fecha_hora DESC, id_auditoria DESC`), no por la vista.

Procedimiento de aplicacion y reversa en AWS DEV (para el humano):

1. Con el migration candidate congelado (SHA exacto de `main`), verificar que `009` esta
   libre y que no se han reejecutado `005`/`006`.
2. Preflight (tpi_admin): `psql ... -f scripts/sql/009_create_historial_simulaciones.sql`.
   El preflight aborta si `tpi_app` posee `SELECT`/`UPDATE`/`DELETE` directo sobre
   `tpi.auditoria` o si falta `USAGE` sobre `tpi`.
3. Postflight: confirmar `SELECT` solo a `tpi_app` sobre la vista, `PUBLIC` sin privilegios
   y `tpi_app` sin `SELECT`/`UPDATE`/`DELETE` directo sobre `tpi.auditoria`.
4. Reversa (solo tras evaluar el rollback conforme al Harness):
   `psql ... -f scripts/sql/009_drop_historial_simulaciones.sql` (idempotente:
   `REVOKE SELECT` + `DROP VIEW`; no elimina datos de auditoria ni afecta `007`/`008`).

Estado de aplicacion:

- **No aplicada en AWS RDS DEV** al cierre de la etapa de desarrollo. La aplicacion
  en AWS DEV es `change_class D` (db_path) y requiere Human Gate explicito.
- El forward/rollback se probaron en PostgreSQL local/integracion.

## Notas sobre `010`

La migracion `010` amplia `tpi.citas` (creada por `setup_db.py` del proyecto
`tpi-data-pipeline`, 0 filas en DEV) y `tpi.asesores` para sostener la agenda de
reuniones del CRM (seccion 6 de `docs/AGENDA_REUNIONES_DISENO.md`).

Contrato versionado:

- `tpi.citas`: `id_asesor` pasa a `NOT NULL` (responsable de la asesoria); columnas
  nuevas `fecha_hora_fin` (`TIMESTAMPTZ NOT NULL`, `CHECK (fecha_hora_fin > fecha_hora)`),
  `agendada_por_subject` y `agendada_por_nombre` (texto, sin FK), `nota` (texto),
  `motivo_cancelacion` (texto) y `updated_at` (`TIMESTAMPTZ NOT NULL DEFAULT now()`);
  `CHECK` de `estado_cita` (`agendada`, `realizada`, `no_asistio`, `cancelada`); indice
  unico parcial `citas_one_agendada_per_lead_uq` (una agendada por lead); indice
  `citas_fecha_hora_idx`; y restriccion de exclusion
  `citas_responsable_no_superposicion_excl` (`EXCLUDE USING gist`, `id_asesor` con `=`,
  `tstzrange(fecha_hora, fecha_hora_fin)` con `&&`, cuando `estado_cita = 'agendada'`)
  para que un responsable no tenga dos reuniones que se pisen.
- `tpi.asesores.atiende_reuniones BOOLEAN NOT NULL DEFAULT false`: marca de quien puede
  ser responsable de una reunion (Socios CEO/CTO con `rol = 'socio'` y Coordinadores con
  `rol = 'asesor'` y la marca en `true`).
- Privilegios sobre `tpi.citas`: `REVOKE ALL ... FROM PUBLIC` y `GRANT SELECT, INSERT,
  UPDATE` a `tpi_app`, sin `DELETE` (la reunion se cancela, no se borra). No toca los
  privilegios de `tpi_app` sobre `tpi.auditoria` ni sobre las demas tablas.
- `btree_gist`: la restriccion `EXCLUDE` la exige. El preflight aborta con un mensaje
  claro si la extension no esta disponible; si RDS no la permitiera, no se reemplaza por
  cuenta propia (la alternativa es un candado de transaccion por responsable y cambia el
  diseno).

Procedimiento de aplicacion y reversa en AWS DEV (para el humano):

1. Con el migration candidate congelado (SHA exacto de `main`), comprobar previamente que
   RDS permite `btree_gist` a `tpi_admin` (consulta de disponibilidad de extensiones).
2. Preflight (tpi_admin): `psql ... -f scripts/sql/010_extend_citas_agenda.sql`. Aborta
   si falta el esquema `tpi`, si `tpi.citas` tiene filas o si `btree_gist` no esta
   disponible.
3. Postflight: confirmar las columnas nuevas, `id_asesor` `NOT NULL`, las restricciones e
   indices, `tpi.asesores.atiende_reuniones`, y que `tpi_app` tiene `SELECT`, `INSERT` y
   `UPDATE` sobre `tpi.citas` y sin `DELETE` (y `tpi.auditoria` intacta).
4. Reversa (solo tras evaluar el rollback conforme al Harness):
   `psql ... -f scripts/sql/010_drop_citas_agenda.sql` (idempotente: quita indices,
   restricciones, columnas nuevas y los privilegios nuevos; aborta si `tpi.citas` tiene
   filas). No elimina la tabla `tpi.citas`, no elimina `btree_gist` y no toca
   `tpi.auditoria`.

Estado de aplicacion:

- **No aplicada en AWS RDS DEV** al cierre de la etapa de desarrollo. La aplicacion en
  AWS DEV es `change_class D` (db_path) y requiere Human Gate explicito.
- El forward/rollback se probaron en PostgreSQL local/integracion
  (`tests/integration/test_citas_agenda_migration.py`), incluidas las restricciones de
  superposicion, una agendada por lead, estados permitidos y `fecha_hora_fin > fecha_hora`.

## Notas sobre `011`

La migracion `011` crea un read model SQL sanitizado (vista, no tabla) sobre
`tpi.auditoria` para exponer la trazabilidad de los eventos de la agenda de reuniones
(`CRM-AGENDA-4-HISTORIAL`) sin conceder acceso directo a la tabla y sin duplicar estado
en `tpi.citas`.

Contrato versionado:

- Vista `tpi.v_historial_agenda` con `security_barrier`.
- Filtro fijo: `accion IN ('cita_agendada', 'cita_reagendada', 'cita_cancelada',
  'cita_realizada', 'cita_no_asistio')` y `tabla_afectada = 'tpi.citas'`.
- Columnas: `id_auditoria`, `id_lead`, `fecha_hora`, `accion`, `actor_subject`, `id_cita`
  (UUID), `responsable_id` (UUID, puede ser NULL), `estado_anterior`, `estado_nuevo`,
  `fecha_hora_anterior` (TIMESTAMPTZ, puede ser NULL) y `fecha_hora_nueva` (TIMESTAMPTZ,
  puede ser NULL). `id_cita` y `responsable_id` se validan con `CASE` + expresion regular
  canonica de UUID case-insensitive antes del cast; las fechas se proyectan como TIMESTAMPTZ
  (el escritor `AgendaRepository._insert_cita_audit` las guarda como ISO 8601 con zona horaria
  o JSON null).
- `REVOKE ALL ... FROM PUBLIC` y `GRANT SELECT` unicamente a `tpi_app`.
- No amplia los privilegios de `tpi_app` sobre `tpi.auditoria`
  (`SELECT/UPDATE/DELETE` continuan `false`; append-only vigente desde `006`).
- No expone `detalle` crudo, `id_persona`, `id_usuario` ni `ip_origen`; la nota y el motivo
  de cancelacion no se registran en la auditoria de la agenda y no llegan a la vista.
- Sin indice nuevo: la consulta queda servida por el indice de apoyo
  `auditoria_state_history_idx (accion, tabla_afectada, id_lead, fecha_hora)` de la migracion
  `008`, cuyas columnas lideres coinciden con el filtro de la vista.
- Orden estable aplicado por la consulta del repositorio
  (`fecha_hora DESC, id_auditoria DESC`), no por la vista.

Procedimiento de aplicacion y reversa en AWS DEV (para el humano):

1. Con el migration candidate congelado (SHA exacto de `main`), verificar que `011` esta
   libre y que no se han reejecutado `005`/`006`.
2. Preflight (tpi_admin): `psql ... -f scripts/sql/011_create_historial_agenda.sql`.
   El preflight aborta si `tpi_app` posee `SELECT`/`UPDATE`/`DELETE` directo sobre
   `tpi.auditoria` o si falta `USAGE` sobre `tpi`.
3. Postflight: confirmar que la vista existe con `security_barrier`, `SELECT` solo a
   `tpi_app` sobre la vista, `PUBLIC` sin privilegios y `tpi_app` sin `SELECT`/`UPDATE`/`DELETE`
   directo sobre `tpi.auditoria`.
4. Reversa (solo tras evaluar el rollback conforme al Harness):
   `psql ... -f scripts/sql/011_drop_historial_agenda.sql` (idempotente:
   `REVOKE SELECT` + `DROP VIEW IF EXISTS`; no elimina datos de auditoria ni afecta las
   vistas de `007`/`008`/`009`).

Estado de aplicacion:

- **No aplicada en AWS RDS DEV** al cierre de la etapa de desarrollo. La aplicacion
  en AWS DEV es `change_class D` (db_path) y requiere Human Gate explicito.
- El forward/rollback se probaron en PostgreSQL local/integracion
  (`tests/integration/test_agenda_historial_view.py`), con las filas de auditoria producidas
  por el flujo real de la agenda (`AgendaRepository`).

## Bootstrap vs migracion incremental

`scripts/init_test_database.py` no es una migracion de runtime.

Es el bootstrap de testing que recrea el contrato necesario para CI e
integracion, incluyendo la tabla de asignaciones y la proteccion por indice
parcial que los tests necesitan validar.

`001_create_tpi_app_role.sql` sigue siendo el bootstrap base para ambientes
nuevos. Versiona el contrato minimo reproducible para H3.3 en ambientes
futuros, incluyendo `tpi.asesores` read-only, `tpi.asignaciones` read/create
y `tpi.auditoria` append-only.

`006_grant_h3_3_assignment_privileges.sql` representa la evolucion
incremental necesaria para ambientes ya existentes como AWS DEV. Su preflight
aborta si el estado observado no coincide con el drift documentado.

## Regla de drift

Si AWS DEV diverge del contrato versionado, la correccion debe modelarse como
migracion o grant versionado.

No se debe parchar manualmente el schema drift cuando el cambio debe quedar
reproducible.
