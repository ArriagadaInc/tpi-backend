Estado: vigente
Ambiente validado: AWS DEV
Ultima validacion fisica: 2026-10-24 (conteos y claves foraneas con `scripts/dev_reset_leads.py --inspeccionar`)
Fuente: PostgreSQL RDS DEV (solo lectura) + `tpi-data-pipeline` + scripts versionados

# 08 Datos de DEV: inventario, procedencia y reinicio

## Para que sirve este documento

Responde, sin volver a inspeccionar la base, tres preguntas:

1. **Que hay hoy en la base de DEV** y de donde viene (inventario con fecha).
2. **Como se relacionan las tablas** al borrar o insertar datos (orden y reglas de las claves foraneas).
3. **Como se reinician los datos de DEV** de forma segura y que deja y que borra esa operacion.

El esquema columna por columna esta en [02_PHYSICAL_SCHEMA.md](02_PHYSICAL_SCHEMA.md); las reglas de negocio en
[03_BUSINESS_RULES.md](03_BUSINESS_RULES.md); los privilegios de `tpi_app` y `tpi_admin` en
[05_SECURITY_ACCESS.md](05_SECURITY_ACCESS.md).

## Procedencia de los datos

- Los leads de DEV son **sinteticos** (decision del humano, 2026-10-22): se pueden borrar y regenerar sin migrarlos. Los casos reales se
  migraran a produccion mas adelante, por un camino aparte.
- La mayoria nacio por la **ingesta desde Google Sheets** del proyecto hermano `tpi-data-pipeline` (`ingest_google_sheets.py`), que
  tambien es el dueno del DDL de las tablas operativas `campanas_atribucion`, `eventos_lead`, `citas`, `fichas_diagnosticas` e
  `ingesta_google_sheets` (`setup_db.py` y `docs/BASE_DE_DATOS_TPI.md` de ese proyecto). El backoffice (este repositorio) no las usa hoy.
- En la inspeccion de 2026-10-24 hay 85 leads y solo 69 filas de ingesta. No se determino de donde vienen los 16 restantes (pueden ser de
  la API publica, de pruebas manuales o del simulador). `leads.origen_lead` y `leads.fuente_actual` permiten distinguirlos.
- Los leads que siembra la herramienta de reinicio llevan `fuente_actual = 'seed_dev'`, correos `@example.test` y telefonos `+569555...`:
  son ficticios y se reconocen siempre.

## Inventario de DEV al 2026-10-24 (antes del primer reinicio)

Medido con `scripts/dev_reset_leads.py --inspeccionar` y con su simulacion (solo lectura, como `tpi_admin` por el tunel a DEV).

| Tabla | Filas | Relacion con `leads` / `personas` | Regla al borrar el padre |
| ----- | ----: | --------------------------------- | ------------------------ |
| `tpi.leads` | 85 | `id_persona` -> `personas` | NO ACTION |
| `tpi.personas` | 83 | (raiz; 83 personas para 85 leads: algunas tienen mas de un lead) | - |
| `tpi.consentimientos` | 82 | `id_lead` (opcional) y `id_persona` | NO ACTION |
| `tpi.asignaciones` | 34 | `id_lead` -> `leads`, `id_asesor` -> `asesores` | NO ACTION |
| `tpi.auditoria` | 146 (141 con lead o persona) | `id_lead` y `id_persona`, ambos opcionales | NO ACTION |
| `tpi.campanas_atribucion` | 69 | `id_lead` (UNIQUE) | NO ACTION |
| `tpi.eventos_lead` | 69 | `id_lead` | NO ACTION |
| `tpi.ingesta_google_sheets` | 69 (las 69 ligadas a un lead) | `id_lead_generado` (opcional) | NO ACTION |
| `tpi.api_idempotency` | 2 | `lead_id` | **SET NULL** |
| `tpi.citas` | 0 | `id_lead` -> `leads`, `id_asesor` (obligatorio tras 010) -> `asesores` | NO ACTION |
| `tpi.fichas_diagnosticas` | 0 | `id_lead` -> `leads`, `id_asesor` (opcional) | NO ACTION |
| `tpi.asesores` | 4 activos con rol `asesor` (los Socios CEO/CTO entran con rol `socio` tras 010) | referenciada por `asignaciones`, `citas` y `fichas_diagnosticas`; `atiende_reuniones` (010) marca a los responsables de reuniones | - |
| Bucket de adjuntos `leads/` | 7 objetos | clave `leads/{id_lead}/{id_adjunto}` | no es una FK (ver abajo) |

