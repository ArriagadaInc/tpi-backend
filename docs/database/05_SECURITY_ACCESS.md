Estado: vigente
Ambiente de referencia: AWS DEV
Validacion fisica AWS DEV: completa para privilegios de `tpi_app`
Ultima inspeccion: 2026-09-03
Fuente: privilegios efectivos en AWS DEV + scripts versionados + `init_test_database.py`

# 05 Seguridad y Acceso

## Principios

- no versionar secretos
- `.env` es local y no versionado
- AWS y produccion deben recibir configuracion por variables de entorno o un
  gestor de secretos
- aplicar privilegios minimos
- fallar en cerrado si faltan autenticacion o SSL

## Roles

### `tpi_admin`

- rol administrativo
- se usa para inspeccion, bootstrap y migraciones
- no debe ser usado por el runtime de la aplicacion

### `tpi_app`

- rol de runtime de la aplicacion
- usado por el backoffice en local, testing, AWS DEV y futura produccion
- debe operar con privilegios minimos

## Evidencia AWS DEV post-006

Hallazgo confirmado:

- `tpi_app` tiene `USAGE` sobre el esquema `tpi`
- no existen membresias de roles para `tpi_app`
- `rolinherit = false`
- no existe herencia que explique permisos adicionales
- `INSERT` sobre `tpi.auditoria` es `true`
- la evidencia fue obtenida con `scripts/sql/inspect_dev_tpi_app_privileges_readonly.sql`

## Matriz de privilegios

### Leyenda

- **OBSERVADO AWS DEV**: privilegio efectivo medido en la instancia real
- **VERSIONADO REPO**: privilegio declarado por scripts versionados
- **REQUERIDO H3.3**: minimo necesario para el flujo de asignacion inicial

| Objeto | OBSERVADO AWS DEV | VERSIONADO REPO | REQUERIDO H3.3 | Estado |
| ------ | ----------------- | --------------- | -------------- | ------ |
| `schema tpi` | `USAGE = true` | `USAGE = true` | `USAGE = true` | alineado |
| `tpi.personas` | `SELECT/INSERT/UPDATE = true`, `DELETE = false` | `SELECT/INSERT/UPDATE` | fuera de alcance H3.3 | drift historico tolerado por ahora |
| `tpi.leads` | `SELECT/INSERT/UPDATE/DELETE = true` | `SELECT/INSERT/UPDATE` | `SELECT/UPDATE` | drift historico fuera del alcance de 006 |
| `tpi.asesores` | `SELECT = true`; `INSERT/UPDATE/DELETE = false` | `SELECT` | `SELECT` | alineado post-006 |
| `tpi.asignaciones` | `SELECT/INSERT = true`; `UPDATE/DELETE = false` | `SELECT/INSERT` | `SELECT/INSERT` | alineado post-006 |
| `tpi.auditoria` | `INSERT = true`; `SELECT/UPDATE/DELETE = false` | `INSERT` | `INSERT` | alineado post-006; append-only |
| `tpi.v_asignacion_auditoria` (vista 007) | no existe aun en AWS DEV (007 pendiente de Human Gate) | `SELECT` a `tpi_app`; `REVOKE ALL` a `PUBLIC` | `SELECT` a `tpi_app`; sin privilegios para `PUBLIC` | pendiente post-007 |

## Drift de seguridad

Antes de `006` existia una divergencia real entre los tres planos. El estado fisico observado despues de la migracion es:

1. **AWS DEV observado**
2. **repo/versionado**
3. **requerido por H3.3**

Ejemplos concretos:

- AWS DEV ya tiene los permisos minimos H3.3 sobre `tpi.asesores`, `tpi.asignaciones` y `tpi.auditoria`
- `001_create_tpi_app_role.sql` ya declara parcialmente permisos sobre
  `tpi.asesores` y `tpi.asignaciones`
- AWS conserva `DELETE` historico sobre `tpi.leads` y no se revoco mediante `006`

No se debe reconciliar esta realidad silenciosamente.

## Contrato minimo H3.3

Para la asignacion inicial, el minimo operativo es:

- `tpi.asesores`: `SELECT`
- `tpi.asignaciones`: `SELECT`, `INSERT`
- `tpi.auditoria`: `INSERT`
- `tpi.leads`: `SELECT`, `UPDATE`

Estado: OBSERVADO en AWS DEV despues de `006`.

`UPDATE` y `DELETE` sobre `tpi.asignaciones` no forman parte de H3.3 inicial.

## Auditoria

El codigo inserta trazabilidad en `tpi.auditoria`.

Actualmente la aplicacion debe tratar esa tabla como **append-only**:

- `INSERT` permitido
- `UPDATE` no requerido
- `DELETE` no requerido

El retorno de la insercion no debe depender de leer columnas de auditoria
posteriores.

En la practica operativa:

- `tpi.asesores` es read-only para `tpi_app`
- `tpi.auditoria` es append-only para `tpi_app`
- `tpi.asignaciones` solo requiere create/read para la asignacion inicial

## Vista de trazabilidad (migracion 007)

La migracion `007` introduce `tpi.v_asignacion_auditoria`, un read model de solo
lectura que permite a la aplicacion leer la trazabilidad de asignacion **sin**
conceder `SELECT` directo sobre `tpi.auditoria`.

- `PUBLIC` no recibe ningun privilegio sobre la vista (`REVOKE ALL ... FROM PUBLIC`).
- Unicamente `tpi_app` recibe `SELECT` sobre la vista.
- `tpi_app` conserva `SELECT/UPDATE/DELETE = false` sobre `tpi.auditoria`: la vista
  no amplia esos privilegios directos.
- La aplicacion lee la vista (nunca `tpi.auditoria`) y resuelve el nombre del asesor
  con un `JOIN` seguro hacia `tpi.asesores`.

## Identificador tecnico del actor

H3.3 usa `AuthenticatedUser.subject` como valor de `asignado_por`.

Razones para mantenerlo:

- es estable por contrato
- no es un `display_name`
- no se usa como mapping hacia `id_asesor`
- cabe en `VARCHAR(150)`

Si el proveedor de autenticacion cambia el formato o la longitud, este contrato
debe revalidarse.

## `tpi_app` puede y no puede

### Puede

- conectarse al esquema `tpi`
- leer tablas operativas
- crear y actualizar leads en el flujo de registro
- crear filas de asignacion
- insertar trazabilidad

### No puede

- crear roles
- crear bases de datos
- modificar el esquema ad hoc
- depender de SSL deshabilitado en AWS o produccion

## Seguridad SSL/TLS

- `local`: SSL puede estar deshabilitado
- `testing`: depende del entorno configurado
- `aws-dev`: SSL obligatorio
- `production`: `verify-full` + CA de RDS

## Archivos relevantes

- `scripts/sql/001_create_tpi_app_role.sql`
- `scripts/sql/006_grant_h3_3_assignment_privileges.sql`
- `scripts/sql/inspect_dev_tpi_app_privileges_readonly.sql`

## Configuracion

Contratos admitidos:

- `DATABASE_URL`
- o variables `DATABASE_*` separadas

No almacenar en el repositorio:

- passwords
- tokens
- certificados privados
- cadenas de conexion con secretos embebidos
