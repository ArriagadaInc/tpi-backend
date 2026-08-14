# Bitacora del Proyecto

## Proposito

Este documento es una bitacora viva para dar continuidad tecnica al proyecto.
La idea es que cualquier desarrollador pueda abrir este archivo y entender:

- que se hizo
- por que se hizo
- que problemas aparecieron
- como se resolvieron
- que falta por hacer
- que riesgos siguen abiertos

## Reglas de Actualizacion

- Agregar nuevas entradas arriba del historial, con fecha ISO `YYYY-MM-DD`.
- Registrar tareas, hallazgos, decisiones, riesgos y siguiente paso concreto.
- Cada vez que se actualice README.md, docs/ o documentacion operativa relevante, actualizar tambien esta bitacora en la misma tarea.
- No registrar secretos, passwords, endpoints con credenciales, ni datos personales reales.
- Si una tarea queda incompleta, dejar el ultimo estado confiable y el paso exacto para retomarla.
- Si una tarea toca base de datos o infraestructura, documentar impacto y rollback.
- En lo posible, enlazar archivos y documentos relevantes del repo.

## Snapshot Actual

Fecha de referencia: `2026-08-07`

- App principal: Streamlit
- Lenguaje: Python
- Base de datos: PostgreSQL
- Esquema principal: `tpi`
- Driver de acceso: `psycopg`
- Pool de conexiones: `psycopg_pool`
- Configuracion central: `app/config/settings.py`
- Capa de conexion: `app/database/connection.py`
- Healthcheck: `app/database/healthcheck.py`
- Servicio principal: `app/services/solicitud_service.py`
- Repositorio principal: `app/repositories/solicitud_repository.py`

## Estado Actual del Proyecto

- El MVP local funciona para registrar, consultar y visualizar metricas basicas.
- La conexion segura a PostgreSQL/Amazon RDS ya esta implementada en codigo.
- La configuracion por ambiente ya esta centralizada y tipada.
- El rol de aplicacion `tpi_app` ya tiene un script versionado de permisos.
- La validacion manual contra `tpi-postgres-dev` ya fue completada con `tpi_app`, SSL y limpieza posterior del dato sintetico.
- El hito AWS RDS ya fue mergeado a `main` y la CI posterior al merge quedo verde.
- El esquema contiene tablas de auditoria/eventos, pero el backoffice actual no las consume como auditoria funcional; la "trazabilidad" de la UI sigue siendo analitica sobre `tpi.leads`.
- No existe operacion de eliminacion ni desactivacion desde el backoffice.

## Donde Partir Si Tomas el Proyecto Hoy

Orden recomendado:

1. Leer `docs/AWS_RDS_CONNECTION.md`
2. Leer `docs/DECISIONES_TECNICAS.md`
3. Revisar `app/config/settings.py`
4. Revisar `app/database/connection.py`
5. Revisar `app/repositories/solicitud_repository.py`
6. Revisar `app/services/solicitud_service.py`
7. Ejecutar `python scripts/verify_database_connection.py`
8. Ejecutar `pytest`

## Mapa Rapido del Backoffice

Tablas realmente usadas por la app:

- Solo lectura:
  - `tpi.catalogo_afp`
  - `tpi.catalogo_genero`
  - `tpi.catalogo_estado_civil`
- Lectura y escritura:
  - `tpi.personas`
  - `tpi.leads`
  - `tpi.consentimientos`

Archivos clave:

- `app/streamlit_app.py`
- `app/pages/1_registrar_solicitud.py`
- `app/pages/2_solicitudes_registradas.py`
- `app/pages/3_trazabilidad.py`
- `scripts/sql/001_create_tpi_app_role.sql`
- `scripts/verify_database_connection.py`

## Historial Incremental

### 2026-08-14 - H2.2 pre-flight AWS DEV bloqueado por RDS no localizado

Contexto:

- Se inicio H2.2 para publicar Streamlit en Elastic Beanstalk Single Instance, sin cambios de negocio.
- Se actualizo `main` y se creo la rama `feat/h2-2-aws-dev-deployment`.

Pre-flight realizado:

- La identidad AWS configurada respondio correctamente y la region activa es `us-east-1`.
- La CI del commit H2.1 mergeado en `main` finalizo en estado `success`.
- La consulta no destructiva de RDS en la region activa no encontro la instancia `tpi-postgres-dev` ni otras instancias RDS disponibles.

Decision:

- No se crearon recursos Elastic Beanstalk, IAM, Secrets Manager ni Security Groups.
- No se modifico RDS ni su red.
- No se puede continuar sin confirmar la cuenta y region donde existe el RDS DEV o el identificador correcto de la instancia.

Siguiente paso:

- Recibir la cuenta/region autorizada y el identificador RDS correctos, luego repetir el inventario de red antes de cualquier cambio AWS.

### 2026-08-11 - Cierre tecnico H2.1: gates, lockfiles y compatibilidad Pydantic

Contexto:

- La preparacion inicial de despliegue quedo implementada, pero faltaba hacer exigible su calidad en CI y resolver un warning propio de Pydantic.

Tareas realizadas:

- Se migro la configuracion de modelos Pydantic a `ConfigDict` y se agrego una prueba de regresion para el metadata del schema.
- Se configuro cobertura minima global de 80 por ciento.
- Se convirtieron Bandit y `pip-audit` en quality gates bloqueantes.
- Se agrego el build de Docker como job obligatorio de CI.
- Se agregaron `requirements/runtime.lock` y `requirements/dev.lock`; Docker instala solo el lock de runtime.
- Se documento la Definition of Done permanente en `docs/ENGINEERING_STANDARDS.md`.

Decisiones:

- Los lockfiles fijan versiones exactas y se actualizaran de forma deliberada mediante pull request.
- `pip-audit` evalua el lock de runtime, evitando findings de paquetes ajenos al proyecto presentes en entornos compartidos.

Resultados de cierre:

- `docker build -t tpi-backoffice-h21 .` y `docker compose up --build` construyeron la imagen y levantaron PostgreSQL y Streamlit localmente.
- Streamlit respondio `200 ok` en `/_stcore/health`; el healthcheck del contenedor quedo `healthy` y el proceso corrio como `appuser`.
- `pytest tests -q --cov-fail-under=80` termino con `194 passed` y 82.92 por ciento de cobertura.
- Ruff, Black, MyPy y Bandit terminaron sin findings bloqueantes.
- `pip-audit` detecto cinco vulnerabilidades de GitPython 3.1.57; se actualizo el lock a 3.1.58 y la auditoria final quedo sin vulnerabilidades conocidas.

Warnings pendientes:

- Altair emite un warning de inferencia de tipo Vega-Lite para `interval` en pruebas de trazabilidad.
- Pytest puede emitir warnings de cache y limpieza de temporales en Windows por permisos del filesystem.
- Ambos warnings son externos al comportamiento de aplicacion y no bloquean la suite.

Pendiente:

- Consolidar los commits H2.1, publicar la rama y abrir PR contra `main`. No desplegar en AWS dentro de este hito.

### 2026-08-12 - Preparación técnica H2.1 para despliegue AWS DEV

Contexto:

- Se inició la preparación técnica para dejar Streamlit listo para un despliegue reproducible en AWS DEV sin ejecutar todavía el despliegue.
- El foco fue reforzar el arranque, la observabilidad, el healthcheck, la containerización y la documentación operativa.

Tareas realizadas:

- Se agregó `app/runtime.py` para centralizar logging, arranque seguro y manejo controlado de errores.
- Se agregó `scripts/healthcheck_runtime.py` como readiness check del contenedor.
- Se creó `.streamlit/config.toml` para que Streamlit escuche en `0.0.0.0`, en modo headless y con telemetría desactivada.
- Se endureció `Dockerfile` con Python 3.12 explícito, usuario no privilegiado, copia mínima de artefactos y healthcheck real.
- Se actualizó `docker-compose.yml` para validar readiness del servicio Streamlit.
- Se reforzaron `.gitignore` y `.dockerignore` para secretos, certificados y artefactos locales.
- Se actualizó `run_streamlit.bat` para un arranque portable en Windows.
- Se agregaron tests unitarios para runtime, healthcheck y aliases de ambiente.
- Se agregaron tests de integración para el healthcheck completo.
- Se documentó la preparación en `docs/H2_1_PREPARACION_DESPLIEGUE.md` y se enlazó desde `README.md`.