Notas de lectura:

- **Ninguna tabla depende de otra tabla dependiente** (no hay dependencias indirectas): las cinco tablas del pipeline apuntan solo a
  `leads` (y a `asesores`). Por eso basta vaciar los hijos de `leads` y despues `leads` y `personas`.
- Las 146 filas de `auditoria` incluyen unas 5 sin lead ni persona (deducido: 146 en total menos 141 con alguno de los dos); la
  herramienta de reinicio **no** las toca.
- Las claves foraneas son todas `NO ACTION` (bloquean el borrado del padre) salvo `api_idempotency.lead_id`, que es `SET NULL`.
- No se verificaron en DEV los privilegios de `tpi_app` sobre `campanas_atribucion`, `eventos_lead`, `citas`, `fichas_diagnosticas` ni
  `ingesta_google_sheets`; `docs/AWS_RDS_CONNECTION.md` indica que el script de privilegios de la app no se los concede.

## Orden de dependencias

Para **insertar** (padres primero): `personas` -> `leads` -> (`consentimientos`, `asignaciones`, `auditoria`, `campanas_atribucion`,
`eventos_lead`, `citas`, `fichas_diagnosticas`, `ingesta_google_sheets`). `asesores` y los catalogos deben existir antes.

Para **borrar** (hijos primero): `api_idempotency`, `consentimientos`, `asignaciones`, `fichas_diagnosticas`, `citas`, `eventos_lead`,
`campanas_atribucion`, `ingesta_google_sheets` (solo las ligadas a un lead), `auditoria` (solo las que tienen lead o persona), `leads` y
al final `personas`. Es el orden que usa `scripts/dev_reset_leads.py` y lo que verifican sus pruebas
(`tests/unit/test_dev_reset_leads.py`).