Aprendizajes:

- Streamlit necesita una configuración explícita para host no local si se quiere usar el mismo artefacto dentro de contenedores y servicios administrados.
- El healthcheck del contenedor no puede limitarse a “el proceso existe”; debe verificar también la dependencia principal.
- El logging debe salir por stdout/stderr y nunca depender de archivos locales para que sea usable por CloudWatch o por el runtime que corresponda.

Desafios:

- La suite completa de tests tarda lo suficiente como para requerir una ventana de ejecución amplia.
- En Windows, `pytest` deja warnings de limpieza de temp/cache ajenos a la lógica del proyecto.

Como se resolvio:

- Se validó primero la suite unitaria e integración de forma separada.
- Se aisló y volvió a verificar la regresión E2E de consultas antes de cerrar el bloque técnico.

Pendiente:

- Ejecutar la batería completa de calidad con tiempo suficiente y dejar el resumen final consolidado.

Siguiente paso:

- Correr `pytest tests -q`, `ruff`, `black`, `mypy`, `bandit` y `pip-audit` para consolidar evidencia.

### 2026-08-07 - Hito AWS RDS cerrado y mergeado a main

Contexto:

- El PR `#2` quedo aprobado despues de cerrar la validacion manual en Amazon RDS, dejar la CI verde y confirmar que no quedaron datos ficticios residuales en `tpi-postgres-dev`.

Tareas realizadas:

- Se corrigio la suite E2E de Streamlit para que `AppTest.from_file(...)` use rutas absolutas derivadas de la raiz real del repositorio.
- Se agrego un helper reutilizable en `tests/streamlit_test_utils.py` y una prueba unitaria de regresion para esa resolucion portable.
- Se verifico que la violacion `leads_afp_id_fkey` vista en logs de CI provenia de un test negativo de rollback y no de un defecto real de fixtures o catalogos.
- Se hizo `squash and merge` del PR `#2` hacia `main` con el commit final `976e7860cb4d534ed18a24989704c23f3708124c`.
- Se elimino la rama remota `feat-aws-rds-connection` despues de confirmar el merge.

Resultados:

- `main` contiene la integracion segura con Amazon RDS, el rol `tpi_app`, SSL obligatorio en AWS, el pool reutilizable, el healthcheck, las pruebas y el fix de `StreamlitDuplicateElementKey`.
- Los workflows post-merge en `main` quedaron en verde: `Lint & Format`, `Tests` y `Security Audit`.
- La validacion manual AWS quedo cerrada con estado final consistente: `79 -> 80 -> 79` leads y `0` personas asociadas al RUT ficticio al cierre.

Aprendizajes:

- Los tests E2E de Streamlit no deben depender del directorio actual de ejecucion; la ruta del script debe resolverse desde la raiz del repo.
- Un error de FK en logs de PostgreSQL no implica necesariamente un bug de aplicacion; primero hay que separar si viene de un test negativo esperado o de un flujo real.

Siguiente paso:

- Abrir el siguiente frente funcional sobre una base ya estabilizada: autenticacion/autorizacion, auditoria funcional o despliegue productivo, segun prioridad de negocio.

### 2026-08-07 - Cierre de validacion manual AWS y alineacion documental

Contexto:

- La validacion manual contra Amazon RDS `tpi-postgres-dev` quedo completada con `tpi_app`, SSL y limpieza posterior del dato sintetico.
- El estado final de RDS volvio a `79` leads y `0` personas asociadas al RUT ficticio.

Hallazgos relevantes:

- El esquema `tpi` contiene tablas operativas adicionales relacionadas por FK con `leads` y `personas`, incluyendo `auditoria`, `eventos_lead`, `citas`, `asignaciones`, `campanas_atribucion`, `fichas_diagnosticas` e `ingesta_google_sheets`.
- La UI actual del backoffice no consume esas tablas, pero ya no se debe documentar que el esquema carece de auditoria o eventos.

Alineacion realizada:

- El SQL versionado de `tpi_app` se ajusto al minimo privilegio validado: `CONNECT`, `USAGE`, `SELECT` sobre catalogos y `SELECT/INSERT/UPDATE` sobre `personas`, `leads` y `consentimientos`.
- Se eliminaron del script los grants genericos sobre secuencias y `ALTER DEFAULT PRIVILEGES`, porque el esquema validado no tiene secuencias y esos permisos ampliaban alcance innecesariamente.

Resultado:

- Flujo validado: Streamlit local -> pool psycopg -> SSL -> `tpi_app` -> Amazon RDS PostgreSQL.
- Estado final confirmado en AWS: `79` leads, sin datos ficticios residuales.

### 2026-08-07 - Correccion de bug en busqueda por RUT

Contexto:

- La validacion manual del backoffice contra Amazon RDS `tpi-postgres-dev` quedo correcta para conexion, lectura e insercion usando `tpi_app`.
- Durante esa validacion aparecio un error menor en `Solicitudes Registradas -> Buscar por RUT`.

Problema observado:

- La busqueda encontraba la solicitud correcta.
- El listado y el detalle podian renderizarse.
- Adicionalmente aparecia el mensaje `Error en la Busqueda` con texto generico.

Causa raiz:

- `render_solicitud_table()` reutilizaba el mismo `key` de Streamlit para los botones de detalle en el tab de listado y en el tab de busqueda.
- Si el mismo `id_lead` aparecia en ambos tabs durante el mismo render, Streamlit lanzaba `StreamlitDuplicateElementKey`.

Como se resolvio:

- Se agrego `key_prefix` a `render_solicitud_table()` en `app/components/ui.py`.
- La pagina `app/pages/2_solicitudes_registradas.py` ahora usa namespaces distintos: `listado` y `busqueda`.
- Se agrego una prueba de regresion E2E en `tests/e2e/test_consulta_solicitudes.py`.

Resultado:

- La busqueda ya no muestra el error generico en el escenario reproducido.
- No hubo cambios de arquitectura, permisos ni consultas SQL.
- La cobertura total subio a 83 por ciento en la suite completa posterior al fix.

Pendiente:

- Si se quiere reconfirmar el fix contra `aws-dev`, volver a cargar un entorno con `APP_ENV=aws-dev`, porque el entorno activo al cierre de esta correccion estaba resolviendo `local`.

### 2026-08-07 - Creacion de bitacora viva

Contexto:

- Se detecto la necesidad de dejar una memoria tecnica operativa para continuidad del proyecto.
- El repositorio tiene varias piezas de documentacion, pero no un hilo cronologico consolidado.
- Se definio ademas la regla de mantenimiento: toda actualizacion documental relevante debe reflejarse tambien en esta bitacora.

Tareas realizadas:

- Se creo esta bitacora en `docs/BITACORA.md`.
- Se consolido el estado actual del proyecto, sus piezas criticas y los siguientes pasos.
- Se dejo una estructura repetible para seguir agregando entradas.

Aprendizajes:

- La documentacion existente explica arquitectura, testing y despliegue, pero no reemplaza una bitacora incremental.
- Para continuidad real, el valor no esta solo en el "que", sino en el "por que", el "bloqueo" y el "siguiente paso".

Proximo paso:

- Mantener este archivo actualizado al cierre de cada tarea relevante.

### 2026-08-06 - 2026-08-07 - Conexion segura a PostgreSQL y AWS RDS implementada en codigo

Contexto:

- El proyecto necesitaba soportar local, testing, `aws-dev` y futura produccion sin hardcodear credenciales.
- La base `tpi` ya estaba restaurada en Amazon RDS y habia que dejar el backoffice listo para conectarse de forma segura.

Tareas realizadas:

- Se centralizo la configuracion de BD en `app/config/settings.py`.
- Se definio precedencia de configuracion:
  1. `DATABASE_URL`
  2. Variables `DATABASE_*`
  3. Defaults seguros solo para `APP_ENV=local`