El diagrama de relaciones esta en [02_PHYSICAL_SCHEMA.md](02_PHYSICAL_SCHEMA.md#mapa-de-relaciones-y-orden-de-dependencias).

## Adjuntos de las notas (S3)

- Bucket `tpi-dev-adjuntos-821656895812-us-east-2`, region `us-east-2`, cuenta `821656895812`, sin versionado.
- Clave de cada objeto: `leads/{id_lead}/{id_adjunto}` (`SolicitudService._attachment_key`).
- En la base solo queda una **marca** dentro de `tpi.leads.comentarios` (`[adjunto:tipo:uuid]`); no hay tabla de adjuntos. Al borrar un
  lead hay que borrar tambien sus objetos, porque ninguna clave foranea lo hace.
- Nadie puede leer un objeto de `leads/*` sin la etiqueta de escaneo `GuardDutyMalwareScanStatus=NO_THREATS_FOUND`. Listar y borrar
  requieren el perfil del humano (`tpi-dev`); la app no tiene `ListBucket`.
- Diseno completo en [../ADJUNTOS_COMENTARIOS_DISENO.md](../ADJUNTOS_COMENTARIOS_DISENO.md) e infraestructura en
  [../ADJUNTOS_INFRA_S3.md](../ADJUNTOS_INFRA_S3.md).

## Consultas utiles (solo lectura)

`tpi.auditoria` solo se puede leer con `tpi_admin` (`tpi_app` tiene unicamente `INSERT`).

```sql
-- Leads por estado
SELECT estado_lead, count(*) FROM tpi.leads GROUP BY 1 ORDER BY 2 DESC;

-- Leads sin asignacion activa (misma definicion que el dashboard y el listado)
SELECT count(*) FROM tpi.leads l
WHERE NOT EXISTS (
    SELECT 1 FROM tpi.asignaciones a
    WHERE a.id_lead = l.id_lead AND a.estado_asignacion = 'activa'
);

-- Carga actual por asesor
SELECT s.nombre, count(*) FROM tpi.asignaciones a
JOIN tpi.asesores s USING (id_asesor)
WHERE a.estado_asignacion = 'activa' GROUP BY 1 ORDER BY 2 DESC;

-- Leads sembrados por la herramienta de reinicio
SELECT estado_lead, count(*) FROM tpi.leads WHERE fuente_actual = 'seed_dev' GROUP BY 1;

-- Estado de la ingesta y cuantas filas quedaron ligadas a un lead
SELECT estado_procesamiento, count(*) AS filas, count(id_lead_generado) AS con_lead
FROM tpi.ingesta_google_sheets GROUP BY 1;

-- Acciones registradas en la auditoria
SELECT accion, count(*) FROM tpi.auditoria GROUP BY 1 ORDER BY 2 DESC;
```

"Estancado" (cinco dias o mas sin movimiento) no se reescribe a mano: su definicion unica esta en `app/repositories/lead_activity_sql.py`
(`ultimo_movimiento_expr` y `estancado_predicate`) y depende de la vista `tpi.v_historial_estado_lead`.

## Reinicio de los datos de DEV

Herramienta: [`scripts/dev_reset_leads.py`](../../scripts/dev_reset_leads.py). La ejecuta **el humano**, nunca el Harness ni el Deployer,
y solo contra DEV. Nacio como parte del criterio AC-7 de `CRM-ESTADOS-1-CATALOGO`.

### Que hace

| Modo | Efecto |
| ---- | ------ |
| `--inspeccionar` | Solo lectura: lista las tablas que dependen de `leads`/`personas` (directa o indirectamente), con filas y regla de borrado de cada FK. |
| (sin opciones) | Simulacion: muestra el destino, lo que borraria (conteos y objetos S3) y lo que sembraria. No escribe nada. |
| `--ejecutar` | Pide escribir la frase exacta `REINICIAR DEV`; borra todo lo anterior y siembra 100 leads ficticios completos. |
| `--sin-s3` | No toca el bucket (para ensayos en una base local). |

Siembra **100 leads**: 24 `nuevo`, 14 `asignado`, 12 `en_seguimiento`, 10 `sin_contacto`, 8 `reunion_agendada`, 5 de cada uno de
`reunion_realizada`, `ficha_generada`, `cerrado` y `no_interesado`, y 4 de cada uno de `datos_erroneos`, `no_contactado` y `perdido`. Los 76
que no son `nuevo` reciben una asignacion activa (con su evento `asignacion_lead` en `auditoria`) a los asesores activos; 20 leads activos
quedan sin movimiento hace mas de 5 dias para probar "estancados"; los avanzados llevan 1 a 3 notas con el encabezado que escribe la app.
Los datos son reproducibles con `--semilla`.

**Perfil de los leads (edad de jubilacion en Chile):** 50 hombres de 62 a 68 anios (centro 65) y 50 mujeres de 57 a 63 (centro 60), con
nombre de pila segun el sexo, estado civil concordante en genero (Casado/Casada...), RUT valido con digito verificador y correo
`@example.test`.

### Campos que se siembran (un lead completo, como lo deja la ingesta)

| Tabla | Campos |
| ----- | ------ |
| `personas` | `rut`, `nombre_completo`, `email`, `telefono`, `fecha_nacimiento`, `genero` y `estado_civil` (texto) |
| `leads` | `fecha_ingreso`, `afp_actual` + `afp_id`, `genero_id`, `estado_civil_id` (claves de los catalogos, que son las que muestra la app), `saldo_afp`, `comentarios` (consulta inicial del formulario + notas), `estado_lead`, `prioridad`, `origen_lead` (`formulario_web`), `fuente_actual` (`seed_dev`), `raw_payload` (fila original del formulario) |
| `consentimientos` | terminos y politica aceptados, `fecha_aceptacion`, versiones (`v1.0`), `ip_origen` (rangos de documentacion RFC 5737), `user_agent`, `finalidad_contacto` |
| `campanas_atribucion` | `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content` |
| `eventos_lead` | evento `lead_importado_sheets` con los ids de catalogo en `metadata` |
| `ingesta_google_sheets` | fila de origen `seed_dev`, carga original, estado `procesado`, lead generado |
| `asignaciones` y `auditoria` | solo para los leads que no son `nuevo` |

Antes de borrar nada, el script exige que los catalogos tengan los valores que necesita (`FEMENINO`, `MASCULINO`; `SOLTERO`, `CASADO`,
`DIVORCIADO`, `VIUDO`; las siete AFP): si falta alguno se detiene y no toca la base.

### Que conserva

`tpi.asesores`, los catalogos, los eventos de `auditoria` sin lead ni persona, las filas de `ingesta_google_sheets` que no generaron un
lead, los roles y los privilegios. No cambia el esquema.

### Barreras de seguridad

- Se niega (codigo 2, sin tocar nada) si el host no es local (solo se llega a DEV por el tunel), si el usuario no es `tpi_admin` o si la
  base no es `tpi`.
- Se niega si encuentra una tabla que depende de `leads`/`personas` y no esta en su lista conocida, aunque sea una dependencia indirecta.
- Toda la parte de base de datos va en una **transaccion**; el borrado en S3 se ejecuta antes del `commit` y, si falla, se revierte la base.
- Verifica que la cuenta AWS sea `821656895812` antes de listar o borrar objetos.

### Como se corre

Desde una terminal PowerShell **separada** de la del orquestador, en la carpeta de `tpi-backend`, con el tunel SSM a DEV abierto (puerto local
`5433`) y la sesion AWS vigente (`aws login --profile tpi-dev --remote`). La clave de `tpi_admin` se pide sin mostrarse y no se escribe en
ningun archivo:

```powershell
$env:APP_ENV = 'aws-dev'
$env:DATABASE_HOST = 'localhost'
$env:DATABASE_NAME = 'tpi'
$env:DATABASE_USER = 'tpi_admin'
$env:DATABASE_SCHEMA = 'tpi'
$env:DATABASE_SSLMODE = 'require'
$clave = Read-Host 'Clave de tpi_admin' -AsSecureString
$env:DATABASE_PASSWORD = [System.Net.NetworkCredential]::new('', $clave).Password
python scripts/dev_reset_leads.py --port 5433 --inspeccionar
python scripts/dev_reset_leads.py --port 5433
python scripts/dev_reset_leads.py --port 5433 --ejecutar
```

Si el tunel no esta abierto veras `connection timeout expired` / `server closed the connection unexpectedly`; con la terminal del
proyecto apuntando a la base local el script se niega por el usuario y la base. Las variables `$env:` solo viven en esa terminal.

### Simulacion del 2026-10-24 (evidencia previa al primer reinicio)

Lo que se **borraria** es lo que midio la simulacion de ese dia. La siembra de entonces era de 42 leads y no llenaba el sexo, el estado
civil ni la AFP en los catalogos; se reemplazo por la version de 100 leads completos descrita arriba antes de ejecutarla.

```text
Lo que se BORRARA:
  leads: 85                              eventos_lead: 69
  personas: 83                           fichas_diagnosticas: 0
  consentimientos: 82                    ingesta_google_sheets (ligadas a un lead): 69
  asignaciones: 34                       objetos de adjuntos en S3 (leads/): 7
  auditoria de leads/personas: 141
  api_idempotency: 2
  campanas_atribucion: 69
  citas: 0
Lo que se SEMBRARA (version inicial, reemplazada): 42 leads ficticios en 12 estados; asesores activos disponibles: 4
```

### Estado

El primer reinicio de DEV queda **pendiente de ejecucion por el humano** al cierre de este documento (criterio AC-7 de
`CRM-ESTADOS-1-CATALOGO`). Tras ejecutarlo, actualizar esta seccion con la fecha y los conteos sembrados.

## Usuarios de prueba por perfil en DEV

Los usuarios de la aplicacion en DEV viven en el secreto `tpi/dev/auth-users` de AWS Secrets Manager (Elastic Beanstalk lo inyecta como `AUTH_USERS_JSON`
con `aws:elasticbeanstalk:application:environmentsecrets`); no se versionan. La app lo lee una sola vez al arrancar: un cambio solo se ve tras
`RestartAppServer` o un `UpdateEnvironment`, que ejecuta el humano fuera del Harness.

Usuarios conocidos al 2026-10-26 (sin claves): `asesor.desarrollo1` y `asesor.desarrollo2` (rol `advisor`, perfil Runner, con `advisor_id`),
`diego.operaciones` (`ceo`) y `alvaro.operaciones` (`cto`) (perfil Socio), `h2-5d-smoke` (`tester`) y, mientras dure la prueba del perfil Coordinador,
`coordinador.ejemplo1` y `coordinador.ejemplo2` (rol `coordinator`, cada uno con su propio asesor en `tpi.asesores`).

Herramienta del humano: [`scripts/dev_usuarios.py`](../../scripts/dev_usuarios.py) (`listar`, `asesores`, `agregar`, `quitar`). Conserva a los usuarios existentes,
valida el resultado con el parser de la app, no imprime hashes ni claves, pide una frase de confirmacion antes de escribir y deja la version anterior del
secreto como `AWSPREVIOUS`. Las cuentas de prueba son sinteticas y su clave es igual al usuario: **desmontarlas con `quitar` cuando termine la prueba**.

Orden seguro para un rol nuevo: el rol `coordinator` solo lo entiende la version RBAC (`ba53777` en adelante); la version anterior no arranca si lo ve
(`Unknown auth role`), y un rollback con el usuario ya cargado tampoco levantaria. Por eso primero `asesores` (sin riesgo), despues del despliegue y de
`Ready/Green/Ok` se ejecuta `agregar` y se reinicia el servidor de la aplicacion.

### Socios y responsables de reuniones (migracion 010)

Tras aplicar la migracion `010` (`scripts/sql/010_extend_citas_agenda.sql`), `scripts/dev_usuarios.py` gana dos subcomandos (plan por defecto; escriben solo con
`--ejecutar` y su frase de confirmacion, y no imprimen hashes ni claves):

- `socios`: da de alta en `tpi.asesores` a los usuarios `ceo` y `cto` del secreto (rol `socio`, `atiende_reuniones = true`, nombre tomado del nombre visible).
  Idempotente: si el asesor ya existe por nombre, lo marca sin duplicarlo.
- `marcar-coordinadores`: pone `atiende_reuniones = true` en la fila de `tpi.asesores` de cada usuario `coordinator`, resuelta por su `advisor_id`. Los
  Coordinadores conservan rol `asesor`.

Ambos validan que la migracion `010` este aplicada (si falta `tpi.asesores.atiende_reuniones` se detienen con un mensaje claro) y se pueden repetir. La lista de
responsables de reuniones queda como `atiende_reuniones = true` (Socios CEO/CTO y Coordinadores marcados), nunca un Runner.

## Como mantener este documento

- Tras cada reinicio o cambio de esquema en DEV, volver a correr `--inspeccionar` y la simulacion y actualizar el inventario y la fecha.
- Si aparece una tabla nueva que dependa de `leads`/`personas`, agregarla al DDL de [02_PHYSICAL_SCHEMA.md](02_PHYSICAL_SCHEMA.md) y a
  `DEPENDIENTES_CONOCIDOS` y `borrar_todo` del script, con su prueba; el script se detiene mientras no se haga.
- Los datos reales no pasan por esta herramienta: la migracion a produccion es otro procedimiento.