- Se reforzo el pool reutilizable en `app/database/connection.py`.
- Se agrego clasificacion segura de errores de BD en `app/database/errors.py`.
- Se mejoro el healthcheck para validar `SELECT 1`, esquema, tabla `tpi.leads` y usuario efectivo.
- Se sanearon mensajes mostrados por Streamlit para no exponer informacion sensible.
- Se creo `scripts/sql/001_create_tpi_app_role.sql` para el rol de aplicacion `tpi_app`.
- Se documento la operacion en `docs/AWS_RDS_CONNECTION.md`.
- Se agregaron pruebas unitarias e integracion para configuracion, pool, errores y runtime de BD.

Resultados verificados:

- `pytest tests/ -p no:cacheprovider` -> `175 passed`
- Cobertura total -> `82%`
- `ruff check app tests scripts` -> OK
- `black --check app tests scripts` -> OK
- `mypy app --ignore-missing-imports` -> OK
- `bandit -r app -ll` -> OK
- `pip-audit` sobre dependencias del proyecto -> sin vulnerabilidades conocidas

Desafios encontrados:

- Habia documentacion con valores sensibles o demasiado parecidos a secretos reales.
- `pip-audit` detecto vulnerabilidades en los minimos de `pydantic-settings` y `python-dotenv`.
- En Windows, `pip-audit` requirio manejo especial por restricciones del directorio temporal.

Como se resolvio:

- Se reemplazaron ejemplos riesgosos por placeholders seguros en documentacion.
- Se elevaron los minimos de `pydantic-settings` a `2.14.2` y `python-dotenv` a `1.2.2`.
- Se ejecuto `pip-audit` de forma acotada sobre dependencias del proyecto, no sobre todo el entorno compartido.

Decisiones importantes:

- No se introdujo SQLAlchemy como segunda forma de acceso a BD.
- Se mantuvo `UPDATE` en `tpi_app`, pero sin `DELETE`.
- No se agrego RDS Proxy todavia; queda solo documentado para una etapa de mayor concurrencia.

Pendiente inmediato:

- Validacion manual contra `tpi-postgres-dev` usando `tpi_app`.

### 2026-08-07 - Preparacion de validacion manual en AWS RDS

Contexto:

- Se aprobo provisionalmente la implementacion local y se paso a cerrar solo la validacion manual contra Amazon RDS.

Hallazgos:

- El backoffice no usa tablas separadas de auditoria o eventos.
- La pagina de "trazabilidad" consume metricas y listados sobre `tpi.leads`.
- El MVP no tiene una operacion de UI para eliminar o desactivar leads.

Decision tomada:

- Crear el lead ficticio desde Streamlit usando `tpi_app`.
- Eliminarlo manualmente despues con `tpi_admin`.
- Dejar la ausencia de auditoria real registrada como deuda tecnica, sin implementarla en esta tarea.

Bloqueo actual:

- Falta ejecutar operativamente la creacion/habilitacion de `tpi_app` en RDS y luego validar la app contra `tpi-postgres-dev`.

Siguiente paso exacto:

- Abrir `psql` como `tpi_admin`, confirmar owners de tablas/secuencias y luego aplicar los grants para `tpi_app` sin exponer passwords en linea de comandos.

### 2026-08-01 - Validacion MVP1 local documentada

Contexto:

- El MVP1 quedo validado para demostracion local antes del trabajo de AWS.

Estado consolidado:

- Registro de solicitudes funcionando.
- Consulta de solicitudes funcionando.
- Trazabilidad basica funcionando.
- Validadores de RUT, email y telefono operativos.
- Persistencia en PostgreSQL local funcionando.

Documentos de referencia:

- `docs/INFORME_CORRECCION_MVP1.md`
- `docs/MVP1_VALIDACION.md`
- `docs/PROJECT_STATUS.md`

## Aprendizajes Acumulados

- No introducir una segunda estrategia de conexion a BD si `psycopg` + `psycopg_pool` ya cubre el caso.
- En Streamlit, el pool debe vivir fuera del rerun normal o quedar cacheado como recurso.
- Los healthchecks utiles no solo prueban `SELECT 1`; tambien deben probar esquema, tabla critica y usuario efectivo.
- Este repo no tiene migraciones formales; el esquema minimo vivo esta reflejado en `scripts/init_test_database.py`.
- La app hoy no tiene ciclo de vida para "desactivar" leads; si eso pasa a ser requisito, hay que diseniarlo explicitamente.
- La documentacion no debe incluir secretos reales ni placeholders ambiguos que parezcan credenciales activas.

## Desafios Recurrentes y Como Resolverlos

### 1. Confusion entre ambientes

Sintoma:

- La app parece funcionar en local, pero apunta a otra base o a otra combinacion de variables.

Resolucion:

- Revisar `APP_ENV`.
- Revisar precedencia entre `DATABASE_URL` y `DATABASE_*`.
- Ejecutar `python scripts/verify_database_connection.py`.

### 2. Errores de conexion poco accionables

Sintoma:

- El usuario ve solo un fallo generico en Streamlit.

Resolucion:

- Revisar logs del modulo de BD.
- Confirmar si el error es DNS, timeout, credenciales, SSL o pool.
- Ver `app/database/errors.py`.

### 3. Diferencia entre "trazabilidad" y "auditoria"

Sintoma:

- Se asume que la app ya registra eventos o historial de cambios.

Resolucion:

- Aclarar que el esquema si contiene tablas de auditoria/eventos, pero la UI actual no las consume como auditoria funcional.
- Si se necesita auditoria real en el backoffice, planificar la integracion explicita de esas tablas o un flujo nuevo de eventos.

### 4. Limpieza de datos de prueba

Sintoma:

- Se necesita crear un lead sintetico en ambientes compartidos.

Resolucion:

- Crear solo datos ficticios claramente identificables.
- Registrar conteo inicial y final.
- Si la app no soporta eliminacion, limpiar manualmente con rol administrativo y dejar trazabilidad de la accion.

## Deuda Tecnica

- Integrar en el backoffice una auditoria funcional sobre las tablas/eventos existentes o redisenar ese flujo si el modelo actual no alcanza.
- Autenticacion y autorizacion por roles.
- Operacion formal para desactivar o archivar leads.
- Integracion de secretos de produccion con AWS Secrets Manager.
- Uso de `sslmode=verify-full` con CA bundle en produccion.
- Migrar modelos Pydantic desde `Config` class-based a configuracion moderna.

## Proximos Pasos

### Operativos inmediatos

1. Definir la siguiente prioridad despues del cierre AWS: autenticacion, auditoria funcional o despliegue productivo controlado.
2. Si el siguiente paso es despliegue, preparar inyeccion de secretos via entorno o AWS Secrets Manager sin reintroducir credenciales en archivos versionados.
3. Si el siguiente paso es funcional, decidir si la UI debe consumir tablas de `auditoria`/`eventos_lead` existentes o si se requiere otro modelo de trazabilidad.
4. Mantener `scripts/verify_database_connection.py` como smoke test previo a cualquier cambio de ambiente.

### Proximos pasos funcionales

1. Autenticacion del backoffice.
2. Roles y permisos de usuario.
3. Auditoria de eventos.
4. Edicion controlada de solicitudes.
5. Flujo oficial de archivado o baja logica.

## Nice to Have

- Runbook de incidentes operativos.
- Script automatizado para smoke test seguro por ambiente.
- Pagina interna de diagnostico tecnico para administradores.
- Makefile o task runner unico para pruebas, lint y validaciones.
- Dashboard de salud tecnica con pool, latencia y errores de BD.

## Checklist de Retoma

Antes de continuar el proyecto, verificar:

- `.env` local presente y no versionado
- `APP_ENV` correcto
- base objetivo correcta
- `python scripts/verify_database_connection.py`
- `pytest`
- `git status --short`
- lectura de esta bitacora y de `docs/AWS_RDS_CONNECTION.md`

## Plantilla de Nueva Entrada

Usar esta estructura:

```md
### YYYY-MM-DD - Titulo breve

Contexto:

- ...

Tareas realizadas:

- ...

Aprendizajes:

- ...

Desafios:

- ...

Como se resolvio:

- ...

Pendiente:

- ...

Siguiente paso:

- ...
```
