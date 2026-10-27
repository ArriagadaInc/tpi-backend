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

### 2026-10-27 - CRM agenda 4b: eventos de la agenda en el historial y casos por asesor por perfil (CRM-AGENDA-4-HISTORIAL)

- Desarrollo (clase A): los eventos de la agenda (agendada, reagendada, cancelada, realizada y no asistio) aparecen en
  la linea de tiempo del historial del lead, leidos solo de `tpi.v_historial_agenda` (migracion 011) unida a
  `tpi.asesores` por `responsable_id` (LEFT JOIN) para el nombre del responsable, ordenados por `fecha_hora DESC,
  id_auditoria DESC`. Cadena: `AgendaRepository.get_lead_agenda_events` (la consulta no menciona `tpi.auditoria` ni
  `tpi.citas`), `AgendaService.get_lead_agenda_events`, `SolicitudService.get_lead_agenda_events` (protocolo
  `LeadBoardService` y su fake en `app/web/dependencies.py`), y `build_timeline_items` con `kind='agenda'` (rank entre
  `state_change` y `note`). El detalle muestra los cinco textos con la insignia «Automatico» y el actor; «responsable
  no disponible» si el responsable no se resuelve; sin ids internos, nota ni motivo de cancelacion.
- Alcance y degradacion (AC-4): los eventos se cargan solo cuando el lead es visible (mismo control del detalle); un
  Runner no obtiene eventos de un lead ajeno y, si la lectura de la vista falla, el detalle responde 200 con el resto
  del historial, sin lineas de agenda y sin volcar el error.
- Dashboard ejecutivo (AC-5): el Resumen por asesor y su detalle «Ver casos por estado y asesor» agrupan a los asesores
  por perfil (Coordinador = `rol='asesor'` + `atiende_reuniones=true`; Runner = `rol='asesor'` + `atiende_reuniones=false`;
  Socios defensivo). El repositorio trae `rol` y `atiende_reuniones` en las mismas consultas; el servicio calcula el
  grupo; la presentacion arma los grupos con subtotal de conteos (los tiempos muestran «—») y estado vacio por grupo.
  «Sin asesor» sigue aparte.
- Pruebas: unitarias de presentacion (`test_agenda_historial_timeline_presentation.py`,
  `test_asesor_groups_presentation.py`, `test_asesor_groups_render.py`), repositorio (`test_agenda_historial_repository.py`),
  servicio (`test_agenda_service.py`, `test_executive_dashboard_service.py`) y web (`test_agenda_historial_web.py`), y de
  integracion (`test_agenda_repository.py`, `test_executive_dashboard_per_advisor.py`). Documentacion en
  `docs/AGENDA_USO.md` (seccion 7), `docs/H3_3_4_DASHBOARD_DESIGN.md` y `CHANGELOG.md`.

### 2026-10-27 - Harness: tarea CRM-AGENDA-4-HISTORIAL-MIGRACION cerrada (DONE)

- Titulo: CRM agenda 4a: vista de solo lectura con los eventos de la agenda para el historial del lead
- Evidencia: `evidence/CRM-AGENDA-4-HISTORIAL-MIGRACION/` y `tasks/completed/CRM-AGENDA-4-HISTORIAL-MIGRACION.yaml`.
- release_sha: `bfa288f63c3de6a0838fcf7b4a76770c6570f5d6`
- pr_number: `148`
- Cierre automático por `merged_no_deploy` (clase D sin despliegue), 1 ronda. Pendiente del humano (AC-6): aplicar la migración 011 en AWS DEV desde `bfa288f` (script humano con simulación previa); después se activa `CRM-AGENDA-4-HISTORIAL`.

### 2026-10-27 - Agenda: migración 011 lista para el humano (CRM-AGENDA-4-HISTORIAL-MIGRACION)

- Qué se hizo: vista de solo lectura `tpi.v_historial_agenda` (migración `011`, clase D) sobre `tpi.auditoria` para
  que el historial del lead muestre los eventos de la agenda sin leer la tabla directamente (mismo patrón de mínimo
  privilegio de las migraciones 007 a 009). Filtro fijo `accion IN ('cita_agendada', 'cita_reagendada',
  'cita_cancelada', 'cita_realizada', 'cita_no_asistio') AND tabla_afectada = 'tpi.citas'`; columnas tipadas
  (`id_cita` y `responsable_id` como UUID, `fecha_hora_anterior`/`fecha_hora_nueva` como TIMESTAMPTZ); `security_barrier`;
  `REVOKE ALL FROM PUBLIC` y `GRANT SELECT` solo a `tpi_app`; sin índice nuevo (reutiliza `auditoria_state_history_idx`).
- Reversa idempotente `scripts/sql/011_drop_historial_agenda.sql` (REVOKE SELECT + DROP VIEW IF EXISTS); no toca
  `tpi.auditoria` ni las vistas 007/008/009.
- Pruebas: unitarias de contrato (`tests/unit/test_agenda_historial_migration_scripts.py`) y de integración
  (`tests/integration/test_agenda_historial_view.py`) que producen las filas con el flujo real de `AgendaRepository`
  (agendar, reagendar, cancelar, realizada y no asistió) y demuestran que la nota y el motivo de cancelación no llegan
  a la vista.
- `scripts/init_test_database.py` crea la misma vista para el bootstrap de pruebas; documentación en
  `docs/database/` (02 y 04), `docs/AGENDA_REUNIONES_DISENO.md` y `CHANGELOG.md`.
- Pendiente: la aplica el humano en AWS DEV (change_class D, `deploy_required: false`); el código que la usa es la
  tarea siguiente `CRM-AGENDA-4-HISTORIAL`.

### 2026-10-27 - Agenda: definidas las tareas del historial del lead y de los casos por asesor

- Pedido del humano (2026-10-27): (1) en el dashboard, la tabla de casos por asesor debe separar coordinadores de runners (los socios no van: no tienen cartera asignada); (2) quitar el botón
  Continuar del simulador y mejorar su aspecto (pendiente, va después); (3) los eventos del agendamiento deben quedar en el historial del lead. Orden acordado: 3, luego 1, luego 2.
- Los puntos 3 y 1 se definen como dos tareas porque la aplicación no lee `tpi.auditoria` (solo vistas sanitizadas, migraciones 007 a 009), así que el historial necesita una vista nueva:
  - `CRM-AGENDA-4-HISTORIAL-MIGRACION` (clase D, `deploy_required: false`): migración 011, vista `tpi.v_historial_agenda`. La aplica el humano en DEV.
  - `CRM-AGENDA-4-HISTORIAL` (clase A): eventos de la agenda en el historial del lead y casos por asesor separados en Coordinadores y Runners. Se activa cuando la migración esté aplicada.
- Sin activar ninguna todavía.

### 2026-10-27 - Se retira la referencia visual de la agenda y cambia la fecha de vigencia de la Ley 21.719

- Se retira `docs/ui/referencia/agenda/` de `main`: la tarea `CRM-AGENDA-3-LOOK` está cerrada (PR 144 y cierre en el PR 145) y su README pedía retirarla al cerrar. El resultado vive en `app/web/` y las
  carpetas `docs/ui/referencia/estados/` y `docs/ui/referencia/ui1/` no se tocan.
- Fecha de la Ley 21.719: el humano confirmó el 2026-10-27 que entra en vigencia el **2027-10-01** (se creía 2026-12-01, que es lo que dicen las guías públicas consultadas y el PDF del protocolo
  de runners). Se actualizan el backlog (`CRM-NO-CONTACTAR-1`) y el diseño de la agenda; las entradas anteriores de esta bitácora quedan como estaban porque reflejan lo que se sabía en ese momento.
  `CRM-NO-CONTACTAR-1` sigue siendo requisito antes de usar la agenda con datos reales, ya sin la presión de diciembre de 2026.

### 2026-10-27 - Harness: tarea CRM-AGENDA-3-LOOK cerrada (DONE)

- Titulo: CRM agenda 3: nuevo aspecto de la agenda, contraste del historial y logo como acceso al sitio
- Evidencia: `evidence/CRM-AGENDA-3-LOOK/` y `tasks/completed/CRM-AGENDA-3-LOOK.yaml`.
- release_sha: `d8b8eeccb90314191bc74fb1c7276e74f938a208`
- pr_number: `144`
- application_version: `h3-crm-agenda-3-look-d8b8eec-domainlocked-r1`
- bundle_sha256: `8adec16a980bd6aa0da395cfb24e9034226f11d8093e7e21824730f55c283bb3`
- lkg: `h3-crm-agenda-2-calendario-a4a5bee-domainlocked-r1`
- deployment: `success`
- deployed_commit: `d8b8eeccb90314191bc74fb1c7276e74f938a208`
- verification: `PASS`

**Resultado.** El nuevo aspecto de la agenda está en DEV: semana por horas con reuniones simultáneas lado a lado, leyenda de responsables que filtra, lista por día, tarjeta Reunión y
formulario rediseñados, historial del lead con fondo `--surface-soft` (más contraste) y barra superior sin el botón Home, con el logo de TPI como enlace al sitio público (solo con sesión y
con la URL aprobada, en pestaña nueva y con `rel="noopener noreferrer"`). Sin dependencias ni librerías nuevas. El humano aceptó el AC-7 (revisión visual en DEV) el 2026-10-27 (12:12Z).

**Una sola ronda, sin rework.** El Reviewer aprobó a la primera. Observaciones: dos archivos Python de la referencia (`agenda_presentation.py` y `routes/agenda.py`) no pasaban `black --check`, así que el
Developer los formateó y difieren de la referencia solo en saltos de línea (AST idéntico, verificado por el Reviewer); la falla fue mía al armar la referencia sin formatear. Los seis templates y el CSS
quedaron idénticos a la referencia.

**Lecciones de operación.**

1. *Los archivos Python de una referencia visual deben pasar `black` antes de publicarse como referencia*; si no, el criterio de identidad literal choca con el gate de formato del CI.
2. *La sesión AWS (`tpi-dev`) caduca a las 12 h*: la aceptación humana llegó tras ese plazo y el preflight del Deployer devolvió `expired` hasta renovarla con `aws login --profile tpi-dev --remote`. Mientras el
   orquestador espera la aceptación no lanza turnos nuevos ni gasta saldo de la API.

**Pendiente.** Retirar de `main` la carpeta `docs/ui/referencia/agenda/` (su README lo indica al cerrar la tarea).

### 2026-10-27 - Agenda: implementado el nuevo aspecto (CRM-AGENDA-3-LOOK)

- Qué se hizo: se copiaron los ocho archivos de `docs/ui/referencia/agenda/` a sus rutas de destino en `app/web/`
  (`base.html`, `agenda.html`, `agenda_form_fields.html`, `agenda_macros.html`, `reunion_card.html`, `app.css`,
  `agenda_presentation.py` y `routes/agenda.py`), idénticos a la referencia ignorando fines de línea (AC-1).
- Pruebas nuevas: `tests/unit/test_agenda_presentation.py` (helpers de presentación: `color_map`, `rango_label`,
  `etiqueta_dia`, `_asignar_carriles`, `build_week_grid`, `resumen_semana`, `agrupar_por_dia` y `meeting_tile`);
  pruebas de conservación de los parámetros de la URL en `/agenda` (filtro por responsable, navegación por semanas y
  selector Semana/Lista); y pruebas del CSS de `.timeline-item` (claro con `--surface-soft`, oscuro sin cambios).
- Pruebas actualizadas: `tests/unit/test_web_app.py` (el botón Home pasa a ser el logo `a.brand-link`, sin debilitar la
  protección de la URL aprobada: `target="_blank"` y `rel="noopener noreferrer"`).
- Las 101 pruebas de agenda existentes siguen pasando. Sin dependencias, tipografías, scripts ni librerías nuevas.
- Documentación: `docs/AGENDA_USO.md` (vistas nuevas) y `docs/UI_DESIGN_SYSTEM.md` (nota de los patrones nuevos).

### 2026-10-26 - Agenda: el logo sustituye al botón Home (se suma a CRM-AGENDA-3-LOOK)

- Pedido del humano: quitar el botón **Home** de la barra superior y llegar al home presionando el logo de TPI.
- Interpretación: el botón enviaba al sitio público aprobado (`TPI_PUBLIC_SITE_URL`, lista permitida en `app/components/urls.py`); el logo toma ese mismo destino. Se mantiene todo lo
  que protegían las pruebas: solo con sesión iniciada, solo con la URL aprobada (si falta o no está aprobada, el logo queda sin enlace), pestaña nueva y `rel="noopener noreferrer"`.
- Qué se hizo: cambio en la vista previa local (verificado: 0 botones Home, logo con el `href` aprobado), referencia actualizada (`base.html` y `app.css`) y la tarea
  `CRM-AGENDA-3-LOOK` ampliada con un criterio nuevo (AC-6) que actualiza las pruebas del botón Home sin debilitarlas. Sigue sin activarse.

### 2026-10-26 - Agenda: nuevo aspecto aprobado y tarea CRM-AGENDA-3-LOOK definida

- Contexto: con la agenda v1 funcionando en DEV, el humano pidió mejorar su look and feel (moderno, alineado con la UX del CRM y fácil de entender) y, como anexo,
  oscurecer el fondo de los comentarios del historial del lead para que contrasten (igual que la solicitud original).
- Qué se hizo: una vista previa local con datos ficticios (17 reuniones, tres perfiles, claro y oscuro, celular), construida con la skill `ui-ux-pro-max` sobre el
  sistema visual existente. El humano la aprobó el mismo día. Las 101 pruebas de agenda existentes pasan sin cambios con esa versión.
- Qué se agrega: la referencia exacta en `docs/ui/referencia/agenda/` (siete archivos y un README) y la tarea activable `CRM-AGENDA-3-LOOK` (clase A, con despliegue y
  revisión visual humana). Solo estética: no cambian reglas, permisos, privacidad de los leads ajenos ni CSRF.
- Qué cambia: la página Agenda (cuadrícula por horas con carriles para reuniones simultáneas, línea de «ahora», leyenda de responsables que también filtra, resumen de la
  semana, lista por día para celular), la tarjeta Reunión y el formulario de agendar, y el fondo `--surface-soft` de `.timeline-item`. La tarjeta Reunión ahora lleva relleno interno
  (antes el texto quedaba pegado al borde).
- Detalle técnico a vigilar: en Jinja una clave de diccionario llamada `items` choca con el método `dict.items`; por eso la agrupación por día usa `reuniones`.

### 2026-10-26 - Harness: tarea CRM-AGENDA-2-CALENDARIO cerrada (DONE)

- Titulo: CRM agenda 2: calendario comun, agendar desde el lead y estados de la reunion
- Evidencia: `evidence/CRM-AGENDA-2-CALENDARIO/` y `tasks/completed/CRM-AGENDA-2-CALENDARIO.yaml`.
- release_sha: `a4a5beec1265730a5eb537bc3bb8d430882d23bd`
- pr_number: `140`
- application_version: `h3-crm-agenda-2-calendario-a4a5bee-domainlocked-r1`
- bundle_sha256: `08353be998de7097c65d7e97e93e2e6c4a3a6fb38a81bb8755bb4be777402c68`
- lkg: `h3-crm-perfiles-1-rbac-ba53777-domainlocked-r1`
- deployment: `success`
- deployed_commit: `a4a5beec1265730a5eb537bc3bb8d430882d23bd`
- verification: `PASS`


**Resultado.** La agenda de reuniones (v1) está en DEV: calendario común, tarjeta Reunión y formulario en el detalle del lead, reagendar, cancelar con motivo y marcar
realizada o no asistió (estas dos solo Coordinador y Socio). El responsable lo valida el servidor (el Runner solo elige Socios; el Coordinador solo es responsable de leads de su
cartera) y el cambio de estado del lead ocurre en la misma transacción que la reunión. El humano aceptó el AC-9 con los tres perfiles el 2026-10-26 (23:04Z).

**Una ronda de rework.** El Reviewer rechazó la primera entrega por un bloqueante (no se exigía que el lead estuviera activo: agendar sobre un lead cerrado o perdido lo reabría
como «Reunión agendada»), dos mayores (faltaba la matriz de permisos completa y una prueba que leyera el HTML del calendario para un lead ajeno; una prueba de «solo lectura» pasaba
por el token CSRF y no por el permiso) y tres menores (la vista de semana seguía visible en celular, el orden de las validaciones dejaba inferir el dueño de un lead ajeno y el motivo
de cancelación en texto libre iba a la auditoría). Aprobó la segunda entrega.

**Lecciones de operación.**

1. *Una tarea de permisos y datos personales vuelve a exigir la matriz completa de pruebas desde la primera entrega*, igual que `CRM-PERFILES-1-RBAC`. Conviene ponerlo en las
   restricciones de cada tarea de este tipo, con el ejemplo de la prueba que pasa por el motivo equivocado.
2. *La API de Claude se quedó sin saldo prepagado en plena revisión* («Credit balance is too low»): el Reviewer murió a los 2 minutos y el orquestador se detuvo. Tras recargar y relanzar
   desde la terminal del humano (la clave solo existe ahí) el arnés retomó en `REVIEWING` sin perder trabajo.
3. *Al cerrar `CRM-AGENDA-1-MIGRACION` con `deploy_required: false` la tarea no pasó por `BLOCKED_HUMAN`* aunque la clase era D: la aplicación de la migración quedó como paso manual del humano,
   con un script que simula primero. La nota del Deployer decía lo contrario.

**Pendiente.** Desmontar las cuentas de prueba `coordinador.ejemplo1` y `coordinador.ejemplo2` cuando termine la ronda de pruebas de la agenda
(`python scripts/dev_usuarios.py quitar --ejecutar` y `restart-app-server`). `CRM-NO-CONTACTAR-1` sigue pendiente y debe cerrarse antes de usar la agenda con datos reales (Ley 21.719 desde el 2026-12-01).

### 2026-10-26 - Harness: tarea CRM-AGENDA-1-MIGRACION cerrada (DONE); la migración 010 queda por aplicar en DEV

- Titulo: CRM agenda 1: ampliar tpi.citas y tpi.asesores, privilegios y scripts de altas
- Evidencia: `evidence/CRM-AGENDA-1-MIGRACION/` y `tasks/completed/CRM-AGENDA-1-MIGRACION.yaml`.
- release_sha: `c76ec21f9fec9defcc08ed5cb85e40494c9cac16`
- pr_number: `138`
- Resultado: una sola ronda (el Reviewer aprobó el PR #138 en unos 4 minutos con CI verde y 8 pruebas de integración de la migración). Con `deploy_required: false` el
  merge pasó por `merged_no_deploy` a `DONE` y el arnés cerró solo. La nota del Deployer dice que la clase D lleva a `BLOCKED_HUMAN`; en la práctica no ocurrió, y no
  cambia el resultado porque la aplicación de la migración nunca fue un paso del arnés.
- **Pendiente del humano (AC-6): aplicar la migración 010 en AWS DEV** con `tpi_admin` (antes se comprobó `btree_gist`: disponible 1.7 y `tpi_admin` es `rds_superuser`) y
  luego ejecutar `socios` y `marcar-coordinadores` de `scripts/dev_usuarios.py`. Hasta entonces `CRM-AGENDA-2-CALENDARIO` no puede activarse.
- Observaciones menores del Reviewer, sin bloquear: `marcar-coordinadores` no avisa si un `advisor_id` no existe en `tpi.asesores`; `socios` busca por nombre y fija
  `rol = 'socio'`, así que un nombre que coincida con el de un asesor real lo sacaría de la cartera (la simulación por defecto lo muestra antes de escribir).

### 2026-10-26 - Agenda de reuniones: migración 010 lista para el humano (CRM-AGENDA-1-MIGRACION)

- Migración de clase D que amplía `tpi.citas` y `tpi.asesores` para la agenda (sección 6 de `docs/AGENDA_REUNIONES_DISENO.md`).
- Forward `scripts/sql/010_extend_citas_agenda.sql`: `btree_gist` (la restricción EXCLUDE lo exige; preflight que aborta con mensaje claro), en `tpi.citas`
  `id_asesor NOT NULL`, `fecha_hora_fin` (CHECK > `fecha_hora`), `agendada_por_subject`/`agendada_por_nombre`, `nota`, `motivo_cancelacion`, `updated_at`,
  CHECK de `estado_cita` (agendada/realizada/no_asistio/cancelada), índice único parcial `citas_one_agendada_per_lead_uq` (una agendada por lead), índice
  `citas_fecha_hora_idx` y exclusión `citas_responsable_no_superposicion_excl` (el responsable no se pisa); en `tpi.asesores` `atiende_reuniones BOOLEAN NOT NULL
  DEFAULT false`; `REVOKE ALL FROM PUBLIC` + `GRANT SELECT, INSERT, UPDATE` a `tpi_app` sobre `tpi.citas` (sin DELETE, sin tocar auditoría).
- Reversa `scripts/sql/010_drop_citas_agenda.sql` transaccional e idempotente: quita índices, restricciones, columnas nuevas y privilegios; aborta si `tpi.citas`
  tiene filas; no elimina la tabla, ni `btree_gist`, ni toca `tpi.auditoria`.
- Bootstrap `scripts/init_test_database.py`: crea `tpi.citas` en su forma final (DDL original de `tpi-data-pipeline` + 010) y `tpi.asesores.atiende_reuniones`;
  agrega `CREATE EXTENSION btree_gist`.
- `scripts/dev_usuarios.py` gana `socios` (alta idempotente de CEO/CTO con rol `socio` y `atiende_reuniones = true`) y `marcar-coordinadores` (marca por
  `advisor_id`, conservan rol `asesor`); ambos validan la 010 aplicada y son plan por defecto.
- Pruebas: contrato estático de ambos scripts (`tests/unit/test_agenda_migration_scripts.py`), unitarias de los subcomandos (`tests/unit/test_dev_usuarios.py`) e
  integración forward/reversa y restricciones (`tests/integration/test_citas_agenda_migration.py`).
- Pendiente del humano: comprobar que RDS permite `btree_gist` y aplicar la 010 en AWS DEV con `tpi_admin` (clase D, Human Gate), luego `socios` y
  `marcar-coordinadores` y comprobar la lista de responsables.

### 2026-10-26 - Agenda de reuniones: tareas definidas (CRM-AGENDA-1-MIGRACION y CRM-AGENDA-2-CALENDARIO)

- Decisiones del humano: «el Coordinador solo puede agendar sus leads y los Runner solo pueden asignar reuniones a los Socios»; `CRM-NO-CONTACTAR-1` queda para
  después. Con eso el punto J del diseño queda resuelto y no quedan preguntas abiertas (`docs/AGENDA_REUNIONES_DISENO.md`).
- `CRM-AGENDA-1-MIGRACION` (clase D, `deploy_required: false`): migración 010 que amplía `tpi.citas` y `tpi.asesores`, su reversa, el bootstrap de pruebas, la documentación
  de la base y dos subcomandos humanos de `scripts/dev_usuarios.py` (`socios` y `marcar-coordinadores`). La aplica el humano en DEV tras comprobar que RDS permite
  `btree_gist`. Sin dependencias.
- `CRM-AGENDA-2-CALENDARIO` (clase A, con despliegue y aceptación humana): reglas de la reunión, calendario común, tarjeta en el detalle del lead, permisos por perfil
  (el servidor decide quién puede ser responsable), privacidad del calendario, auditoría y matriz de pruebas completa. Depende de la anterior.
- Orden: la agenda no debe usarse con datos reales hasta cerrar `CRM-NO-CONTACTAR-1` (la ley rige desde el 2026-12-01).

### 2026-10-26 - Agenda de reuniones: decisiones confirmadas (CRM-AGENDA)

- Contexto: el humano respondió «de acuerdo con todo» a los supuestos del diseño (`docs/AGENDA_REUNIONES_DISENO.md`, PR 135) con dos precisiones.
- Decisión 6: para la agenda, **Socio = solo CEO y CTO** (Diego y Álvaro en DEV). Pepe y María de los Ángeles quedan fuera por ahora; sumarlos es una fila.
- Decisión 7: **la reunión con el lead la hacen los Socios y los Coordinadores**. El Runner agenda, pero no puede ser el responsable.
- Consecuencia en el modelo: los Coordinadores conservan `rol = 'asesor'` en `tpi.asesores` (la cadena de cartera lo exige), así que se agrega la columna
  `atiende_reuniones` para distinguir a quién puede ser responsable. La migración `CRM-AGENDA-1-MIGRACION` la incluye.
- Sigue abierto el punto J: un Coordinador solo sería responsable de leads de su cartera (propuesta), porque las carteras son independientes y, si no, atendería una
  reunión sin poder ver al lead. Tampoco se eligió el orden respecto de `CRM-NO-CONTACTAR-1`.

### 2026-10-26 - Agenda de reuniones del CRM: diseño y decisiones (CRM-AGENDA)

- Contexto: el humano pidió un módulo de agendamiento para que los Runners agenden a los Socios cuando un lead es positivo y quiere asesoría.
- Decisión del humano: la v1 es un **calendario propio y común** (todos lo ven y todos pueden agendar), con el **responsable de la asesoría** y **quién agendó**
  en cada reunión; sincronizaciones y lo demás van en la v2.
- Qué se agrega: `docs/AGENDA_REUNIONES_DISENO.md` (decisiones, supuestos a confirmar, flujo, permisos por perfil, modelo de datos, pantallas, auditoría, v2 y criterios)
  y dos tareas en el backlog, `CRM-AGENDA-1-MIGRACION` (clase D) y `CRM-AGENDA-2-CALENDARIO` (clase A). `CRM-AGENDAMIENTO` queda con el resto del protocolo
  (intentos, cadencia, calificación, panel por runner y agenda v2).
- Hallazgos del código que moldean el diseño: `tpi.citas` ya existe (0 filas) y se amplía en vez de crear otra tabla; el Runner no puede fijar `reunion_realizada`,
  así que marcar «realizada» y «no asistió» es de Coordinador y Socio; las consultas de asignación y de cartera filtran por `rol = 'asesor'`, de modo que los Socios
  pueden vivir en `tpi.asesores` con `rol = 'socio'` sin entrar al reparto.
- Pendiente del humano: confirmar la sección 10 del documento (Socios responsables, horario y duración, privacidad del calendario común, quién marca asistencia,
  avisos y orden respecto de `CRM-NO-CONTACTAR-1`). Sin código ni migración todavía.

### 2026-10-26 - Harness: la regla de logs deja de bloquear verificaciones por robots de internet (HARNESS-LOGS-FALSOS-POSITIVOS-CADDY)

- Contexto: la verificación de `CRM-ESTADOS-1-CATALOGO` quedó en `FAIL` por 1 coincidencia del indicador fuerte `secret` que era una línea de acceso de Caddy
  de un robot que pidió `GET /secrets.json` y recibió 404. Los indicadores fuertes no se degradan y la ventana empieza en el despliegue, así que el humano
  no podía clasificarla; hubo que cerrar la tarea a mano. `CRM-PERFILES-1-RBAC` se desplegó asumiendo ese riesgo y pasó solo por una ventana corta.
- Cambio (mantenimiento acotado, sesión abierta y cerrada por el humano): en `harness/policies.yaml`, `observability.log_indicators.strong`, los
  patrones `password`, `cookie`, `secret` y `token` pasan a `"<palabra> -bytes_read"`. `bytes_read` es un campo que Caddy escribe en todas sus líneas de
  acceso y que no aparece en ninguna otra: medido en los logs reales de DEV hubo 1.641 líneas de acceso y 1.641 con `bytes_read`, 0 fuera del acceso,
  y las 300 líneas `INFO` de la app no cambian con la exclusión. `Authorization -REDACTED`, `Bearer`, `raw_payload` y los débiles no cambian.
- Seguridad de la corrección: un patrón antiguo sin exclusión (`secret`) ya no está declarado, y `log_scan.py` trata lo no declarado como fuerte, así que
  falla cerrado. Pruebas nuevas lo fijan, junto con la lista exacta de patrones fuertes y débiles del `policies.yaml` real.
- Riesgo aceptado: un valor sensible puesto en la URL de una petición ya no lo detecta este escaneo. Hoy la app no lo hace (los parámetros de URL son
  filtros del listado) y Caddy ya redacta `Authorization` y `Cookie` en esas líneas.
- Proceso: el humano abrió el alcance (`maintenance-scope open`), lanzó `claude -p` con solo `Read,Glob,Grep,Write,Edit,Bash` y el guard no negó ninguna de
  las 14 llamadas de la sesión; `check_scope_tools.py` dio `CHECK: PASS` ligado a esa sesión y el humano cerró el alcance. El orquestador revisó el diff,
  corrió `validate_repo.py` (PASS) y 242 pruebas, y copió los tres archivos a un worktree normal para el PR (la sesión no puede commitear: cambiar el HEAD
  invalida el alcance).
- Observaciones: `runtime/claude/E2E-PROCEDURE.md`, citado por el README de mantención, no existe en el repositorio; el paso de comprobación de herramientas
  se resolvió ejecutando el trabajo con `claude -p --output-format stream-json` y comprobándolo después con `check_scope_tools.py --guard-log --scope-id`. El
  docstring de `scripts/harness/log_scan.py` aún lista los términos fuertes sin exclusión (es descriptivo, fuera del alcance de esta sesión).
- Siguiente paso: retirar `HARNESS-LOGS-FALSOS-POSITIVOS-CADDY` del backlog (hecho en este PR) y, en una próxima mantención, corregir el docstring y el README
  de mantención.

### 2026-10-26 - Harness: tarea CRM-PERFILES-1-RBAC cerrada (DONE); perfiles Runner, Coordinador y Socio en DEV

- Titulo: CRM: tres perfiles de usuario (Runner, Coordinador y Socio) con permisos por perfil
- Evidencia: `evidence/CRM-PERFILES-1-RBAC/` y `tasks/completed/CRM-PERFILES-1-RBAC.yaml`.
- release_sha: `ba537775a62d500907f44c5f52b27df400f3030f` (PR 132)
- application_version: `h3-crm-perfiles-1-rbac-ba53777-domainlocked-r1`
- bundle_sha256: `b9f1a423f4a897efe6b79c3ee5eb7d1b0ee2ae3108d89b22ff948e9b6bc21f8a`
- lkg: `h3-crm-estados-1-catalogo-bfa4ede-domainlocked-r1`
- deployment: `success` (un solo `update-environment` version-only, 2026-10-26 14:17Z, sin rollback)
- verification: `PASS`; el humano aceptó AC-8 el 2026-10-26 (14:39Z), 22 minutos después del cutover.

**Resultado.** DEV corre el rol nuevo `coordinator`, las etiquetas Runner (`advisor`), Coordinador y Socio (`ceo`/`cto`), una única función de alcance de
cartera (`has_portfolio_scope`), la asignación solo para los socios y los estados permitidos por perfil. Una ronda de rework: el Reviewer rechazó la primera
entrega por falta de respaldo (cuatro hallazgos mayores: entrada de BITACORA, matriz de pruebas del `POST` del simulador y del PDF, escrituras cruzadas
entre carteras y adjuntos del coordinador) y aprobó la segunda; no encontró ningún hueco de permisos en el código.

**Prueba humana (AC-8).** Con los usuarios Runner (`asesor.desarrollo1/2`), Socio (`diego.operaciones` y `alvaro.operaciones`) y dos Coordinadores de prueba
(`coordinador.ejemplo1` y `coordinador.ejemplo2`, cada uno con su propio asesor en `tpi.asesores` para aislar las carteras). Las cuentas de prueba son
sintéticas y su clave es igual al usuario: **hay que desmontarlas** del secreto cuando ya no se necesiten (`scripts/dev_usuarios.py quitar`).

**La falsa alarma de logs no se repitió.** Se aceptó la regla tal cual (`HARNESS-LOGS-FALSOS-POSITIVOS-CADDY` sigue en el backlog) apostando a una ventana
corta entre el despliegue y la aceptación; fueron 22 minutos y la verificación dio cero coincidencias en los ocho patrones.

**Orden seguro para dar de alta usuarios `coordinator`.** La versión anterior de la app no conoce el rol y no arranca si lo ve en `AUTH_USERS_JSON`
(`Unknown auth role`), y un rollback con el usuario ya cargado tampoco levantaría. Por eso: primero el asesor del coordinador (sin riesgo), después del
despliegue y de `Ready/Green/Ok` se agrega el usuario al secreto `tpi/dev/auth-users` y se hace `RestartAppServer`. Lo automatiza `scripts/dev_usuarios.py`
(`listar`, `asesores`, `agregar`, `quitar`): conserva a los usuarios existentes, valida con el mismo parser de la app, no imprime hashes y deja la versión
anterior del secreto como `AWSPREVIOUS`.

**Lecciones de operación** (ninguna cambió código del Harness):

1. *Una tarea de permisos exige la matriz completa de pruebas* (lectura y escritura, `GET` y `POST`, entre carteras, adjuntos y borrado por la ruta real),
   no solo la lectura del detalle; y la entrada de BITACORA va en el PR, no la genera el cierre.
2. *Los topes del Developer subieron a 600 llamadas y 1500 pasos* (`harness-deepagents/models.yaml`): el turno inicial entregó en unos 30 minutos
   sin cortarse (el de CRM-ESTADOS-1 se había cortado en 300).
3. *La API de Claude se detuvo dos veces en una misma tarea:* primero el límite de gasto mensual («You have reached your specified API usage limits») y luego
   el saldo prepagado («Credit balance is too low»). Un turno de Reviewer cuesta ~1 USD y los del Deployer entre 0,3 y 1,6 USD.
4. *La sesión de `aws login` caducó dos veces durante la tarea* (2026-10-26 02:01Z y ~14:25Z) y la renovación hecha a las 14:08Z no evitó el segundo vencimiento:
   se verifica con `aws sts get-caller-identity` antes de lanzar el Deployer; un `identidad AWS no verificada` es un `DENIED` que detiene al Supervisor.
5. *El Deployer vuelve a terminar su turno tras `update-environment` si espera con un `sleep` suelto* (pasó otra vez): el cutover queda hecho y sin registrar.
   La nota en `progress/current.md` (no repetir el cutover, solo verificar y registrar) lo resuelve; mejora pendiente: instruirlo en su CONTEXT.
6. *El orquestador no despierta tras decisiones humanas tomadas en otra terminal* y, al cambiar el estado por debajo, un aviso viejo puede quedar en pantalla:
   se responde con el estado actual y Enter sin ejecutar el comando que imprime.

**Siguiente paso:** desmontar las cuentas de prueba; resolver `HARNESS-LOGS-FALSOS-POSITIVOS-CADDY` (paquete listo, requiere una sesión de mantenimiento
tuya); y elegir la próxima tarea de producción (`CRM-NO-CONTACTAR-1`, que necesita criterio legal antes del 2026-12-01, y `CRM-AGENDAMIENTO`).

### 2026-10-26 - CRM-PERFILES-1-RBAC: perfiles Runner, Coordinador y Socio (desarrollo)

- Contexto: el protocolo de Runners (reunion de equipo, octubre 2026) y las decisiones del humano del 2026-10-22 definen tres perfiles
  operativos: Runner (hoy el rol `advisor`), Coordinador (rol nuevo `coordinator`) y Socio (`ceo`/`cto`). Todo se resuelve en el servidor y
  falla cerrado; la interfaz solo guia.
- Cambio: se agrega `coordinator` a `UserRole` y a los roles permitidos de la autenticacion (`app/auth/models.py`, `app/auth/simple_dev.py`).
  Toda comprobacion `user.role == 'advisor'` se generaliza a una unica funcion `has_portfolio_scope` (`PORTFOLIO_ROLES = {advisor, coordinator}`);
  `resolve_advisor_identity`, `_advisor_mutation_scope`, el detalle y la bandeja la usan. `can_assign_lead` queda solo para `ceo`/`cto` (admin y
  executive pierden la asignacion). `SimuladorService.can_simulate` pasa a admitir `coordinator`. El cambio de estado respeta reglas por perfil
  (`_RUNNER_FORBIDDEN_STATUS_STATES`).
- Reglas por perfil: Runner y Coordinador ven solo su cartera (mismo alcance, `advisor_id` obligatorio y resuelto a un asesor activo; si no
  resuelve, tablero vacio). Solo los Socios asignan leads. El Coordinador puede usar el simulador sobre su cartera; el Runner recibe 403 real.
  El Runner no puede fijar `reunion_realizada`, `ficha_generada` ni `cerrado` (los fija el Coordinador o un Socio); Coordinador y Socio pueden
  fijar todos los estados excepto `asignado` (solo por asignacion). Dashboard ejecutivo, exportacion XLSX y borrado de adjuntos siguen siendo
  de `ceo`/`cto`; el enmascarado de PII no cambia (los datos de la propia cartera siguen sin enmascarar para Runner y Coordinador).
- Pruebas: `tests/unit/test_crm_perfiles_rbac.py` amplia la matriz rol x accion (ver cartera, ver datos completos, asignar, cambiar estado,
  simular y descargar PDF por perfil, exportar, dashboard, adjuntos) con el 403/404 esperado, incluyendo escrituras cruzadas (Runner A vs Runner B
  y Coordinador) y adjuntos (subir con auditoria, ver, descargar y rechazo de borrado). Se actualizan las pruebas de asignacion sin debilitarse
  (admin/executive pasan a denegados explicitos) y se agregan pruebas de `simple_dev` para `coordinator` (advisor_id valido, ausente y malformado).
  Cobertura >= 85% verificada por el CI del PR.
- Documentacion: `docs/SEGURIDAD.md` con la matriz de permisos por perfil y la configuracion de usuarios (valor `coordinator`, ejemplo ficticio
  sin secretos ni claves).
- Sin migracion ni cambio de esquema (clase A); no se toca `deployment/**`, IAM, bucket ni GuardDuty.
- Nota de despliegue: el humano agrega los usuarios de prueba con rol `coordinator` (y su `advisor_id`) al secreto de usuarios del ambiente
  DESPUES del despliegue, nunca antes: un rol `coordinator` en la configuracion con la version actual romperia el arranque. El smoke por perfil
  es el criterio humano AC-8.

### 2026-10-25 - Harness: tarea CRM-ESTADOS-1-CATALOGO cerrada a mano (el Harness la registra como CANCELLED); desplegada y aceptada, bloqueada por una falsa alarma del escaneo de logs

- Titulo: CRM: nuevo catalogo de 12 estados del lead segun el protocolo de runners
- Evidencia: `evidence/CRM-ESTADOS-1-CATALOGO/` y `tasks/completed/CRM-ESTADOS-1-CATALOGO.yaml`.
- release_sha: `bfa4edee00abb786d83b42ccaa01614a9985080d` (PR 129)
- application_version: `h3-crm-estados-1-catalogo-bfa4ede-domainlocked-r1`
- bundle_sha256: `2c4c5905c70d5784ecf7879a1715afd9f235ea327afa7beb2b5826ce3837ae8a`
- lkg: `h3-crm-ui-1-armonia-visual-db51f95-domainlocked-r1`
- deployment: `success` (un solo `update-environment` version-only, 2026-10-23 20:05Z, sin rollback)
- verification: `FAIL` por una falsa alarma ya clasificada (ver abajo); el humano aceptó AC-7 el 2026-10-24 (23:49Z).

**Resultado.** El release con los 12 estados está en DEV y los criterios AC-1 a AC-7 quedaron cumplidos o aceptados. El Harness no
pudo marcarla `DONE`: la verificación automática quedó en `FAIL` y el humano cerró la tarea con `resolve --to IDLE` (opción B), que el
Harness registra como `CANCELLED` aunque el despliegue está vigente.

**Qué bloqueó la verificación.** El conteo de logs desde el despliegue dio 1 coincidencia del indicador fuerte `secret`
(`harness/policies.yaml`, `observability.log_indicators.strong`), entre 2026-10-23 21:00Z y 22:00Z. Se inspeccionó la línea en solo lectura,
con los valores largos enmascarados: es un registro de acceso de Caddy de un robot de internet (IP `34.52.229.253`) que pidió
`GET /secrets.json` y recibió **404 con tamaño 0**. El mismo origen hizo unas 117 peticiones de barrido (`/.env`, `/.docker/config.json`,
`/.claude/settings.json`...), todas 404. La palabra está en la dirección pedida, no en un valor filtrado: falsa alarma, sin exposición.

**Por qué no se resolvió dentro del Harness.** Los indicadores fuertes bloquean `verified` y nunca se degradan; la ventana de conteo empieza
en el inicio del despliegue, así que `resolve --to VERIFYING` habría vuelto a contar la misma línea. Además se repetirá en cada despliegue:
cualquier robot que pida `/secrets.json` o `/token` activa la regla (las verificaciones anteriores pasaron porque no hubo tal tráfico).

**Decisión del humano.** Opción B: cerrar a mano ahora y tratar la regla como tarea aparte (`HARNESS-LOGS-FALSOS-POSITIVOS-CADDY`, P1, en
el backlog). La opción A (excluir de los patrones fuertes las líneas de acceso de Caddy) se descartó por ahora por sus contras: se pierde
la detección de un valor sensible puesto en la URL (hoy la app no lo hace y Caddy ya oculta `Authorization` y `Cookie`), debilita una regla
pensada como rígida, el patrón de exclusión de CloudWatch hay que validarlo contra los logs reales y no cubre otros usos legítimos de esas
palabras en los logs de la app. Cambia `harness/policies.yaml`, archivo protegido: exige una sesión de mantenimiento lanzada por el humano.

**Lecciones de la operación de la tarea** (ninguna cambió código del Harness):

1. *El Developer (runtime `other`) necesita el Python del entorno virtual de `harness-deepagents`.* Con `python` suelto sale con código 1 en
   0,3 segundos (`ModuleNotFoundError`); Reviewer y Deployer (Claude) no lo notan. Siempre dar la ruta completa del intérprete.
2. *El tope de 300 llamadas de herramienta por turno* (`harness-deepagents/models.yaml`) cortó un turno del Developer justo antes del commit;
   la nota para el siguiente turno (no rehacer, pocas llamadas, gates una vez) lo resolvió.
3. *Un script de Python no puede escribir rutas protegidas del Harness:* el Reviewer quiso corregir su payload con `python -c` y el guard lo
   negó; el payload se reescribe completo con la herramienta Write.
4. *Sin `ANTHROPIC_API_KEY` en la terminal del orquestador, `claude -p` cae al inicio de sesión del plan* y falla con «OAuth session
   expired and could not be refreshed» en menos de 5 segundos. La clave se pone en esa terminal antes de lanzar el orquestador.
5. *Las decisiones humanas tomadas en otra terminal (`resolve`, `gate`, `accept`) no despiertan al orquestador:* hay que responder su aviso
   en su propia ventana. Y un Deployer que espera en segundo plano termina su turno y el supervisor se detiene.
6. *La base de DEV tiene tablas del pipeline de datos* (`campanas_atribucion`, `eventos_lead`, `citas`, `fichas_diagnosticas`,
   `ingesta_google_sheets`) que este repositorio no conocía; quedaron documentadas en `docs/database/` (PR 130) junto con la herramienta
   `scripts/dev_reset_leads.py`, que reinicia los datos de DEV y siembra 100 leads completos.

**Siguiente paso:** definir y ejecutar `HARNESS-LOGS-FALSOS-POSITIVOS-CADDY` antes de desplegar nada más; después activar
`CRM-PERFILES-1-RBAC` (Runner, Coordinador, Socio).

### 2026-10-24 - Base de datos: inventario de DEV, relaciones del pipeline documentadas y herramienta de reinicio de datos

- Contexto: para el criterio AC-7 de `CRM-ESTADOS-1-CATALOGO` el humano debía reiniciar los datos de DEV. El script de reinicio se negó a
  correr por tablas que la documentación del backoffice no conocía (`campanas_atribucion`, `citas`, `eventos_lead`, `fichas_diagnosticas`,
  `ingesta_google_sheets`): las crea el proyecto hermano `tpi-data-pipeline`, no este repositorio.
- Qué se hizo: se documentó el esquema real de esas cinco tablas (DDL del pipeline, con las claves foráneas verificadas en DEV con
  `--inspeccionar`), un mapa de relaciones con las reglas de borrado (todas `NO ACTION`, salvo `api_idempotency.lead_id` que es `SET NULL`) y el
  orden para insertar y borrar. Nuevo `docs/database/08_DEV_DATA_INVENTORY.md` con la procedencia de los datos, el inventario del 2026-10-24
  (85 leads, 83 personas, 82 consentimientos, 34 asignaciones, 146 eventos de auditoría, 69 filas en atribución, eventos e ingesta, 7 adjuntos),
  la ubicación de los adjuntos en S3, consultas útiles y el procedimiento de reinicio. El script quedó en `scripts/dev_reset_leads.py` con
  pruebas (`tests/unit/test_dev_reset_leads.py`). La siembra se rehízo tras la primera revisión del humano: la versión
  inicial (42 leads) dejaba sin llenar el género, el estado civil y la AFP de los catálogos (que son los que lee la app) y usaba nombres sin
  relación con el sexo; ahora siembra 100 leads completos (50 hombres de 62 a 68 años y 50 mujeres de 57 a 63, edad de jubilación en Chile) con todos
  los campos que deja la ingesta real.
- Verificación: el script se ensayó contra una base PostgreSQL local con el mismo esquema (siembra, reinicio repetido, filas dependientes en
  las cinco tablas, tabla desconocida directa e indirecta, rechazos por usuario, host y base); el borrado en S3 se probó con `aws` simulado y
  la lectura de S3 contra el bucket real en modo solo lectura.
- Lecciones: (a) la base de DEV tiene tablas de otro proyecto; antes de borrar datos hay que inspeccionar las dependencias, no suponerlas;
  el script ahora lo hace solo y se detiene ante cualquier dependiente desconocido, incluso indirecto. (b) `Path.as_uri()` no sirve para el
  argumento `file://` del AWS CLI en Windows. (c) El túnel SSM a DEV debe estar abierto en su propia terminal; sin él la conexión muestra
  `connection timeout expired`.
- Pendiente: el humano ejecuta el primer reinicio de DEV y se actualiza la sección «Estado» de `08_DEV_DATA_INVENTORY.md`. Los privilegios de
  `tpi_app` sobre las cinco tablas del pipeline no están verificados. Una inspección completa del catálogo de DEV (columnas, índices,
  vistas 007-009 y privilegios) sigue sin hacerse.

### 2026-10-23 - CRM-ESTADOS-1-CATALOGO: catalogo de 12 estados del lead segun el protocolo de Runners (desarrollo)

- Contexto: se reemplaza el vocabulario de `estado_lead` por el protocolo de trabajo de los Runners (octubre 2026). Es solo el catalogo: los datos
  estructurados (intento, reunion, no contactar) y la automatizacion de los 14 dias son tareas posteriores.
- Cambio: `app/models/crm_states.py` expone los 12 estados (nuevo, asignado, sin_contacto, en_seguimiento, reunion_agendada, reunion_realizada,
  ficha_generada, cerrado, no_interesado, datos_erroneos, no_contactado, perdido) con etiquetas con tilde (Reunion, Datos erroneos) y tonos; el alias
  `pendiente` sigue mapeando a `nuevo`. Los estados anteriores (prospecto, contactado, citado, en_tramite, expediente, no_califica, duplicado, dormido)
  dejan de existir en el contrato; un valor desconocido guardado en la base se muestra tal cual, sin error.
- Reglas: `asignado` sigue exclusivo de `assign_lead` (servicio y repositorio lo rechazan en el cambio generico y el selector no lo ofrece).
  `CARTERA_INACTIVA_ESTADOS` pasa a (cerrado, perdido, no_interesado, datos_erroneos, no_contactado); `ficha_generada` sigue activo hasta cerrarse.
  El texto del dashboard que explica la cartera activa nombra esos estados. Sin migracion: el estado es texto sin restriccion en la base.
- Interfaz: filtros, chips y barra de estado usan el contrato nuevo; el CSS elimina las reglas de chip de los estados retirados (los tonos de los
  nuevos ya venian de CRM-UI-1). La exportacion XLSX muestra las etiquetas nuevas. Sin transiciones restringidas salvo `asignado`.
- Pruebas: se actualizan las suites que mencionaban los estados anteriores (contrato, web, dashboard, exportacion, historial, asignacion, integracion)
  preservando lo que protegen, y se agregan pruebas del contrato nuevo (12 estados, etiquetas, tonos, alias), de los estados inactivos y del valor
  desconocido.
- Documentacion: `docs/database/03_BUSINESS_RULES.md` y `docs/H3_3_CRM_LITE_WEB_UX.md`.
- Sin migracion ni mapeo de estados viejos a nuevos: los leads de DEV son sinteticos y el humano los reinicia tras el despliegue (AC-7).

### 2026-10-23 - Harness: tarea CRM-UI-1-ARMONIA-VISUAL cerrada (DONE); el publish exigió corregir el runner (PR 127) y tres relanzamientos del orquestador

- Titulo: CRM: armonia visual aprobada (tokens y componentes, iconos, tipografia alojada, edad en el listado y textos retirados)
- Evidencia: `evidence/CRM-UI-1-ARMONIA-VISUAL/` y `tasks/completed/CRM-UI-1-ARMONIA-VISUAL.yaml`.
- release_sha: `db51f95e2e2db85922e4cb9bb7c1e6c6c9144c28` (PR 126); el workflow de publish se corrigió aparte en el PR 127 (`a415233`)
- application_version: `h3-crm-ui-1-armonia-visual-db51f95-domainlocked-r1`
- bundle_sha256: `6b9b08ea16af3c1a386777fea6d9e6fa4b4207216a712c158167f2634118e6c3`
- lkg: `h3-crm-adjuntos-3-ajustes-fd5778a-domainlocked-r1`
- deployment: `success` (cutover version-only, uno solo, 2026-10-23 15:37Z)
- verification: `PASS`; el humano aceptó AC-8 el 2026-10-23 («smoke visual OK en DEV»).

**Cronología.** El Developer (DeepSeek) dejó todo el trabajo hecho en el primer turno y quedó bloqueado solo en `git commit` por forma (una variable
de shell ocultaba la ruta del worktree al guard); con la nota de ruta literal entregó el PR 126 (3 commits, CI verde, archivos idénticos a la referencia
`docs/ui/referencia/ui1/`), el Reviewer lo aprobó y el Deployer lo mergeó como `db51f95`. El publish a ECR falló dos veces en el gate de escaneo
(runs 39953213366 y 39961897074) por la causa que recoge la entrada anterior (runner `ubuntu-26.04` sube un índice OCI que ECR no escanea); el
PR 127 fijó `ubuntu-24.04` y el run 39974187904 pasó 6 de 6 con escaneo COMPLETE y 0 HIGH/CRITICAL. Después: candidato aprobado por el Reviewer, gate
humano, despliegue, verificación técnica PASS (identidad de runtime 4/4, smoke HTTP 8/8, logs sin errores) y aceptación humana.

**Lecciones del Harness y de la operación** (ninguna cambió código del Harness):

1. *Un Deployer que espera con una tarea en segundo plano o con un `sleep` suelto termina su turno* y el supervisor se detiene con «worker exited
   without workflow progress». Pasó dos veces: tras despachar el publish y tras ejecutar el `update-environment` (el cutover ya estaba hecho y el
   registro faltaba). Se resolvió con notas en `progress/current.md` (no repetir el cutover, esperar con bucles de sondeo en primer plano) y
   relanzando el orquestador. Mejora pendiente: instruirlo en el CONTEXT del Deployer y que el supervisor distinga «esperando un workflow externo».
2. *Una decisión humana tomada en otra terminal (`resolve`, `gate`) no despierta al orquestador*: sigue en su aviso hasta que el humano lo responde
   en su propia ventana. Ocurrió tres veces y parecía una detención del Harness.
3. *Un escaneo de ECR que «no termina» puede ser permanente*: antes de borrar y relanzar hay que mirar `imageManifestMediaType` y probar
   `start-image-scan` (ver entrada anterior y el runbook).
4. *Observación abierta*: en DEV la fuente `PlusJakartaSans-latin.woff2` llega como `application/octet-stream` (Alpine, y Python no conoce `.woff2`); no impide
   la carga y el humano aceptó el smoke. La prueba de AC-2 exige `font/woff2` y depende del host de CI; tarea chica si llegara a molestar.
5. *Disco*: C: bajó a 6,1 GB libres durante la tarea (el orquestador se detiene bajo 5 GB); antes se purgó la caché de pip (3,3 GB).

**Siguiente paso:** activar `CRM-ESTADOS-1-CATALOGO` (12 estados) y después `CRM-PERFILES-1-RBAC` (Runner, Coordinador, Socio); tras desplegar los estados,
resetear los leads sintéticos de DEV con un script que corre el humano.

### 2026-10-23 - Release: el publish a ECR falló dos veces porque el runner nuevo sube un índice OCI que ECR no escanea (CRM-UI-1-ARMONIA-VISUAL)

- Contexto: el release `db51f95` (PR #126, armonía visual) pasó todos los gates del workflow de publicación, pero el escaneo de ECR nunca se inició: `ScanNotFoundException` en ambas imágenes y el gate venció a los 20 minutos (runs 39953213366 y 39961897074). Se borraron las dos imágenes y se relanzó con el mismo SHA según el runbook; falló igual y el Deployer se detuvo en `BLOCKED_HUMAN` (mismo error de infraestructura dos veces).
- Diagnóstico: `aws ecr start-image-scan` respondió `UnsupportedImageTypeException` («application/vnd.oci.image.index.v1+json cannot be scanned»). El publish del 2026-10-22 (`fd5778a`, escaneo COMPLETE en 2 minutos) corrió en `ubuntu-24.04` y subió un manifiesto Docker v2; el del 2026-10-23 corrió en `ubuntu-26.04` (al que pasó `ubuntu-latest`) y subió un índice OCI con una imagen de atestación. La diferencia observada entre ambos es el runner; la versión de Docker no se comprobó. No es un problema del código del CRM ni de la configuración del registro (escaneo BASIC, `scanOnPush` activo).
- Cambio: `publish-dev-ecr-images.yml` fija todos sus jobs en `ubuntu-24.04`; dos pruebas nuevas en `tests/security/test_ecr_scan_wait_workflow.py` (runner fijado y causa documentada); sección nueva en `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md` con síntoma, causa y comprobación del `imageManifestMediaType`; entrada en el CHANGELOG.
- Lecciones: (a) el gate fallaba cerrado como debe, pero «no terminó en el plazo» ocultaba una causa permanente; `start-image-scan` la distingue en un segundo, antes de borrar y relanzar. (b) Un runner flotante (`ubuntu-latest`) cambió el formato de lo publicado sin tocar el repo: los pasos de release van con la imagen del runner fijada. (c) El workflow se toma de `main`, así que corregirlo allí vale para el release ya mergeado.
- Pendiente: confirmar con el próximo publish que el tipo de manifiesto vuelve a ser Docker v2 (si siguiera siendo un índice, agregar `--provenance=false --sbom=false` a los `docker build`).
- Siguiente paso: tras mergear este PR, el humano borra las dos imágenes `db51f95` (índices sin escaneo) y resuelve CRM-UI-1 a `PREPARING_DEPLOYMENT`; el Deployer relanza el publish con el mismo SHA.

### 2026-10-22 - CRM: producción mínima definida (interfaz, 12 estados y tres perfiles) y referencia visual aprobada

- Contexto: el humano aprobó la armonía visual tras iterar en una copia local con datos ficticios, y decidió los estados y perfiles a partir del PDF
  «Protocolo de trabajo para Runners». Decisiones: 12 estados (Nuevo = sin asignar; Asignado = solo al asignar a un ejecutivo); perfiles
  Runner (= `advisor`), Coordinador (rol nuevo, solo su cartera, puede asesorar) y Socio (= CEO/CTO); solo los socios asignan leads; los
  runners pueden subir y ver adjuntos; producción mínima primero y después el módulo de agendamiento para los tres perfiles.
- Qué se agrega: la referencia exacta de la interfaz en `docs/ui/referencia/` (CSS, plantillas, consulta de la edad y contrato de estados) y tres
  tareas activables en `tasks/backlog.yaml`: `CRM-UI-1-ARMONIA-VISUAL`, `CRM-ESTADOS-1-CATALOGO` y `CRM-PERFILES-1-RBAC` (clase A, con aceptación
  humana; en ese orden). Quedan resumidas `CRM-NO-CONTACTAR-1` (clase D, con fecha límite: la Ley 21.719 rige desde el 2026-12-01) y
  `CRM-AGENDAMIENTO` (clase D, posterior a producción).
- Cómo se usa la referencia: el Developer no reinterpreta el diseño, lo copia; el Reviewer comprueba que los archivos son idénticos a la referencia
  (ignorando fines de línea) y la verificación visual la hacen Claude (capturas con la vista previa local) y el humano (smoke en DEV).
- La tipografía Plus Jakarta Sans alojada (`woff2` del subconjunto latino, 27 KB, y su licencia SIL OFL) quedó en
  `docs/ui/referencia/ui1/fonts/`, descargada de `fonts.gstatic.com` y del repositorio público `google/fonts` con autorización del humano. El PR del
  sistema de diseño (`scripts/ui_css_audit.py` y el skill de interfaz) ya está en `main`.
- Después de desplegar los estados, el humano reinicia los datos de DEV (borrar los leads sintéticos y sembrar nuevos) con un script que entrega
  Claude; la auditoría es de solo agregar y referencia a los leads, así que lo ejecuta el humano con `tpi_admin`, como las migraciones.

### 2026-10-22 - CRM: dirección de diseño para armonizar la interfaz, auditoría del CSS y skill de interfaz para el Developer

- Pedido del humano: un CRM profesional, moderno, atractivo y minimalista; le gusta cómo se ve hoy, solo quiere armonizarlo.
- Qué se hizo: auditoría del CSS (`scripts/ui_css_audit.py`, solo lectura, con pruebas) y recorrido visual de la lista, el detalle del lead, el
  dashboard y el móvil en una copia local del CRM con datos ficticios. Línea base: 17 tokens, 80 colores sueltos distintos (156 usos),
  25 tamaños de letra, 15 radios, 13 sombras, 61 espaciados, 5 cortes responsive y 39 reglas de tema oscuro por componente; `--shadow-sm` se
  usa sin estar definido y la tipografía Inter se declara pero no se carga.
- Entrega: `docs/UI_DESIGN_SYSTEM.md` (dirección, línea base, hallazgos, tokens, componentes canónicos, plan por tareas y decisiones abiertas) y
  el skill `agents/developer/skills/tpi-ui-design/SKILL.md`, con un puntero en `agents/developer/CONTEXT.md`.
- El skill NO está registrado en `harness/policies.yaml` (archivo protegido que no se toca sin sesión de mantenimiento): las tareas de
  interfaz lo citan en sus restricciones y el CONTEXT del Developer lo señala. Registrarlo queda para la tarea de mantenimiento del Harness.
- Decisiones abiertas del humano (sección 8 del documento): tipografía (alojar Inter o pila del sistema), peso de los títulos, sombras sin
  brillo, botones en píldora, barra superior móvil y texto técnico del dashboard. Las tareas de interfaz se definen después de aprobarlas.

### 2026-10-22 - CRM: datos de uso de los adjuntos en DEV incorporados al informe previo a producción (CRM-ADJUNTOS-REVISION-PREPROD)

- Qué se hizo: el humano corrió `scripts/adjuntos_revision_preprod.py` contra DEV por el túnel (puerto 5433, usuario `tpi_admin`) y se pegó su
  salida, con la hora de los rechazos y cuatro pruebas dirigidas, en la sección «Datos de uso» de `docs/ADJUNTOS_REVISION_PREPROD.md`, con una
  lectura de cada punto. Los datos son de las pruebas de humo de dos días (2 usuarios, 2 leads), no de uso real.
- Hallazgos: (1) la auditoría de rechazos funciona con el código nuevo (`empty_file`, `too_large`) y no hay fallos de escritura en el log;
  (2) los rechazos previos a la validación (413, 411, 400 del analizador, 403) no dejan fila en `tpi.auditoria`: decisión pendiente del humano;
  (3) hay 8 eliminaciones frente a 7 subidas, por aclarar con la consulta que trae el informe; (4) el humano comprobó que la foto JPEG de celular de la
  prueba (188 KB) tiene latitud y longitud: el riesgo de EXIF/GPS (punto 3) está confirmado en la práctica, porque el servidor guarda los bytes
  sin modificar. **Decisión del humano (2026-10-22): opción A del punto 3**, las imágenes conservan sus metadatos en la primera versión;
  la limpieza de EXIF sigue agendada como segunda versión (se registra también en la decisión 8 de `docs/ADJUNTOS_COMENTARIOS_DISENO.md`).
- Script: ahora cierra el pool de conexiones al salir (desaparecen los avisos `couldn't stop thread ...`), con pruebas.

### 2026-10-22 - CRM: el script de medición de adjuntos indica el puerto del túnel a DEV (5433) y explica mejor sus fallos

- Qué pasó: al correr `scripts/adjuntos_revision_preprod.py` contra DEV el humano obtuvo un error de conexión. El túnel SSM a la base de DEV
  escucha en el puerto local **5433** (el de RDS, al otro lado, es 5432) y el informe mandaba a apuntar `DATABASE_*` a DEV sin decir el puerto,
  así que se usaba el 5432 por defecto de la aplicación.
- Cambio: el script acepta `--port` (reemplaza `DATABASE_PORT`; no aplica con `DATABASE_URL`) y, si falla la conexión, muestra el destino sin
  secretos (host, puerto, base y usuario) y, cuando el destino es `localhost:5432`, la pista de usar 5433. El informe
  `docs/ADJUNTOS_REVISION_PREPROD.md` trae ahora los pasos exactos en PowerShell (la clave se pide sin mostrarla). Pruebas nuevas.
- Segundo hallazgo al reintentar con el puerto correcto: el informe indicaba el usuario `tpi_app`, pero ese rol solo tiene `INSERT` sobre
  `tpi.auditoria` (registro de solo agregar, `scripts/sql/001_create_tpi_app_role.sql`) y no puede leerla; la autenticación falló y, aun con la
  clave correcta, la consulta habría fallado por permisos. Los pasos ahora usan `tpi_admin` (el script solo ejecuta `SELECT`, no escribe nada).
- Sin cambios en la aplicación, en las consultas ni en lo que imprime el script en el caso exitoso.

### 2026-10-22 - Harness: tarea CRM-ADJUNTOS-REVISION-PREPROD cerrada (DONE)

- Titulo: Preparar la revision previa a produccion de los adjuntos de notas: informe de decisiones, medicion de uso y pruebas de los limites conocidos
- Evidencia: `evidence/CRM-ADJUNTOS-REVISION-PREPROD/` y `tasks/completed/CRM-ADJUNTOS-REVISION-PREPROD.yaml`.
- release_sha: `7b96c67ce6429e9f865bc82c01f059659c237780` (PR 120)
- Clase A sin despliegue: tras la aprobacion del Reviewer el Deployer mergeo el PR y la tarea cerro sola (`merged_no_deploy`). El Reviewer
  aprobo sin hallazgos que corregir; dejo una observacion menor (si falla la conexion, el script imprime el detalle del error, que puede
  incluir el host o el puerto) y dos informativas (la seccion «Datos de uso» queda vacia a proposito; la opcion de quitar metadatos con
  Pillow es futura).
- Pendiente del humano, fuera del Harness: leer `docs/ADJUNTOS_REVISION_PREPROD.md`, correr `scripts/adjuntos_revision_preprod.py` contra DEV
  por el tunel, pegar la salida en «Datos de uso» (con un PR) y decidir los seis puntos; lo que decida se convierte en tareas nuevas.

**Lecciones de operacion.**

1. *El merge de una tarea del Harness lo hace el Deployer solo, justo despues de la aprobacion del Reviewer.* No hay un punto de «mergea N»
   del humano en una tarea sin despliegue: si el humano quiere leer un informe antes de que entre a `main`, hay que decirlo al definir la
   tarea (por ejemplo con un criterio humano y despliegue) o entregarlo fuera del Harness. En esta tarea el riesgo era nulo (el informe
   propone, no decide), asi que se acepto que el humano lo lea despues del merge.
2. *Un reinicio de la sesion interactiva mata el orquestador y el dashboard* (los lanzo yo en el panel Terminal). Con la tarea activada
   el Developer alcanzo a trabajar ~12 minutos antes del corte; al relanzar el orquestador la sesion nueva retomo desde el worktree
   conservado y termino sin perder trabajo.

### 2026-10-22 - CRM: informe de revisión previa a producción de los adjuntos implementado (CRM-ADJUNTOS-REVISION-PREPROD)

- Qué entrega (clase A, sin despliegue y sin cambio de comportamiento): el informe
  `docs/ADJUNTOS_REVISION_PREPROD.md`, el script de solo lectura `scripts/adjuntos_revision_preprod.py` y pruebas
  de caracterización en `tests/unit/test_attachments_known_limitations.py` y `tests/unit/test_adjuntos_revision_preprod.py`.
- Qué contiene el informe: una tabla resumen (punto, riesgo, recomendación en una línea, quién decide) y UNA sección por
  cada uno de los seis puntos aceptados el 2026-10-21 — (1) PDF con archivos incrustados, (2) visibilidad de los adjuntos
  para todo usuario con acceso al lead, (3) EXIF y GPS de las imágenes, (4) retención y borrado a solicitud del titular,
  (5) costo de GuardDuty Malware Protection for S3 y (6) validación de PDF con streams comprimidos. Cada sección trae cómo
  funciona HOY con referencias al código (`app/attachments/`, `app/services/solicitud_service.py`, `app/web/routes/leads.py`),
  el riesgo con un ejemplo, opciones con esfuerzo/costo/efecto, una recomendación marcada como propuesta y la pregunta exacta
  para el humano. No afirma tarifas ni plazos legales: el punto 5 deja la fórmula del costo con variables a confirmar y el
  punto 4 lista preguntas para el asesor legal sin dar opinión jurídica.
- Cómo ejecutar el script de medición (solo lectura, sin PII): abrir el túnel SSM a la base de DEV, activar el entorno del
  proyecto (`pip install -e .`) con las variables `DATABASE_*` de DEV y correr `python scripts/adjuntos_revision_preprod.py --days 30`.
  Muestra solo agregados de `tpi.auditoria` (conteo por acción, rechazos por código, subidas con/sin archivos incrustados, subidas
  por tipo, objetos y bytes subidos por mes, leads y usuarios distintos). La salida se pega en la sección «Datos de uso» del informe.
- Pruebas que fijan los límites sin cambiar el comportamiento: un JPEG con EXIF/GPS se acepta y sus bytes no cambian (punto 3) y
  un PDF cuyo JavaScript está dentro de un object stream comprimido con FlateDecode pasa la validación (punto 6). El caso de
  `/EmbeddedFile` ya tenía prueba equivalente en `tests/unit/test_attachments_validation.py` y se cita en el informe.
- Referencias cruzadas: `docs/ADJUNTOS_COMENTARIOS_DISENO.md` (sección 8) y `docs/SEGURIDAD.md` (sección «Adjuntos de notas»)
  enlazan el informe.

### 2026-10-22 - CRM: revisión previa a producción de los adjuntos definida como tarea activable (CRM-ADJUNTOS-REVISION-PREPROD)

- Qué es: la tarea deja de ser un resumen en el backlog y queda definida (`tasks/backlog.yaml`, clase A, sin despliegue, 6 criterios).
  No decide nada por el humano: prepara la revisión de los seis puntos aceptados el 2026-10-21 (archivos incrustados en PDF,
  visibilidad total del lead, EXIF y GPS, retención y borrado, tarifa de GuardDuty, PDF con streams comprimidos).
- Qué entrega el Developer: `docs/ADJUNTOS_REVISION_PREPROD.md` (cómo funciona hoy cada punto con referencias al código, riesgo, opciones,
  recomendación propuesta y la pregunta exacta para el humano), el script de solo lectura `scripts/adjuntos_revision_preprod.py` que mide el
  uso real en `tpi.auditoria` (solo agregados, sin PII) y pruebas que fijan los límites conocidos sin cambiar el comportamiento.
- Cómo se revisa: el humano lee el informe al mergear el PR, corre el script contra DEV por el túnel y decide cada punto; lo que decida
  se convierte en tareas nuevas. Como no hay despliegue, la tarea cierra sola tras el merge (`merged_no_deploy`).
- Por qué clase A y no un informe del Developer sobre datos reales: el Developer no tiene acceso a la base de DEV ni a AWS, así que el informe
  deja la sección «Datos de uso» para pegar la salida del script, y no se aceptan cifras, tarifas ni plazos legales sin fuente (AC-2).
- También: `HARNESS-GUARDS-REPROCESO-POST-DEPLOY` queda en ASCII como el resto del backlog.

### 2026-10-22 - Harness: tarea CRM-ADJUNTOS-3-AJUSTES cerrada (DONE); el arreglo de las notas de solo texto exigió un reproceso y dos excepciones del Harness

- Titulo: Adjuntos de notas: mensajes de rechazo claros, estados de escaneo y borrado visibles, PDF con archivos incrustados
- Evidencia: `evidence/CRM-ADJUNTOS-3-AJUSTES/` y `tasks/completed/CRM-ADJUNTOS-3-AJUSTES.yaml`.
- release_sha: `fd5778ac79b77e28e0add3c5c54646ca5bf4a08f` (PR 117, sobre el release `e37bb77` del PR 116)
- application_version: `h3-crm-adjuntos-3-ajustes-fd5778a-domainlocked-r1`
- bundle_sha256: `21a58cb28a1dca04e758f92c6b53f885d26c5d61b1ba493fb4dad555d797d725`
- lkg: `h3-crm-adjuntos-3-ajustes-e37bb77-domainlocked-r1`
- deployment: `success` (cutover version-only, ejecutado por el humano a mano; ver abajo)
- verification: `PASS`; el humano aceptó AC-8 y AC-9 el 2026-10-22.

**Cronología.** Ronda 1: release `e37bb77` desplegado y con verificación técnica PASS (`verification-01`). En el smoke humano de AC-9 en
DEV, una nota de solo texto devolvía 400 «Archivo 1 de 1: el archivo está vacío» y no se guardaba. El humano rechazó AC-9
(`verification-02`, `failure-01`, clase funcional, sin rollback: el release anterior tenía el mismo defecto) y resolvió a DEVELOPING.
Ronda 2: el PR 117 corrigió el defecto, pasó revisión y CI, y se desplegó como `fd5778a`; el smoke humano pasó (`verification-03`).

**Causa del defecto (desde CRM-ADJUNTOS-2-CODIGO).** Cuando no se elige ningún archivo, el navegador igual envía una parte multipart
`files` con `filename=""` y cuerpo vacío; Starlette la entrega como `UploadFile` de 0 bytes y `lead_comment_append` la validaba como
archivo real (`empty_file`). Las pruebas usaban dobles y nunca simularon esa parte. El arreglo ignora las partes con `filename == ""`
(un archivo con nombre y 0 bytes sigue rechazándose) y reaplica el tope de 5 archivos sobre los archivos reales; las pruebas nuevas pasan
por el parser real de multipart.

**Lecciones del Harness** (ninguna cambió código del Harness en esta tarea):

1. *Reproceso después de un merge deja dos worktrees de Developer registrados.* El Developer creó un worktree nuevo desde `origin/main`
   (correcto: main ya trae el squash del release), pero `guard._developer_worktree` toma el PRIMER worktree de Developer registrado en
   `state.json`, así que negó `git commit` y `git push` del nuevo. Se resolvió con una nota que mandó al Developer a retirar el viejo con
   `worktree.py remove --name ...`. Mejora pendiente: tomar el último registrado, o que `worktree.py create` retire el anterior.
2. *`aws_guard` cuenta los cutover y rollbacks por tarea, no por aprobación.* Una tarea que ya desplegó una vez no puede volver a desplegar
   tras un reproceso («ya hubo un intento de cutover: un release, una promoción»). El humano eligió la excepción documentada: ejecutó él
   mismo, en su terminal y UNA sola vez, el `update-environment` del plan aprobado (15:33:27Z, convergió en ~41 s). El Deployer no lo ejecutó:
   verificó el environment y los eventos, y `deployment-02.json` deja la constancia explícita (`cutover.executed_by: human`, `warnings`). El
   rollback al LKG siguió autorizado y sin usar. Mejora pendiente: contar por aprobación (`HARNESS-GUARDS-REPROCESO-POST-DEPLOY`). Para
   evitarlo hasta entonces, un arreglo posterior a un despliegue conviene como tarea nueva de clase A y no como reproceso de la misma.
3. *Las pruebas de formularios deben pasar por el parser real.* Una prueba con doble de `UploadFile` no reproduce lo que envía un
   navegador. Quedó como prueba obligatoria en las notas a los Developers.
4. *Operación:* la sesión AWS (`aws login --profile tpi-dev --remote`) venció dos veces durante la tarea y el límite de uso de Claude
   interrumpió una vez al Reviewer; en ambos casos el trabajo se conservó y bastó relanzar el orquestador.

Pendientes que quedan en el backlog: `CRM-ADJUNTOS-REVISION-PREPROD` (revisión de seguridad antes de producción),
`SIM-CANARIA-MENSUAL`, `SEG-LIMPIEZA-RESIDUOS-STREAMLIT` y `HARNESS-GUARDS-REPROCESO-POST-DEPLOY`.

### 2026-10-21 - Harness: lecciones de forma del guard en las vistas de los roles; el «Remove-Item on system path» no es del guard

- Cambio (solo documentación de los roles): `agents/developer/PROMPT.md` y `agents/developer/CONTEXT.md`, `agents/reviewer/CONTEXT.md` y
  `agents/deployer/CONTEXT.md` recogen las formas que bloquearon sesiones en `SEG-DESACOPLAR-STREAMLIT` y `CRM-ADJUNTOS-2-CODIGO`:
  - `.env.example` y los demás archivos de la raíz están fuera del alcance del Developer; la configuración se documenta solo en `docs/**`.
  - El payload de evidencia se escribe con Write en la ruta **absoluta de la raíz de control** (el directorio que contiene
    `.harness-worktrees/`) y `evidence.py` se ejecuta desde allí; dentro del worktree la regla `payloads/**` no vale y el guard lo
    deniega. El `PROMPT` del Developer decía solo `.harness-runtime/payloads/developer.json`, que dentro de un worktree se resuelve mal.
  - `progress/current.md` se edita con Edit o Write: un `python` o heredoc que calcula el destino en código que menciona rutas protegidas
    se deniega (bloqueó al Reviewer del candidato).
  - Si la evidencia de un rol ya existe porque una sesión anterior se detuvo antes de la transición, la sesión nueva la contrasta y aplica
    la transición, sin repetir toda la revisión (Reviewer).
  - Un `main` local atrasado da diferencias falsas: el template y el constructor se toman del commit del release (Reviewer y Deployer).
- Investigación del «falso positivo» reportado por el Reviewer: el mensaje «Remove-Item on system path 'C:' is blocked. This path is
  protected from removal.» **no sale del guard del Harness**. No existe en `scripts/harness`, `harness/`, `agents/` ni en `guard.log`, y
  aparece también en transcripciones de otros proyectos sin relación (con `C:\Program` como ruta). Es un control de seguridad integrado en
  la herramienta PowerShell de Claude Code, que se dispara con borrados de rutas del sistema. Además `progress/decisions.md` ya prohibía
  `rm`, `del` y `Remove-Item` en los turnos. No hay nada que corregir en el guard; se agrega la advertencia a las vistas del Developer y
  del Reviewer. Queda descartado como pendiente.

### 2026-10-21 - CRM: permiso de solo lectura de la etiqueta de escaneo para la app (CRM-ADJUNTOS-3-AJUSTES, requisito previo)

- Cambio (solo repositorio; **no se aplicó nada en AWS**): la política `tpi-backoffice-dev-adjuntos-s3` del rol de la instancia agrega un
  segundo statement con `s3:GetObjectTagging` sobre `leads/*`. Es de **solo lectura**: la app puede leer el resultado del escaneo de
  GuardDuty para mostrar «Escaneando» o «Bloqueado», pero no puede escribir ni borrar etiquetas, y la política del bucket sigue
  impidiéndolo a cualquiera que no sea GuardDuty.
- Pruebas: la prueba de seguridad del rol de la app ahora exige exactamente dos statements, que la única acción de etiquetas sea
  `s3:GetObjectTagging`, y que no haya `ListBucket` ni acciones sobre el bucket; `verify` del script comprueba además con el simulador de
  IAM que `GetObjectTagging` está permitido y que `PutObjectTagging` y `DeleteObjectTagging` siguen denegados.
- Aplicación: `python deployment/aws/adjuntos_s3_infra.py plan` mostrará la política de la app como `DIFIERE`; `apply` con la frase de
  confirmación la actualiza (el resto queda igual) y `verify` la comprueba. Debe aplicarse antes de desplegar `CRM-ADJUNTOS-3-AJUSTES`,
  aunque el código de esa tarea degrada bien si el permiso todavía falta.

### 2026-10-21 - CRM: ajustes de los adjuntos definidos; se permiten PDF con archivos incrustados (CRM-ADJUNTOS-3-AJUSTES)

- Decisión del humano (opción B): los PDF con archivos incrustados **se permiten**. Los 4 rechazos de DEV fueron `unsafe_pdf` y el PDF que
  el humano diagnosticó con una herramienta local trae un archivo incrustado real; la regla lo rechazaba como estaba diseñada, pero el
  usuario no sabía por qué. Riesgo evaluado: un archivo incrustado solo hace daño si alguien lo abre a mano desde un lector de escritorio,
  GuardDuty no garantiza revisarlo como archivo independiente (el bucket falla cerrado) y la regla de `/EmbeddedFile` es la más fiable
  porque va en el diccionario del stream, que no se comprime.
- Condiciones: se siguen rechazando JavaScript, `/Launch` y los PDF cifrados; el dato `archivos_incrustados` queda en la auditoría; la
  nota muestra la etiqueta «Contiene archivos incrustados: ábrelo en el navegador»; el ajuste `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES`
  permite volver al rechazo; la decisión se revisa antes de producción (nuevo item `CRM-ADJUNTOS-REVISION-PREPROD`).
- Tarea definida y activable (`CRM-ADJUNTOS-3-AJUSTES`, **clase A**, riesgo medio, aceptación humana): 9 criterios. Mensajes de rechazo por
  causa con la posición del archivo y sin nombres, y el código `unsafe_pdf` dividido por causa; reglas de PDF que respetan dónde termina el
  nombre (sin debilitarlas); PDF con archivos incrustados con sus condiciones; borrado registrado dentro de la nota con una marca de
  eliminado para que se muestre «Archivo eliminado» sin enlaces; estados «Escaneando» y «Bloqueado» leyendo la etiqueta de GuardDuty en los
  adjuntos de los últimos 30 minutos; página amable para un adjunto no disponible; regresión, documentación y smoke humano.
- Es clase A porque no toca `deployment/**`: el ajuste vale por defecto en el código. El permiso de solo lectura `s3:GetObjectTagging` lo
  agrega el humano con un PR aparte y el script de infraestructura **antes** del despliegue; el código debe funcionar si todavía falta.
- Pendiente: PR del permiso `s3:GetObjectTagging` y su aplicación; activar la tarea.


### 2026-10-21 - CRM: adjuntos de notas desplegados y aceptados con observaciones (CRM-ADJUNTOS-2-CODIGO)

- Resultado: el humano aceptó AC-11 (documentación) y AC-12 (smoke humano en DEV) **con observaciones**, que recoge la tarea
  `CRM-ADJUNTOS-3-AJUSTES`. Funciona el flujo central: subida junto con la nota, vista en línea de imágenes, PDF en pestaña nueva,
  descarga, control de acceso por lead, escaneo de GuardDuty, auditoría y borrado por `ceo` o `cto`.
- Cambio (PR #111, `03436de`; clase C porque agrega dos variables literales al compose del backoffice): paquete `app/attachments/`
  (validación por contenido, almacenamiento en S3 con cliente inyectable, marcas en la nota y auditoría), rutas de vista, descarga y
  borrado, plantilla y estilos, y pruebas (unitarias y de seguridad con S3 simulado). Sin tabla nueva ni migración.
- Rondas: 1 rechazo del Reviewer. El hallazgo mayor fue que la subida sin `Content-Length` (petición `chunked`) esquivaba los topes de
  10 MiB y 25 MiB: el parser de Starlette 1.3.1 solo limita con `max_part_size` los campos de texto y no las partes de archivo. El criterio
  de aceptación lo pedía así por un error de la especificación, no del Developer. Se corrigió rechazando con 411 la petición sin
  `Content-Length` válido cuando los adjuntos están activos, con su prueba.
- Release: publish a ECR en el primer intento (run 39676430248, escaneo `COMPLETE` sin hallazgos), despliegue con un único
  `update-environment` de unos 42 s, sin rollback, y verificación automática PASS (smoke HTTP y 0 coincidencias en los logs).
- Observaciones del smoke del humano: (1) un PDF liviano se rechaza con el mensaje genérico «Uno de los archivos no es válido»; los 4
  rechazos de DEV fueron `unsafe_pdf` y el PDF diagnosticado trae un archivo incrustado real (`/EmbeddedFile`), por lo que la regla lo
  rechaza como está diseñada pero el usuario no sabe por qué; (2) una imagen recién subida muestra «adjunto eliminado» mientras
  GuardDuty la escanea; (3) un PDF eliminado sigue mostrando «Ver PDF» y «Descargar» y abre una pestaña con 404. Las observaciones 2 y 3
  corresponden al hallazgo F-3 que el Reviewer dejó como opcional; no se registraba el borrado dentro de la nota, algo que la
  especificación tampoco pedía.
- Incidentes con el guard (tres bloqueos de forma, sin pérdida de trabajo): el Developer intentó editar `.env.example`, fuera de su
  alcance; el Developer escribió el payload de evidencia dentro de su worktree y no en la raíz de control, donde la regla lo permite; el
  Reviewer del candidato intentó anotar su decisión con un script de Python que calculaba la ruta, que el guard tomó por una escritura a
  archivos protegidos (la evidencia `APPROVED` ya estaba escrita; una sesión nueva aplicó la transición). Además el Reviewer de la ronda 0
  reportó una denegación (`Remove-Item on system path 'C:'`) en un comando que no contenía esa operación, que parece un falso positivo del
  guard con PowerShell y queda pendiente de investigar.
- Cosas a recordar: la nota del humano en `progress/current.md` hizo que el Reviewer confirmara y subiera a mayor un hallazgo que ya
  había visto como menor (`review-01.json`, una aprobación descartada en su misma sesión, y `review-02.json`, el rechazo); el
  `main` local atrasado hizo que el Deployer descartara un primer bundle sin las variables de adjuntos antes de subir nada, así que
  conviene sincronizarlo tras cada merge; el disco `C:\` quedó con unos 9 GB libres.
- Lecciones:
  - Un criterio que depende del comportamiento de una biblioteca se verifica contra la versión instalada antes de escribirlo.
  - Los avisos de forma del guard se repiten de una sesión a otra; las reglas sobre rutas permitidas (`.env.example`, el payload en la
    raíz de control, no usar Python para escribir `progress/current.md`) pasan a las vistas de los roles.
  - Lo que S3 devuelve sin `ListBucket` (403 para inexistente, no escaneado e infectado) no alcanza para mostrar estados distintos; hace
    falta una marca de eliminado en la nota y leer la etiqueta de escaneo.
- Pendiente: `CRM-ADJUNTOS-3-AJUSTES` (clase A, solo resumen hasta decidir qué hacer con los PDF con archivos incrustados); llevar las
  lecciones de forma del guard a `agents/developer/CONTEXT.md` y a la vista del Reviewer; investigar el falso positivo de PowerShell.

### 2026-10-21 - Harness: tarea CRM-ADJUNTOS-2-CODIGO cerrada (DONE)

- Titulo: Adjuntos de notas, paso 2: subida, vista en linea, descarga y borrado
- Evidencia: `evidence/CRM-ADJUNTOS-2-CODIGO/` y `tasks/completed/CRM-ADJUNTOS-2-CODIGO.yaml`.
- release_sha: `03436de2e1a66c6c5950633111075521c4122b5f`
- pr_number: `111`
- application_version: `h3-crm-adjuntos-2-codigo-03436de-domainlocked-r1`
- bundle_sha256: `c24f2e7e8530a61b3bbf7504c7c8c9574d387845fe6b78e274eec755148d2bde`
- lkg: `h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1`
- deployment: `success`
- deployed_commit: `03436de2e1a66c6c5950633111075521c4122b5f`
- verification: `PASS`

### 2026-10-21 - CRM: infraestructura de los adjuntos aplicada y verificada; paso 2 definido (CRM-ADJUNTOS-COMENTARIOS)

- Resultado del paso 1 (`CRM-ADJUNTOS-1-INFRA-S3`, PR #109): el humano ejecutó `apply` y `verify` con `deployment/aws/adjuntos_s3_infra.py`
  sobre AWS DEV. `apply` terminó con las 12 comprobaciones en `OK` y `verify` con las 7 en `PASA`: un objeto sin escanear no se puede
  leer; el archivo limpio queda `NO_THREATS_FOUND` y entonces se lee; el archivo de prueba EICAR queda `THREATS_FOUND` y no se puede leer; no
  se puede falsificar la etiqueta de escaneo; el permiso de la app cubre `leads/*` y nada más.
- Hallazgos: GuardDuty Malware Protection for S3 creó el plan **sin necesitar un detector de GuardDuty activo** (plan
  `12d0afd1193ea2e81987` en `ACTIVE`); no hubo que corregir ninguna acción del rol de GuardDuty; el escaneo de un objeto tardó segundos. La
  tarifa por objeto de GuardDuty en `us-east-2` sigue sin confirmar.
- Recursos creados: bucket `tpi-dev-adjuntos-821656895812-us-east-2`, rol `tpi-dev-guardduty-malware-s3-role`, política en línea
  `tpi-backoffice-dev-adjuntos-s3` en `tpi-backoffice-dev-ec2-role` y el plan de GuardDuty. Retroceso: `rollback` del mismo script.
- Paso 2 definido y activable (`CRM-ADJUNTOS-2-CODIGO`, clase C con despliegue, riesgo alto, aceptación humana): 12 criterios (configuración
  fail-closed, validación por contenido, almacenamiento en S3 con cliente inyectable, subida con permiso comprobado antes de subir nada,
  marcas en la nota, vista en línea y descarga con cabeceras de seguridad, auditoría y borrado, configuración literal en el compose de DEV,
  pruebas de seguridad, documentación y smoke humano). Se leyó el código antes de definirlo: las notas son texto en `tpi.leads.comentarios`
  y su parser falla cerrado; la web no tiene límite de tamaño de petición ni el backoffice cabeceras de seguridad en Caddy, por lo que la
  tarea los exige en la ruta; hay un limitador de tasa y un patrón de auditoría reutilizables.
- Decisión nueva: la página del lead no muestra el tamaño del archivo (no consulta S3 al renderizar); se muestra «Imagen adjunta» o «PDF
  adjunto».

### 2026-10-21 - CRM: herramienta de infraestructura S3 de los adjuntos, sin aplicar todavía (CRM-ADJUNTOS-1-INFRA-S3)

- Cambio (solo repositorio; **no se aplicó nada en AWS**): `deployment/aws/adjuntos_s3_infra.py` con los subcomandos `plan` (solo lectura),
  `apply`, `verify` y `rollback`; cuatro documentos de política en `deployment/iam/` (política del bucket, rol y confianza de GuardDuty
  y permiso de la app); procedimiento en `docs/ADJUNTOS_INFRA_S3.md`. `apply` y `rollback` exigen una frase de confirmación y el
  script comprueba la cuenta antes de actuar.
- Diseño de seguridad: la política del bucket impide leer `leads/*` a cualquiera (también al administrador) si el objeto no tiene la
  etiqueta `GuardDutyMalwareScanStatus=NO_THREATS_FOUND`; solo el rol de GuardDuty puede escribir o borrar esa etiqueta, y subir un
  objeto con la etiqueta puesta también se deniega. El rol de la app no tiene `ListBucket` ni permisos de etiquetas.
- Hallazgos de la lectura previa de AWS: GuardDuty no está activado en `us-east-2` (sin detectores ni planes); la instancia de Elastic
  Beanstalk es `t3.micro`, demasiado chica para un ClamAV propio, lo que confirma la elección de GuardDuty; no hay bloqueo de acceso
  público a nivel de cuenta (el bucket lo lleva propio); el usuario operador pertenece a `TPI_CTO_ADMINS` (AdministratorAccess).
- Pruebas: 29 pruebas nuevas (19 con un AWS simulado en memoria y 10 de seguridad sobre los documentos de política). Se comprobó con
  mutaciones que fallan si se rompe una política o el orden de `apply`.
- Pendiente: revisar y mergear este PR, ejecutar `plan`, `apply` y `verify` con el humano, y recién entonces cerrar el paso 1.

### 2026-10-21 - CRM: los adjuntos se simplifican a dos pasos y sin tabla (CRM-ADJUNTOS-COMENTARIOS)

- Decisión del humano: el mismo día de definir el diseño (PR #107) se pidió una forma más simple que una tabla de adjuntos. Se
  aprobó un diseño **sin tabla** y **sin re-codificar imágenes** en la primera versión.
- Nuevo diseño: el archivo y sus datos (tipo verificado, tamaño, SHA-256, quién lo subió) viven en S3 con clave `leads/<id_lead>/<uuid>`;
  la nota guarda una marca `[adjunto:<tipo>:<uuid>]` que agrega el servidor; el antivirus es GuardDuty Malware Protection for S3, que
  etiqueta cada objeto, y una política del bucket impide leer lo que no tenga `NO_THREATS_FOUND`; los eventos se auditan en `tpi.auditoria`.
  `tpi.auditoria` no sirve de registro porque su contrato prohíbe usar `detalle` como almacén de relaciones operativas.
- Efecto en el backlog: de cuatro pasos a dos. Se eliminan la tabla con su migración 010 (clase D) y el paso del antivirus. Quedan
  `CRM-ADJUNTOS-1-INFRA-S3` (bucket, permisos y GuardDuty; lo aplica el humano con Claude interactivo) y `CRM-ADJUNTOS-2-CODIGO`
  (clase C, porque agrega variables al compose de despliegue de DEV).
- Riesgos aceptados además de la visibilidad: al no re-codificar, EXIF y GPS de las imágenes quedan visibles; no hay transacción entre S3 y
  la nota (puede quedar un objeto huérfano si falla el borrado tras un error); no se puede consultar por SQL qué leads tienen adjuntos.
  Camino de vuelta: migrar a una tabla con los datos de las marcas y de S3.
- Cambio de este PR (solo documentación y backlog): `docs/ADJUNTOS_COMENTARIOS_DISENO.md` reescrito y `tasks/backlog.yaml` actualizado.

### 2026-10-21 - CRM: diseño de los adjuntos en las notas del lead (CRM-ADJUNTOS-COMENTARIOS)

- Decisiones del humano: PDF, PNG y JPEG verificados por contenido; 10 MB por archivo, 5 por nota y 25 MB por petición; **vista en línea**
  (imágenes en el detalle y PDF en una pestaña nueva) además de la descarga; retención mientras exista el lead y borrado a solicitud del
  titular (Ley 21.719); cada subida, vista y descarga auditada; visibles para **todos los usuarios con acceso al lead**.
- Riesgo aceptado: la interfaz enmascara los datos personales, pero un archivo no se puede enmascarar (una foto de una cédula la vería
  cualquier usuario con acceso al lead). Compensaciones: aviso al subir, auditoría de cada vista, borrado a solicitud y revisión tras el
  primer mes. Se deja constancia en `docs/SEGURIDAD.md` al implementar.
- Hallazgo que condiciona el diseño: las notas no son una entidad; son texto agregado a `tpi.leads.comentarios` (máximo 1000 caracteres
  por nota). Los adjuntos serán una tabla propia ligada al lead, que se sube junto con la nota, sin migrar las notas.
- Cambio de este PR (solo documentación y backlog): `docs/ADJUNTOS_COMENTARIOS_DISENO.md` y la división en cuatro pasos en el backlog:
  bucket S3 y permisos (clase C), tabla y migración 010 (clase D), código con interruptor apagado (clase A) y antivirus con habilitación
  (clase C). Los pasos 1 y 2 son independientes. `CRM-ADJUNTOS-COMENTARIOS` queda como paraguas y no se activa.

### 2026-10-21 - Seguridad: Streamlit retirado y Pillow 13 desplegados; excepción de pip-audit cerrada (SEG-DESACOPLAR-STREAMLIT)

- Resultado: el humano aceptó AC-7 y AC-8 en DEV (inicio de sesión en el backoffice, lista y detalle de leads, asistente del simulador con
  el PDF y su logo, y API pública). La tarea terminó en la ronda 0, sin rechazos del Reviewer.
- Cambio (PR #103, `0c9b165`; 58 archivos, +365 y −3128 líneas): el código legado de Streamlit salió del repositorio, `pillow` subió a
  13.0.0 y se retiró la excepción de `pip-audit` (8 avisos de Pillow 12.3.0, PR #99, que vencía el 2026-11-20) junto con su prueba guardia.
  `pip-audit` pasa sin excepciones en el CI y en el publish. Al irse Streamlit hubo que declarar `uvicorn`, `Jinja2`, `python-multipart`
  e `itsdangerous`, que antes llegaban como dependencias transitivas.
- Release: publish a ECR en el primer intento (run 39622446165, escaneo COMPLETE sin hallazgos en las dos imágenes). Despliegue con un único
  `update-environment` por version label, convergió en unos 46 s, entorno Ready/Green/Ok, sin rollback. Verificación automática PASS
  (smoke HTTP 5/5, 0 coincidencias en los patrones de PII, secretos y `Traceback`).
- Es una tarea de clase C que cambia la aplicación: tras el merge pasó por `BLOCKED_HUMAN` y el humano resolvió hacia
  `PREPARING_DEPLOYMENT`. La definición de la tarea lo decía de forma explícita y el flujo funcionó sin ambigüedad.
- Bloqueos del guard durante el desarrollo (dos sesiones del Developer, sin pérdida de trabajo): (1) el nombre del SDK de AWS escrito en un
  comando de shell, porque la regla de `policies.yaml` busca esa palabra en cualquier comando; (2) la creación de un script suelto en la raíz
  del worktree, que el guard no permite y que había sugerido el propio humano. Ambos eran de forma, no de fondo; el humano dejó notas en
  `progress/current.md` y el Developer continuó desde su trabajo previo y entregó.
- Incidente menor: la sesión AWS expiró antes del release. El orquestador lo detectó antes de lanzar al Deployer y pidió reautenticar,
  sin perder estado.
- Lecciones:
  - Una instrucción al Developer no puede pedir algo que el guard prohíbe: las rutas permitidas y las reglas de texto de `policies.yaml` se
    revisan antes de dar una indicación operativa.
  - Las dependencias exclusivas de Streamlit (altair, pandas, pyarrow, pydeck, protobuf y watchdog, entre otras) salieron del lock de
    runtime; `jsonschema` pasó al lock de desarrollo porque lo usa `scripts/harness/common.py`. El lock de desarrollo se verificó con
    `pip install --dry-run`, que resuelve sin conflictos.
  - Con la excepción de Pillow cerrada vuelve a ser posible aceptar archivos de usuarios sin una excepción de seguridad vigente: se
    desbloquea la dependencia de `CRM-ADJUNTOS-COMENTARIOS` (sigue pendiente de decisiones del humano).
- Pendiente: el humano borra `.streamlit/` en un PR aparte (el guard no lo permite al Developer). Quedan residuos cosméticos sin efecto
  en el runtime (docstrings en `app/`, texto en `scripts/generate_coverage_report.py`, `check_streamlit.py` en la raíz y los diagramas de
  `docs/ARCHITECTURE.md`); se registran en el backlog como `SEG-LIMPIEZA-RESIDUOS-STREAMLIT`.

### 2026-10-21 - Harness: tarea SEG-DESACOPLAR-STREAMLIT cerrada (DONE)

- Titulo: Retirar Streamlit del proyecto y subir Pillow a 13 para eliminar la excepcion de pip-audit
- Evidencia: `evidence/SEG-DESACOPLAR-STREAMLIT/` y `tasks/completed/SEG-DESACOPLAR-STREAMLIT.yaml`.
- release_sha: `0c9b16599c84e1bd4c3e198f6efa4733f1785e76`
- pr_number: `103`
- application_version: `h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1`
- bundle_sha256: `c187fd6bf9bb9997efdce754068e5729621e3f3b8a0ab6a940f7ed4b419b4d39`
- lkg: `h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1`
- deployment: `success`
- deployed_commit: `0c9b16599c84e1bd4c3e198f6efa4733f1785e76`
- verification: `PASS`

### 2026-10-21 - Seguridad: retirada de Streamlit del runtime y Pillow 13 (SEG-DESACOPLAR-STREAMLIT, en desarrollo)

- Cambio (change_class C, `allow_lockfile_update` solo para quitar Streamlit y subir Pillow): se retira el código legado de Streamlit
  (`app/streamlit_app.py`, `app/backoffice_app.py`, `app/pages/`, `app/presentation/`, `app/internal_tools/`, `app/components/ui.py`,
  `app/auth/guards.py` y `app/runtime.py`) junto con las pruebas que solo lo ejercitaban. La API y la web no cambian de comportamiento.
- Se mueven sin reescribir los helpers que la web/API sí usan: `get_public_site_url`/`get_public_simulator_url` a
  `app/components/urls.py`, `format_currency_clp` a `app/components/formatting.py` y `log_health_status` a `app/database/healthcheck.py`.
- Dependencias: `streamlit` y sus dependencias exclusivas salen de `requirements/runtime.lock`; `pillow` sube a 13.0.0. Se declaran
  explícitamente `uvicorn`, `Jinja2`, `python-multipart` e `itsdangerous`, que antes llegaban transitivamente vía Streamlit.
- Dockerfile sin `STREAMLIT_*` ni `COPY .streamlit`, con `CMD` uvicorn `app.web.main:app` en `:8501`; el backoffice de `docker-compose.yml`
  local hace lo mismo. El compose de despliegue (ECR) ya usaba uvicorn y no cambia.
- Se cierra la excepción de `pip-audit` para los 8 avisos de Pillow 12.3.0: fuera los `--ignore-vuln` de `ci.yml` y
  `publish-dev-ecr-images.yml`, fuera `tests/security/test_excepcion_pip_audit_pillow.py` y actualizada la sección de `docs/SEGURIDAD.md`.
  `pip-audit --requirement requirements/runtime.lock` pasa sin excepciones.
- Nuevo test `tests/unit/test_streamlit_retired.py`: importa ambos entrypoints con `streamlit` bloqueado y comprueba estáticamente que
  ningún archivo de `app/` lo importa.

### 2026-10-21 - Publish de ECR: la espera del escaneo sube a 20 minutos (H3.2-ECR-SCAN-WAIT)

- Cambio (PR #101, `dfb1d7f`): el paso del escaneo de `publish-dev-ecr-images.yml` espera hasta 20 minutos, con sondeo cada 15 segundos,
  mediante el script `scripts/release/wait_for_ecr_scan.py`. Los fallos tienen mensajes propios: el escaneo no terminó en el plazo (aclara
  que no hay hallazgos verificados y apunta a la recuperación), el escaneo terminó en `FAILED` o `UNSUPPORTED_IMAGE`, o hay hallazgos
  HIGH/CRITICAL. El gate sigue cerrando en falso: sin escaneo `COMPLETE` con CRITICAL=0 y HIGH=0 no se arma el bundle. El procedimiento de
  recuperación (revisar el escaneo, borrar las dos imágenes del release por sus tags inmutables y relanzar con el mismo SHA) quedó en
  `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`.
- Resultado: clase C con `deploy_required: false`; cerró sola al hacer merge (`merged_no_deploy`), sin pasar por `BLOCKED_HUMAN`. Confirma la
  lección de `H3.2-ECR-LIFECYCLE`: una tarea de infraestructura sin cambio de la aplicación se define con `deploy_required: false`.
- Validación real diferida: el workflow solo se ejercita en el próximo release; mientras tanto lo cubren pruebas estáticas del YAML y del
  script con el CLI de AWS simulado (5 escenarios). Observación del Reviewer: el script se detiene en la primera imagen con fallo, sin evaluar
  la segunda; sigue siendo fail-closed.
- Incidente: el Developer (DeepSeek) se detuvo a los 22 minutos con `402 Insufficient Balance` cuando el PR ya estaba en verde. El supervisor
  paró con `failed` y la tarea quedó intacta en `DEVELOPING`; tras recargar el saldo, el Developer entregó en menos de 5 minutos. Lección: un
  `failed` con 402 no es un fallo de la tarea; se recarga el saldo y se relanza el orquestador.
- Límite que no resuelve: un escaneo atascado más de 20 minutos (como el del 2026-10-20) sigue fallando el publish; para eso está el
  procedimiento documentado.

### 2026-10-21 - Harness: tarea H3.2-ECR-SCAN-WAIT cerrada (DONE)

- Titulo: Publish de imagenes a ECR: esperar el escaneo hasta 20 minutos y fallar con un mensaje claro
- Evidencia: `evidence/H3.2-ECR-SCAN-WAIT/` y `tasks/completed/H3.2-ECR-SCAN-WAIT.yaml`.
- release_sha: `f82180fc57b479ddde307c12e2bdce41c0e045fa`
- pr_number: `101`

### 2026-10-21 - Publish a ECR: esperar el escaneo hasta 20 minutos y fallar con mensajes claros (H3.2-ECR-SCAN-WAIT, en desarrollo)

- Contexto: el publish del release fallo dos veces (2026-10-16 y 2026-10-20) porque el escaneo de ECR no terminaba en los 5 minutos que esperaba el workflow y quedaba atascado mas de 20-47 minutos (lo normal es de 14 a 35 s). El workflow tampoco distinguia entre «escaneo lento», «escaneo fallido» y «hallazgos reales».
- Cambio (change_class C, sin despliegue): `publish-dev-ecr-images.yml` espera hasta `SCAN_TIMEOUT_MINUTES=20` minutos (sondeo cada `SCAN_POLL_SECONDS=15` s) a que ambas imagenes (`tpi-dev-app` y `tpi-dev-caddy`) tengan el escaneo `COMPLETE`, con gate fail-closed (`CRITICAL=0` y `HIGH=0`; `IN_PROGRESS` nunca cuenta como exito). La logica de espera se extrae a `scripts/release/wait_for_ecr_scan.py`.
- Mensajes de fallo: (a) no termino en el plazo (aclarando que NO hay hallazgos verificados, con los digests y la recuperacion); (b) termino en `FAILED` o `UNSUPPORTED_IMAGE`; (c) hallazgos HIGH/CRITICAL con el detalle.
- Recuperacion cuando el publish falla por el escaneo: revisar el estado del escaneo de ambos digests, borrar las dos imagenes del release (los tags son inmutables, lo hace el humano) y relanzar el workflow con el mismo SHA. Documentado en `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`.
- Sin cambios de permisos IAM/OIDC, de la politica de tags ni de la publicacion de imagenes; no se toca el paso de pip-audit ni la excepcion de Pillow.
- Siguiente paso: correr las pruebas locales (sin BD) y entregar a revision.

### 2026-10-21 - Simulador: línea de tiempo tolerante a eventos antiguos desplegada e incidente de release (SIM-HISTORIAL-EVENTOS-ANTIGUOS)

- Resultado: el humano aceptó AC-5 y AC-6 en DEV. El lead que daba «Internal Server Error» abre sin error y su línea de tiempo muestra
  sus 5 simulaciones: 4 antiguas con la nota «Registro anterior al guardado de entradas…» y 1 completa con su detalle.
- Incidente en el release (cronología, 2026-10-20):
  1. El CI del PR #97 falló en `Security Audit`: `certifi 2026.7.22` (GHSA-6q48-6c7w-9gw2). Se corrigió con el PR #98
     (`certifi 2026.10.19`); el Developer trajo `main` a su rama y entregó.
  2. El publish del release `793e718` falló: el escaneo de ECR no terminó en los 5 minutos del workflow y quedó atascado más de
     47 minutos (lo normal es de 14 a 35 s). El Deployer se detuvo en `BLOCKED_HUMAN` (`preparation_failed`).
  3. Se borraron las dos imágenes del release con una herramienta de una sola vez (espera opcional del escaneo, frase de
     confirmación, probada con 19 escenarios simulados) y se relanzó el publish. Volvió a fallar, esta vez en `Security Audit`:
     8 avisos nuevos de `pillow 12.3.0`, corregidos solo en Pillow 13.0.0.
  4. `streamlit` (hasta la 1.66.0) exige `pillow<13`, por lo que no se podía subir. Además el workflow audita el lock del commit
     que publica, así que `793e718` no podía pasar sin cambiar el workflow.
  5. Decisión del humano: excepción acotada de `pip-audit` para esos 8 IDs (PR #99, vence 2026-11-20, vigilada por una prueba del
     CI). El publish de `793e718` terminó bien (run 39516711668, escaneo COMPLETE sin hallazgos); el humano resolvió a
     `PREPARING_DEPLOYMENT`; siguieron candidato, gate, despliegue, verificación y aceptación.
- Lecciones:
  - El workflow de publicación toma su definición de `main` pero audita el lock del commit que publica: una excepción puesta en
    `main` también vale para un commit ya mergeado, lo que evitó rehacer el release.
  - Un escaneo de ECR puede atascarse; esperar a uno atascado no sirve, hay que borrar las imágenes y volver a publicar para que se
    escaneen de nuevo. La espera de 5 minutos del workflow es corta.
  - Los avisos de dependencias aparecen sin cambiar el código: un PR verde por la mañana puede fallar por la tarde.
  - Antes de aceptar una excepción de seguridad hay que preguntar por los planes del producto: la futura función de adjuntos en los
    comentarios invalidó el argumento «la app no recibe archivos de usuarios» y obligó a ponerle vencimiento y una guardia.
- Backlog (definido en este PR de cierre): `H3.2-ECR-SCAN-WAIT` y `SEG-DESACOPLAR-STREAMLIT` (decisión del humano: retirar el código
  legado de Streamlit, no aislarlo), listas para activar; `CRM-ADJUNTOS-COMENTARIOS` (bloqueada hasta la anterior, con los resguardos
  como requisitos) y `SIM-CANARIA-MENSUAL` (requiere una persona con credenciales del portal).
- Estado: la excepción de Pillow sigue vigente hasta 2026-11-20 o hasta que `SEG-DESACOPLAR-STREAMLIT` la elimine, lo que ocurra
  primero; ningún archivo de usuarios puede aceptarse antes.

### 2026-10-21 - Harness: tarea SIM-HISTORIAL-EVENTOS-ANTIGUOS cerrada (DONE)

- Titulo: Linea de tiempo del lead: no fallar con simulaciones registradas antes de guardar sus entradas
- Evidencia: `evidence/SIM-HISTORIAL-EVENTOS-ANTIGUOS/` y `tasks/completed/SIM-HISTORIAL-EVENTOS-ANTIGUOS.yaml`.
- release_sha: `793e718aaf8f4dcd52e1cd12644f8b514984202f`
- pr_number: `97`
- application_version: `h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1`
- bundle_sha256: `8c341278fdf069cd925219bf6d7004c963ac485738a04a4c17c3a6f5e000aa79`
- lkg: `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`
- deployment: `success`
- deployed_commit: `793e718aaf8f4dcd52e1cd12644f8b514984202f`
- verification: `PASS`

### 2026-10-20 - Seguridad: excepción acotada de pip-audit para 8 avisos de Pillow 12.3.0

- Hallazgo: poco después del bump de `certifi` (#98) `pip-audit` empezó a reportar 8 avisos en `pillow 12.3.0`
  (CVE-2026-112395, 112397, 112400, 112404, 112895, 112896, 112897 y 112899), todos corregidos solo en Pillow 13.0.0. Eso hizo
  fallar el `Security Audit` del CI y del workflow de publicación, y dejó el release `793e718` de `SIM-HISTORIAL-EVENTOS-ANTIGUOS`
  sin poder publicarse (el workflow audita el lock del commit que publica).
- Por qué no se actualiza: `streamlit` (1.60.0 y también la última, 1.66.0) exige `pillow<13`. Streamlit no puede salir del runtime
  todavía: `app.web.main` y la API lo importan a través de `app.auth` (`guards.py`) y `app.components.ui`.
- Riesgo evaluado: los avisos exigen abrir una imagen o un PDF enviado por un atacante. La aplicación no recibe archivos de
  usuarios, no usa Pillow directamente y solo abre el logo fijo del repositorio (vía `reportlab`).
- Decisión del humano (2026-10-20): excepción acotada a esos 8 IDs, en `ci.yml` y en `publish-dev-ecr-images.yml`, con fecha de
  vencimiento 2026-11-20. Como el workflow de publicación toma su definición de `main`, también aplica al publicar el commit
  `793e718` ya mergeado.
- Resguardos: nueva prueba `tests/security/test_excepcion_pip_audit_pillow.py` que falla si los workflows difieren de los 8 IDs
  documentados, si aparece código que reciba archivos de usuarios, si cambia la versión de Pillow o si llega el vencimiento.
  Sección «Excepciones de pip-audit» en `docs/SEGURIDAD.md` con la condición de salida.
- Motivo de fondo de los resguardos: el humano planea una función de adjuntos (imágenes y PDF) en los comentarios del CRM. La
  excepción deja de ser válida en ese momento, así que la salida (Pillow >= 13 vía desacople de Streamlit) es requisito previo.
- Siguiente paso: tareas `SEG-DESACOPLAR-STREAMLIT` y `CRM-ADJUNTOS-COMENTARIOS` en el backlog (se agregan en el PR de cierre de
  la tarea en curso) y reintento del publish de `793e718`.

### 2026-10-20 - Línea de tiempo del lead: tolerar simulaciones anteriores a SIM-EVIDENCIA-ENTRADAS (SIM-HISTORIAL-EVENTOS-ANTIGUOS, en desarrollo)

- Tarea `SIM-HISTORIAL-EVENTOS-ANTIGUOS` (clase A, fast path version-only): el detalle del lead no debe fallar por la forma
  de un evento de simulación. Las simulaciones registradas antes de `SIM-EVIDENCIA-ENTRADAS` (2026-10-16) tienen un
  `detalle` con solo `actor_subject`, `role`, `tipo_escenario`, `version_modelo` y `codigo_verificacion`; la vista
  `tpi.v_historial_simulaciones` devuelve `entradas` y `resultado` en `NULL`, y la plantilla del detalle encadenaba
  `item.entradas.causante.sexo` sobre un valor indefinido, lo que en Jinja lanza `UndefinedError` y tumba la página del
  lead con un 500.
- Corrección en `app/web/presentation.py`: `build_timeline_items` normaliza `entradas` y `resultado` a una forma segura
  (claves fijas con fallback `None`; `causante` y `beneficiarios` normalizados) y marca los eventos antiguos con
  `es_legacy` (`entradas` y `resultado` ambos `NULL`). La plantilla (`app/web/templates/lead_detail_panel.html`) muestra
  para esos eventos «Simulación generada» con ejecutivo, escenario, versión del modelo y código, más la nota «Registro
  anterior al guardado de entradas: solo se conservan escenario, version y codigo», sin el detalle desplegable; los
  eventos con evidencia completa se muestran como hasta ahora.
- La presentación y la plantilla toleran cualquier dato faltante o nulo (entradas o resultado ausentes, causante ausente,
  beneficiarios vacíos, beneficiarios con campos faltantes y fechas nulas) sin producir un 500. Sin cambios de base de
  datos, vistas, `scripts/sql/**`, `app/simulador_pension/**` ni `app/auth/**`.
- Pruebas: unitarias de presentación (`tests/unit/test_sim_historial_timeline_presentation.py`), de render del detalle
  (`tests/unit/test_web_app.py`) y de integración en PostgreSQL (`tests/integration/test_audit_simulation_view.py`) con
  filas de ambas formas (antigua y completa) leídas a través de `tpi.v_historial_simulaciones`.

### 2026-10-20 - Seguridad: certifi 2026.7.22 → 2026.10.19 (GHSA-6q48-6c7w-9gw2)

- Hallazgo: el CI del PR #97 (`SIM-HISTORIAL-EVENTOS-ANTIGUOS`) falló en `Security Audit`: `pip-audit` reportó 1 vulnerabilidad
  conocida en `certifi 2026.7.22` (GHSA-6q48-6c7w-9gw2, corregida en `2026.10.19`). El aviso se publicó entre el último CI verde
  de `main` (2026-10-20 14:49 UTC) y las 20:11 UTC, así que afecta a cualquier PR hasta que `main` lo incorpore.
- Efecto en el Harness: la tarea no puede tocar dependencias y el guard `g_developer_evidence_valid` rechaza evidencia con un gate
  en rojo, por lo que el Developer se detuvo correctamente (`no_progress`) en lugar de falsear la evidencia.
- Cambio: `requirements/runtime.lock`, una línea: `certifi==2026.10.19` (última versión publicada). `dev.lock` no incluye `certifi`.
- Verificación: `pip-audit --requirement requirements/runtime.lock` da «No known vulnerabilities found» con el cambio y reproduce
  la vulnerabilidad con el lock anterior.
- Solo dependencia transitiva de ejecución: sin cambios de código, base de datos ni configuración.
- Siguiente paso: tras el merge, el PR de la tarea en curso debe traer `main` a su rama para que su CI pase.

### 2026-10-20 - Simulador: migración 009 aplicada en DEV y defecto con eventos antiguos (SIM-HISTORIAL-LINEA-TIEMPO)

- Migración 009 aplicada y verificada en AWS DEV por el humano (2026-10-20, 10:34 hora de Chile) con una herramienta de una sola
  vez que simula primero y deshace (ROLLBACK), pide una frase de confirmación, usa el SQL exacto del commit `e4476c3` (huella
  `6a5247dc14d6`) y verifica antes y después del COMMIT. Resultado: vista `tpi.v_historial_simulaciones` creada con
  `security_barrier` y las 9 columnas esperadas; `tpi_app` con SELECT sobre la vista y sin SELECT/UPDATE/DELETE sobre
  `tpi.auditoria`; `PUBLIC` sin privilegios; la vista mostró 15 simulaciones, igual que la tabla. PostgreSQL 17.9, usuario
  `tpi_admin`. Luego el humano resolvió el bloqueo hacia `PREPARING_DEPLOYMENT`.
- Despliegue: versión `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`. Verificación PASS (smoke 6/6 y 0 coincidencias
  en los 8 patrones de logs). Aceptados AC-2, AC-5 y AC-6.
- Defecto hallado por el humano al verificar: un lead de DEV con simulaciones anteriores a `SIM-EVIDENCIA-ENTRADAS` mostraba
  solo «Internal Server Error». Causa: esos eventos (2026-10-14 a 2026-10-16) tienen un `detalle` con solo cinco metadatos
  (`actor_subject`, `role`, `tipo_escenario`, `version_modelo`, `codigo_verificacion`); la vista devuelve `entradas` y
  `resultado` en NULL; `build_timeline_items` los normaliza a `{}` y la plantilla lee `item.entradas.causante.sexo`, que en
  Jinja lanza `UndefinedError` y tumba toda la página del lead (500). Reproducido con la plantilla real y confirmado en DEV:
  ese lead tiene 4 eventos antiguos y 1 completo.
- Por qué no se detectó: ni las pruebas del Developer, ni la revisión, ni la definición de la tarea consideraron la evidencia
  anterior a `SIM-EVIDENCIA-ENTRADAS`. Las pruebas usaron solo eventos con el esquema nuevo.
- Lección: una presentación que lee datos históricos se prueba con cada forma que el dato ha tenido en el tiempo. Al definir una
  tarea que lee datos existentes, consultar en DEV las formas reales (por ejemplo `entradas IS NULL`) y exigirlo en un criterio.
- Decisión del humano (2026-10-20): aceptar esta tarea y corregir con una tarea nueva, clase A y P0:
  `SIM-HISTORIAL-EVENTOS-ANTIGUOS`, definida en el PR de cierre. Hasta que se despliegue, los leads con simulaciones de ese
  periodo siguen fallando en DEV.

### 2026-10-20 - Harness: tarea SIM-HISTORIAL-LINEA-TIEMPO cerrada (DONE)

- Titulo: Linea de tiempo del lead: mostrar las simulaciones generadas
- Evidencia: `evidence/SIM-HISTORIAL-LINEA-TIEMPO/` y `tasks/completed/SIM-HISTORIAL-LINEA-TIEMPO.yaml`.
- release_sha: `e4476c325395d849c32b1c521687e1d56f6ee22e`
- pr_number: `95`
- application_version: `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`
- bundle_sha256: `d6f6015d921f19dbaac49b8bcadcf165fbd95c27faaca679c4c2961893fcd6da`
- lkg: `h3-sim-wizard-3-pasos-4ee5fad-domainlocked-r1`
- deployment: `success`
- deployed_commit: `e4476c325395d849c32b1c521687e1d56f6ee22e`
- verification: `PASS`

### 2026-10-20 - Simulador: línea de tiempo del lead con las simulaciones generadas (en desarrollo, DEVELOPING)

- Tarea `SIM-HISTORIAL-LINEA-TIEMPO` (clase D, db_path): mostrar en la línea de tiempo del detalle del lead cada
  simulación generada, con toda la evidencia registrada, leyéndola de una vista de solo lectura sobre `tpi.auditoria`
  (mismo patrón que asignaciones y cambios de estado).
- Migración `009` (`scripts/sql/009_create_historial_simulaciones.sql` + `009_drop_historial_simulaciones.sql`):
  - Vista `tpi.v_historial_simulaciones` con `security_barrier`, filtro fijo `accion = 'simulacion_renta_vitalicia'`
    AND `tabla_afectada = 'tpi.leads'`.
  - Columnas: `id_auditoria`, `id_lead`, `fecha_hora`, `actor_subject`, `tipo_escenario`, `version_modelo`,
    `codigo_verificacion`, `entradas` (JSONB completo) y `resultado` (JSONB completo). No se censura ningún dato
    registrado (decisión del humano 2026-10-19).
  - `REVOKE ALL FROM PUBLIC`; `GRANT SELECT` solo a `tpi_app`; sin `SELECT` directo sobre `tpi.auditoria`. Sin índice
    nuevo: reutiliza `auditoria_state_history_idx` de la migración `008` (sus columnas líderes coinciden con el filtro).
- Aplicación: `SolicitudRepository.get_lead_simulation_events` (lee solo la vista), `SolicitudService`, la presentación
  de la línea de tiempo (`build_timeline_items` con `kind='simulation'`) y el template del detalle (resumen + detalle
  desplegable con entradas y resultado). La visibilidad sigue las reglas vigentes del detalle del lead.
- Bootstrap de tests (`scripts/init_test_database.py`) actualizado con la vista; pruebas unitarias (scripts y
  presentación) e integración (`tests/integration/test_audit_simulation_view.py`) sobre PostgreSQL.
- Procedimiento de aplicación y reversa en AWS DEV (para el humano) documentado en `docs/database/04_MIGRATIONS.md`
  (Notas sobre `009`): preflight/postflight con `tpi_admin`, aplicación única y reversa idempotente.
- Impacto y rollback: solo crea/elimina la vista y su grant; no toca `tpi.auditoria` ni los objetos de `007`/`008`.
- Siguiente paso: revisión independiente del PR y, tras el merge, aplicar la migración en AWS DEV vía Human Gate.

### 2026-10-19 - Simulador: el Excel y el script de las tablas de mortalidad pasan al repositorio

- Pedido del humano: traer al repositorio el script y el Excel de los que salen las tablas de mortalidad, y dejarlo todo
  documentado en el manual de uso del simulador (`docs/SIMULADOR_USO.md`).
- Nueva carpeta `scripts/tablas_mortalidad/`:
  - `tablas-mortalidad-cmf.xlsx`: Excel de la CMF sin editar (141.411 bytes, descargado el 2026-10-13).
  - `procedencia.json`: fuente, norma (NCG N.º 495 de la CMF), fecha, tamaño, `sha256` y verificaciones ya hechas.
  - `construir_tablas.py`: el script de la investigación (REA), con tres cambios: escribe en este repositorio, valida los
    encabezados del Excel antes de leer y tiene el modo `--verificar`.
  - `README.md`: qué contiene el resultado, qué tabla usa el simulador en cada rol, comandos y procedimiento de actualización.
- Comprobación: el `.npz` que ya usaba el motor se reconstruye idéntico desde el Excel (los 12 arreglos, incluidos los
  valores vacíos de la tabla de mujeres pensionadas antes de los 20 años). No cambia ningún valor del motor ni su versión.
- Prueba nueva `tests/unit/test_tablas_mortalidad.py` (8 pruebas): falla en el CI si el Excel deja de coincidir con
  `procedencia.json`, si el `.npz` deja de reconstruirse desde el Excel, si cambia la estructura de las tablas, o si un Excel
  con otra estructura no produce un error claro.
- Manual de uso: §8.1, §8.2 (insumos, comandos, protección del CI y procedimiento), §8.7, §8.9, §9 (hallazgo 4 resuelto) y §10.
- Solo herramientas, datos públicos y documentación: sin cambios de código de la aplicación, base de datos ni despliegue.
- Siguiente paso: consolidar la campaña canaria en un único script y programar la primera campaña (la ventana validada
  venció el 2026-10-13); contrastar la convención de la columna «2036*» con la documentación oficial.

### 2026-10-19 - Simulador: corrección del documento de uso (`docs/SIMULADOR_USO.md`)

- Corrección al documento mergeado en #90: sí se encontró el Excel de la CMF del que salen las tablas de mortalidad (la
  búsqueda inicial se quedó corta). Está en el workspace de REA
  (`homologacion_simulador/entrega-2026-10-13-v1/investigacion/ejecucion-vejez-edad/tablas-mortalidad-cmf.xlsx`) y la CMF
  publica un archivo del mismo tamaño. El script que construye el `.npz` sigue solo en `REA/simulador_pension/scripts`.
- Se incorporan: nombres oficiales de las tablas, su vigencia (NCG N.° 495 de la CMF, 24-feb-2023; rigen desde el 1-jul-2023;
  según el sitio oficial, uso máximo de 6 años, o sea revisión hacia mediados de 2029), la comparación de 3.636 valores
  contra el módulo de la SP y la convención sin verificar para los años posteriores a 2036.
- Se detalla la campaña canaria (qué es, qué hace falta, cobertura sugerida, qué hacer con el resultado y las fragilidades
  de la herramienta actual).
- Solo documentación: sin cambios de código, base de datos ni despliegue.
- Siguiente paso: tareas para (1) traer al repositorio el script y el Excel de las tablas y (2) consolidar la campaña
  canaria en un único script; programar la primera campaña, porque la ventana validada venció el 2026-10-13.

### 2026-10-19 - Harness: tarea SIM-WIZARD-3-PASOS cerrada (DONE)

- Titulo: Simulador: asistente de 3 pasos (datos, grupo familiar, resultado) con la marca de TPI
- Evidencia: `evidence/SIM-WIZARD-3-PASOS/` y `tasks/completed/SIM-WIZARD-3-PASOS.yaml`.
- release_sha: `4ee5fad2f57abe0842a5beaede4bf981299d953e`
- pr_number: `89`
- application_version: `h3-sim-wizard-3-pasos-4ee5fad-domainlocked-r1`
- bundle_sha256: `9bbcbac1881e8660cf10642f93b094796987316b953b6bc2ea3eebf49cc001e0`
- lkg: `h3-sim-evidencia-entradas-a7859af-domainlocked-r1`
- deployment: `success`
- deployed_commit: `4ee5fad2f57abe0842a5beaede4bf981299d953e`
- verification: `PASS`

### 2026-10-19 - Simulador: documento de uso y mantención (`docs/SIMULADOR_USO.md`)

- Pedido del humano durante la verificación de `SIM-WIZARD-3-PASOS`: documentar qué casos soporta el simulador, cuáles
  quedan fuera y qué hay que hacer para mantenerlo vigente (por ejemplo, las tablas de mortalidad).
- Se revisó el motor (`app/simulador_pension`), el servicio, la ruta y el asistente; se ejecutaron las pruebas de
  regresión, validación y ventana (55 en verde) y se midió la cobertura real del fixture de 435 casos.
- Solo documentación: sin cambios de código, base de datos ni despliegue. Se enlaza desde `docs/INDEX.md`.
- Hallazgos que quedan anotados en el documento (§9), sin acción obligatoria:
  - La ventana de fechas validada terminó el 2026-10-13; el motor avisa internamente pero la pantalla y el PDF no.
  - El PDF no lista el grupo familiar: solo imprime «CÓNYUGE: Sí» y no recibe los hijos. Decisión del humano
    (2026-10-19): se mantiene así, no se agrega.
  - El script que construye las tablas de mortalidad y el Excel de la CMF no están en el repositorio.
  - Con cónyuge e hijos el código admite causantes desde 60 años y la evidencia empieza en 62.
- Siguiente paso: programar la campaña canaria mensual (ventana de fechas) y ubicar el script y el Excel de las tablas.


### 2026-10-19 - Simulador: asistente de 3 pasos con la marca de TPI (en desarrollo, DEVELOPING)

- Tarea `SIM-WIZARD-3-PASOS` (clase A, fast path version-only): rehacer la pantalla del simulador como un asistente de
  3 pasos (Datos de la simulación, Grupo familiar, Resultado) con el flujo y la estructura del simulador de referencia y
  la marca de TPI, sin cambios en el motor, el alcance validado ni la autorización.
- Cambios:
  - `app/web/routes/simulador.py`: el POST despacha por `intent` (`continuar`, `volver_paso1`/`volver_paso2`, `simular`,
    `descargar_pdf`); `simular` calcula en el servidor y muestra el resultado en el paso 3 sin persistir ni auditar, y
    `descargar_pdf` conserva la generación del PDF efímero con su evento append-only de auditoría. Se agrega
    `tipo_pension` y el rechazo del cónyuge inválido (pendiente #8 de `docs/SIM_RV_V1_PENDIENTES.md`).
  - `app/web/templates/simulador.html`: asistente de 3 pasos, indicador de pasos, tabla del grupo familiar con modal de
    beneficiario, tarjetas de resultado, resumen y aviso «Valores referenciales, no vinculantes».
  - `app/web/static/js/simulador_wizard.js`: JavaScript propio (sin CDN) que gestiona el modal y la tabla de beneficiarios
    a partir de los inputs ocultos del formulario.
  - `app/web/static/css/app.css`: estilos del asistente con los tokens del CRM y el azul marino `#0f243e` de la ficha; sin
    el naranja del simulador de referencia.
- Decisión documentada: la relación RVD/RT queda oculta en 100 en el asistente, porque el simulador de referencia no la
  expone en su paso de datos; el motor y la API siguen aceptando 50/51–99 (sin cambios en el alcance validado).
- Sin migraciones, grants, vistas, constraints ni infraestructura (clase A); el motor `app/simulador_pension/**`,
  `app/auth/**` y las dependencias no cambian.
- Pruebas nuevas: `tests/unit/test_sim_wizard.py` (flujo del asistente, validación por paso, no auditoría en `simular`,
  marca TPI y JS propio). La cobertura y la suite completa las valida el CI del PR.

### 2026-10-19 - Simulador: la evidencia de entradas se retiene de forma indefinida

- Decision del humano (2026-10-19): la evidencia de entradas y resultado del simulador (`tpi.auditoria.detalle`, accion
  `simulacion_renta_vitalicia`, creada por `SIM-EVIDENCIA-ENTRADAS`) se conserva **de forma indefinida**, sin purga ni
  expiracion. Cierra la politica de retencion que estaba pendiente.
- Efecto en el trabajo pendiente: `SIM-HISTORIAL-LINEA-TIEMPO` ya no depende de esa decision.
- Sin cambios de codigo, de base de datos ni de despliegue: solo documentacion
  (`docs/SIM_RV_V1_MODELO.md`, `docs/SIM_RV_V1_PENDIENTES.md`, `CHANGELOG.md`).
- Riesgo abierto: el detalle guarda fechas de nacimiento vinculadas a un lead por `id_lead` (sin nombres, RUT, correo ni
  telefono). Queda anotada la revision normativa de la retencion indefinida con asesoria legal (Ley 19.628 y su reemplazo,
  Ley 21.719): si se exigiera un plazo o un mecanismo de supresion, se decide en una tarea nueva; una purga de un registro
  append-only requiere migracion (clase D) aplicada por el humano. No es asesoria legal.
- La entrada del 2026-10-15 de `SIM-EVIDENCIA-ENTRADAS` que dice «retencion pendiente» es historia y no se reescribe; esta
  entrada la reemplaza.

### 2026-10-19 - Harness: tarea H3.2-ECR-LIFECYCLE cerrada (DONE)

- Titulo: Lifecycle de ECR compatible con rollback: conservar 100 imagenes
- Evidencia: `evidence/H3.2-ECR-LIFECYCLE/` y `tasks/completed/H3.2-ECR-LIFECYCLE.yaml`.
- release_sha: `2b0fea25cd9e6b1ad336121719f4fb6362740f58`
- pr_number: `85`
- Aplicacion en AWS DEV (humano, 2026-10-19): politica de `deployment/ecr/lifecycle-policy.json` aplicada en `tpi-dev-app` y `tpi-dev-caddy` (regla de retencion de 20 a 100 imagenes); vista previa previa con 20 imagenes por repositorio: 0 expiraciones; verificada con `get-lifecycle-policy`.
- Cierre MANUAL (humano): la tarea, de infraestructura y sin cambio de la aplicacion, se definio con `deploy_required: true`. Tras aplicar y verificar la politica, el humano resolvio hacia `VERIFYING`, que no tiene salida valida sin evidencia de aprobacion y de despliegue que la tarea nunca tuvo (`verified` la exige; `verify_failed` habria sido un fallo inventado), y el Deployer quedo detenido por una lectura de `ecr get-lifecycle-policy` no permitida en `VERIFYING`. Se cerro con un script de una sola vez que registra `manual_close` (actor humano) en el historial y ejecuta el cierre oficial del Harness. Leccion: una tarea de infraestructura que aplica el humano sin cambio de la aplicacion debe definirse con `deploy_required: false` (cierra sola al hacer merge, `merged_no_deploy`) o resolverse hacia `PREPARING_DEPLOYMENT`.

### 2026-10-19 - H3.2-ECR-LIFECYCLE: lifecycle de ECR conserva 100 imagenes (en desarrollo, DEVELOPING)

- Título: Lifecycle de ECR compatible con rollback: conservar 100 imágenes.
- Clase C (infraestructura): sin fast path; tras el merge la transición obligatoria es `merged_non_fast_path`
  hacia `BLOCKED_HUMAN` y el humano aplica la política en AWS DEV.
- Riesgo documentado desde 2026-09-14: la política anterior (`imageCountMoreThan: 20`) podía expirar imágenes
  requeridas por el LKG. Decisión del humano (2026-10-19): elevar el tope a 100; la aplicación la ejecuta el
  humano (el Harness no la aplica: `ecr put-lifecycle-policy` está denegado a los agentes).
- Cambios:
  - `deployment/ecr/lifecycle-policy.json`: regla 1 sin cambios (capas sin etiqueta a los 7 días); regla 2 pasa
    de `imageCountMoreThan: 20` a `imageCountMoreThan: 100` (`tagStatus: any`, acción `expire`). Un único archivo
    sirve a `tpi-dev-app` y `tpi-dev-caddy`.
  - Nuevo `tests/unit/test_ecr_lifecycle_policy.py` (sin AWS, corre en CI): falla si no hay reglas, hay prioridades
    repetidas, una regla expira por antigüedad imágenes con etiqueta o el conteo de retención baja de 100.
  - Nuevo `docs/ECR_LIFECYCLE_POLICY.md`: por qué 100, procedimiento de aplicación y verificación
    (put/get-lifecycle-policy y vista previa start/get-lifecycle-policy-preview) para `tpi-dev-app` y
    `tpi-dev-caddy`, reversa (reaplicar el JSON anterior desde git) y constancia de que las comprobaciones de
    digests del LKG en el preflight y en la revisión del candidato se mantienen. Lista las notas `keep-20` en
    `agents/` (rutas protegidas) para actualizarlas aparte.
  - `docs/INDEX.md` y `CHANGELOG.md` actualizados.
- Impacto y rollback: conserva más imágenes, no menos; costo residual de almacenamiento marginal. Reversa:
  reaplicar el JSON anterior desde git (documentado en `docs/ECR_LIFECYCLE_POLICY.md`).
- No se tocan `app/**`, `.github/**`, `Dockerfile`, `deployment/` fuera de `deployment/ecr/`, `environments/**`,
  `agents/**`, `harness/**` ni `scripts/harness/**`.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-EVIDENCIA-ENTRADAS cerrada (DONE)

- Titulo: Simulador: guardar entradas y resultado como evidencia (solo escritura)
- Evidencia: `evidence/SIM-EVIDENCIA-ENTRADAS/` y `tasks/completed/SIM-EVIDENCIA-ENTRADAS.yaml`.
- release_sha: `a7859af73491a050b8c327cf21a0004acf995ae0`
- pr_number: `83`
- application_version: `h3-sim-evidencia-entradas-a7859af-domainlocked-r1`
- bundle_sha256: `0a495da76209e6becde56b5036732a162a69238f68d26fd61a4d94fe8b18d9f2`
- lkg: `h3-sim-rv-v1-ventana-5024922-domainlocked-r1`
- deployment: `success`
- deployed_commit: `a7859af73491a050b8c327cf21a0004acf995ae0`
- verification: `PASS`

### 2026-10-16 - SIM-EVIDENCIA-ENTRADAS: guardar entradas y resultado como evidencia (en desarrollo, DEVELOPING)

- Titulo: Simulador: guardar entradas y resultado como evidencia (solo escritura).
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Decision del humano (2026-10-15): reemplaza el AC-10 de `SIM-RV-V1` («no se persiste ninguna entrada ni resultado»). Las
  entradas y el resultado de cada simulacion se guardan como evidencia append-only de solo escritura en
  `tpi.auditoria.detalle`, sin nombres, RUT, correo ni telefono. La politica de retencion queda pendiente de decision del
  humano y mostrarla en la linea de tiempo es `SIM-HISTORIAL-LINEA-TIEMPO`.
- Cambios:
  - `app/services/simulador_auditoria.py`: el `detalle` pasa a ser versionado (`schema_version`) y `record_simulacion_event`
    recibe las entradas (causante, saldo, tasa, garantia, aumento, diferimiento, relacion RVD/RT, valor UF y beneficiarios) y
    el resultado (pension y, en renta temporal, renta temporal y meses de diferimiento); se agrega `build_detalle` puro.
  - `app/services/simulador_service.py` y `app/web/routes/simulador.py`: el evento se registra con las entradas y el resultado
    reales de la simulacion, conservando el fail-closed (si el INSERT falla no se entrega el PDF).
  - `tests/unit/test_sim_rv_auditoria.py` y `tests/unit/test_sim_rv_web.py` ajustados; nuevo
    `tests/unit/test_sim_rv_evidencia_entradas.py` (estructura versionada, sin PII y reproducibilidad del resultado y del
    codigo); `tests/integration/test_sim_rv_web.py` verifica el detalle sin PII (nombre con marcado y caracteres especiales)
    y la reproducibilidad desde PostgreSQL.
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (AC-10 y AC-11), `docs/SIM_RV_V1_PENDIENTES.md` (#6) y `docs/SIM_RV_V1_MODELO.md`
    reflejan la decision del humano; `CHANGELOG.md` actualizado.
- No cambia el motor `app/simulador_pension/**`, la logica numerica, los rangos validados, la autorizacion ni el escape de
  marcado del PDF; no se toca `app/repositories/**`.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-RV-V1-VENTANA cerrada (DONE)

- Titulo: Simulador RV: ventana de validacion abierta, con aviso de valores referenciales
- Evidencia: `evidence/SIM-RV-V1-VENTANA/` y `tasks/completed/SIM-RV-V1-VENTANA.yaml`.
- release_sha: `502492257e505884716d14c2529dd0d08bcb421d`
- pr_number: `81`
- application_version: `h3-sim-rv-v1-ventana-5024922-domainlocked-r1`
- bundle_sha256: `c1fd91f28df57caf85978d23540a620e1b7d8557195ebe46a7be631dc09280db`
- lkg: `h3-sim-ficha-pdf-dd6be12-domainlocked-r1`
- deployment: `success`
- deployed_commit: `502492257e505884716d14c2529dd0d08bcb421d`
- verification: `PASS`

### 2026-10-16 - SIM-RV-V1-VENTANA: ventana de validacion abierta con aviso de valores referenciales (en desarrollo, DEVELOPING)

- Titulo: Simulador RV: ventana de validacion abierta, con aviso de valores referenciales.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Decision del humano (2026-10-14): la ventana validada del simulador queda abierta; ya no bloquea ni advierte por fecha y solo se
  mantiene el aviso de que los valores son referenciales (no vinculantes).
- Cambios:
  - `app/services/simulador_service.py`: se eliminan `clasificar_ventana` y `VENTANA_ADVERTENCIA_DIAS`; `generar_pdf` pierde el
    parametro `advertencia_ventana` y su parrafo, y en la leyenda se agrega la seccion «Supuestos y advertencias» con el aviso
    permanente de valores referenciales (no vinculantes).
  - `app/web/routes/simulador.py`: se eliminan las lineas que usaban `clasificar_ventana` y el 422 por vencimiento de la ventana;
    el contexto del formulario ya no expone `advertencia_ventana`.
  - `app/web/templates/simulador.html`: el bloque condicional de aviso de ventana vencida se reemplaza por un aviso permanente de
    valores referenciales (no vinculantes).
  - `tests/unit/test_sim_rv_ventana.py` reemplazado por pruebas de que cualquier fecha genera y de que el aviso referencial esta en
    el PDF; `tests/unit/test_sim_rv_web.py` y `tests/unit/test_sim_rv_pdf.py` ajustados al nuevo contrato.
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (AC-6 y matriz de contenido del PDF), `docs/SIM_RV_V1_PENDIENTES.md` (§1 y #1) y
    `docs/SIM_RV_V1_MODELO.md` (§5) reflejan la decision del humano; `CHANGELOG.md` actualizado.
- No cambia el motor `app/simulador_pension/**` (conserva `VENTANA_VALIDADA` y su `warnings.warn` informativo) ni el alcance
  validado de la V1 (435/435 casos dentro de ±1 UF, rangos por escenario, autorizacion, CSRF, escape de marcado, headers del PDF
  y auditoria sin PII).
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-FICHA-PDF cerrada (DONE)

- Titulo: Simulador: ficha PDF con el formato 'Estudio de pension' de TPI
- Evidencia: `evidence/SIM-FICHA-PDF/` y `tasks/completed/SIM-FICHA-PDF.yaml`.
- release_sha: `dd6be124595426e6646b94d5b19c19a864e2c5a8`
- pr_number: `79`
- application_version: `h3-sim-ficha-pdf-dd6be12-domainlocked-r1`
- bundle_sha256: `de97beb63b279bc07ae4d154e1054a1b99409c597c6acc413939e01a40bb6c9e`
- lkg: `h3-sim-ux-ajustes-1f50505-domainlocked-r1`
- deployment: `success`
- deployed_commit: `dd6be124595426e6646b94d5b19c19a864e2c5a8`
- verification: `PASS`

### 2026-10-16 - SIM-FICHA-PDF: ficha PDF «Estudio de pensión» (en desarrollo, DEVELOPING)

- Titulo: Simulador: ficha PDF con el formato «Estudio de pensión» de TPI.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Diseño fuente de verdad: `docs/specs/SIM_FICHA_PDF_SPEC.md` (la ficha de ejemplo no se copia ni se usa en pruebas por contener datos de una persona real).
- Cambios:
  - `app/services/simulador_service.py`: `generar_pdf` pasa de A4 a carta apaisada (792×612 pt) con el formato de la ficha «Estudio de pensión»: banda superior azul marino `#0f243e` (tratamiento + nombre, título «ESTUDIO DE PENSIÓN» y fecha), fila de datos (fecha de nacimiento, cónyuge, tasa de venta y valor UF destacado), tablas «OPCIÓN I» (Renta Vitalicia Inmediata + Rescate Total) y «OPCIÓN II» (Aumento Temporal de Pensión + Inflación Futura 4% + Rescate Total) cuando hay aumento temporal, pie de contacto corporativo en texto plano y banda inferior con `official-logo-on-dark.png`. Se agregan los cálculos derivados (`_rescate_opcion_i`, `_valor_actual`, `_valor_futuro`, `_rescate_opcion_ii`, `_pension_aumentada`) y el formato es-CL (`_uf`, `_clp`).
  - `app/web/routes/simulador.py`: `generar_pdf` ahora recibe `sexo_causante`, `causante_nacimiento`, `tiene_conyuge`, `saldo_uf`, meses de garantía/aumento, porcentaje de aumento y años diferidos; se eliminan `_parametros_pdf` y el cálculo de `edad_causante` (ya no se usan).
  - `tests/unit/test_sim_rv_pdf.py`: estructura de la ficha (AC-1), cálculos derivados con datos sintéticos (AC-2), pie y contacto sin PII (AC-3) y conservación de SIM-RV-V1 (AC-4).
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (matriz de contenido del PDF) y `docs/SIM_RV_V1_PENDIENTES.md` (fuera de alcance §5) actualizados.
- Se conservan de SIM-RV-V1: leyenda «Estimación referencial no vinculante», versión del modelo, código de verificación, escape de marcado, metadatos genéricos sin PII y ausencia de RUT, correo y teléfono del lead; la renta temporal con RVD conserva su sección con la nueva apariencia.
- Fuera de alcance documentado (no se inventa): fila «RP (AFP)», bloque «PGU / BAC / TOTAL», comparativa de varias opciones, teléfono personal del ejecutivo, estado civil y renta temporal con RVD (ver `docs/SIM_RV_V1_PENDIENTES.md` §5).
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-UX-AJUSTES cerrada (DONE)

- Titulo: CRM y simulador: aviso de edad en pantalla, navegacion y nombre sin 'Lite'
- Evidencia: `evidence/SIM-UX-AJUSTES/` y `tasks/completed/SIM-UX-AJUSTES.yaml`.
- release_sha: `1f5050537e44d631c685dd78e7277932284c81fa`
- pr_number: `75`
- application_version: `h3-sim-ux-ajustes-1f50505-domainlocked-r1`
- bundle_sha256: `82cfe13688bdad7614501b93c3bdc7d10693eee920b4788da22795e2c46da555`
- lkg: `h3-sim-rv-v1-1308441-domainlocked-r1`
- deployment: `success`
- deployed_commit: `1f5050537e44d631c685dd78e7277932284c81fa`
- verification: `PASS`

### 2026-10-15 - SIM-UX-AJUSTES: aviso de edad en pantalla, navegacion y nombre sin 'Lite' (en desarrollo, DEVELOPING)

- Titulo: CRM y simulador: aviso de edad en pantalla, navegacion y nombre sin 'Lite'.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Cambios:
  - `app/web/routes/simulador.py`: los POST del simulador ya no responden `PlainTextResponse` 422; ahora
    re-renderizan `simulador.html` en la misma pantalla con un aviso arriba (`simulador_errores`) y los valores
    ingresados (`form_values`), conservando HTTP 422 y los flujos 403/404/CSRF/anónimo.
  - `app/web/templates/simulador.html`: aviso de errores y re-poblado de los campos del formulario.
  - `app/web/templates/lead_detail_panel.html`: se elimina el bloque `lead-hero-actions` con el botón antiguo
    «Abrir simulación»; queda solo el panel nuevo «Abrir simulador» (executive/ceo/cto).
  - `app/web/templates/base.html`: «Volver al sitio» → «Home» y «Salir» → «Cerrar sesión».
  - «CRM Lite» → «CRM» en todo texto visible (títulos, cabecera, insignia, kickers, login y app Streamlit) y en
    las pruebas que lo afirmaban; no se renombran rutas, módulos, archivos de prueba ni identificadores, y no se
    reescribe la documentación histórica.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-14 - Harness: tarea SIM-RV-V1 cerrada (DONE)

- Titulo: Simulador de renta vitalicia en el CRM con PDF efimero (perfil ejecutivo), V1 solo validado
- Evidencia: `evidence/SIM-RV-V1/` y `tasks/completed/SIM-RV-V1.yaml`.
- release_sha: `13084414558f59a7b1e30dd859199469c2a62318`
- pr_number: `69`
- application_version: `h3-sim-rv-v1-1308441-domainlocked-r1`
- bundle_sha256: `b91612eacdd0698661ceca28247199d6dd4254c1a675fbae6af969daa5431895`
- lkg: `h3-logo-png-cb628dc-domainlocked-r1`
- deployment: `success`
- deployed_commit: `13084414558f59a7b1e30dd859199469c2a62318`
- verification: `PASS`

### 2026-10-14 - SIM-RV-V1: simulador de renta vitalicia (en desarrollo, DEVELOPING)

- Titulo: Simulador de renta vitalicia en el CRM con PDF efimero (perfil ejecutivo), V1 solo validado.
- Motor puro portado a `app/simulador_pension` (sin cambios en la logica numerica); orquestacion en
  `app/services/simulador_service.py` (PDF efimero, codigo de verificacion, clasificacion de escenario y ventana).
- Decision de alcance (AC-11): el guard del Harness no permite editar `app/repositories/**` en esta tarea, asi
  que el escritor del evento de auditoria vive en un modulo NUEVO `app/services/simulador_auditoria.py`, que usa
  `get_db_connection` de `app.database.connection` con el mismo patron de INSERT append-only de
  `record_xlsx_export_event` (`tpi.auditoria`, `accion='simulacion_renta_vitalicia'`, `tabla_afectada='tpi.leads'`,
  `detalle` JSON sin PII). Se aparta de la convencion de capas; mover a `app/repositories/` en una tarea posterior
  con ese alcance (ver `docs/SIM_RV_V1_PENDIENTES.md` item 15).
- Siguiente paso: completar rutas web, plantillas, pruebas, gates de calidad y `submit_for_review`.
### 2026-10-14 - Harness: tarea TASK-002 cerrada (DONE)

- Titulo: Aplicar logo oficial PNG en CRM Lite (variante clara y oscura)
- Evidencia: `evidence/TASK-002/` y `tasks/completed/TASK-002.yaml`.
- release_sha: `cb628dcb7550bed4bd7a5912c22595f650cc53c9`
- pr_number: `68`
- application_version: `h3-logo-png-cb628dc-domainlocked-r1`
- bundle_sha256: `22f4f98440bdb822918797a6924ce3b600fd4f246b379880aab72a04a04b32c0`
- lkg: `h3-logo-zlib-04e3f1a-domainlocked-r1`
- deployment: `success`
- deployed_commit: `cb628dcb7550bed4bd7a5912c22595f650cc53c9`
- verification: `PASS`

### 2026-10-13 - Harness: tarea TASK-001 cancelada

- Titulo: Desplegar logo oficial de CRM Lite a DEV (release)
- Evidencia: `evidence/TASK-001/` y `tasks/completed/TASK-001.yaml`.
- release_sha: `04e3f1a80aa0c609aef8a0724419f5f21f299c8f`
- pr_number: `66`
- application_version: `h3-logo-zlib-04e3f1a-domainlocked-r1`
- bundle_sha256: `7026a0791cf7ab5c1c0a22cf9021b656b2f98c1a7a93fc568efba34ca8336a76`
- lkg: `h3-3-7-tema-claro-oscuro-6f0f5bb-domainlocked-r1`
- deployment: `success`
- deployed_commit: `04e3f1a80aa0c609aef8a0724419f5f21f299c8f`
- verification: `FAIL`

### 2026-10-12 - Harness: tarea CRM-LITE-OFFICIAL-LOGO cancelada

- Titulo: Reemplazar logo temporal de CRM Lite por logo oficial
- Evidencia: `evidence/CRM-LITE-OFFICIAL-LOGO/` y `tasks/completed/CRM-LITE-OFFICIAL-LOGO.yaml`.
- release_sha: `6a5acd4d23d623c14b67158dd0ef202f1cbfa431`
- pr_number: `64`

### 2026-10-01 - Harness: tarea H3.3.7 cerrada (DONE)

- Titulo: Tema claro y oscuro para CRM Lite
- Evidencia: `evidence/H3.3.7/` y `tasks/completed/H3.3.7.yaml`.
- release_sha: `6f0f5bb1e934742cd8e8572d4a401f8bf29ab1c7`
- pr_number: `60`
- application_version: `h3-3-7-tema-claro-oscuro-6f0f5bb-domainlocked-r1`
- bundle_sha256: `efa590b9e0daef786ce1f4b69ea8026c1a160b39d8dac06999d1c79b7f82d8aa`
- lkg: `h3-3-6-xlsx-export-5f5b3d3-domainlocked-r1`
- deployment: `success`
- deployed_commit: `6f0f5bb1e934742cd8e8572d4a401f8bf29ab1c7`
- verification: `PASS`

### 2026-09-23 - Harness: tarea H3.3.6 cerrada (DONE)

- Titulo: Exportacion ejecutiva XLSX segura
- Evidencia: `evidence/H3.3.6/` y `tasks/completed/H3.3.6.yaml`.
- release_sha: `5f5b3d37bf122f1d4438583b973fd03763aecebe`
- pr_number: `58`
- application_version: `h3-3-6-xlsx-export-5f5b3d3-domainlocked-r1`
- bundle_sha256: `8fbd2526a6e311bdcfb0c2f72cdd20a7ba9f6a056de04562957214946332cb32`
- lkg: `h3-3-5-asesores-cartera-78bf33b-domainlocked-r1`
- deployment: `success`
- deployed_commit: `5f5b3d37bf122f1d4438583b973fd03763aecebe`
- verification: `PASS`

### 2026-09-22 - Harness: tarea H3.3.5 cerrada (DONE)

- Titulo: Asesores DEV y cartera propia
- Evidencia: `evidence/H3.3.5/` y `tasks/completed/H3.3.5.yaml`.
- release_sha: `78bf33bcb946fc442a8e5488cdf0d2f89fd190c2`
- pr_number: `57`
- application_version: `h3-3-5-asesores-cartera-78bf33b-domainlocked-r1`
- bundle_sha256: `f7e661411bbaacaf456a95405fd0e787136ac6cb04eb790fd78039d7938731f1`
- lkg: `h3-3-4-historial-dashboard-3051a62-domainlocked-r1`
- deployment: `success`
- deployed_commit: `78bf33bcb946fc442a8e5488cdf0d2f89fd190c2`
- verification: `PASS`

### 2026-09-21 - Harness: tarea H3.3.4 cerrada (DONE)

- Titulo: Historial integral de estados y Dashboard Ejecutivo CRM
- Evidencia: `evidence/H3.3.4/` y `tasks/completed/H3.3.4.yaml`.
- release_sha: `3051a6271e1626b40fe24a744abe097cab1ab0fe`
- pr_number: `56`
- application_version: `h3-3-4-historial-dashboard-3051a62-domainlocked-r1`
- bundle_sha256: `bcbe935885dc50d279cd19c5f0ddf696449b29d7305c2e5506dc0a5afa9916d0`
- lkg: `h3-3-3-historial-web-ux-c5e738c-domainlocked-r1`
- deployment: `success`
- deployed_commit: `3051a6271e1626b40fe24a744abe097cab1ab0fe`
- verification: `PASS`

### 2026-09-17 - Harness: tarea H3.3.3 cerrada (DONE)

- Titulo: Historial operativo y navegacion Web UX
- Evidencia: `evidence/H3.3.3/` y `tasks/completed/H3.3.3.yaml`.
- release_sha: `c5e738c21ba202d9c664652412e6820628b18e3c`
- pr_number: `54`
- application_version: `h3-3-3-historial-web-ux-c5e738c-domainlocked-r1`
- bundle_sha256: `6b6450b53df7e54a1d80ab637819d2f7dbc059e9435cd59221b549cfda949695`
- lkg: `h3-3-2-superusuarios-ceo-cto-fec33e7-domainlocked-r1`
- deployment: `success`
- deployed_commit: `c5e738c21ba202d9c664652412e6820628b18e3c`
- verification: `PASS`

### 2026-09-16 - Harness: tarea H3.3.2 cerrada (DONE)

- Titulo: Modelo de superusuarios CEO/CTO e identidades DEV
- Evidencia: `evidence/H3.3.2/` y `tasks/completed/H3.3.2.yaml`.
- release_sha: `fec33e7951f862c95b2436b09b969e5ef1915769`
- pr_number: `53`
- application_version: `h3-3-2-superusuarios-ceo-cto-fec33e7-domainlocked-r1`
- bundle_sha256: `ddc5abe2047b624b5a5a1a8aa0615048b54291077bd0d1ffaff7c4fc9e273800`
- lkg: `h3-3-1-rbac-pii-4aac143-domainlocked-r1`
- deployment: `success`
- deployed_commit: `fec33e7951f862c95b2436b09b969e5ef1915769`
- verification: `PASS`

### 2026-09-16 - Harness: tarea H3.3.1 cerrada (DONE)

- Titulo: Completar RBAC/PII y asignacion manual en DEV
- Evidencia: `evidence/H3.3.1/` y `tasks/completed/H3.3.1.yaml`.
- release_sha: `4aac143a396934186342bab5ec97b3df5e53085c`
- pr_number: `52`
- application_version: `h3-3-1-rbac-pii-4aac143-domainlocked-r1`
- bundle_sha256: `e49628affe9279b80764a12ec5b724f60e5b89eb5b8c72bb6d519c9a99e8f72c`
- lkg: `h3-3-crm-web-43101be-domainlocked-r1`
- deployment: `success`
- deployed_commit: `4aac143a396934186342bab5ec97b3df5e53085c`
- verification: `PASS`

### 2026-09-12 - Cierre H3.3 (CLOSED WITH DEFERRED ACCEPTANCE ITEMS) y handoff

Entrada de referencia operativa vigente. Las entradas anteriores de H3.3 y los
hostnames/hashes historicos quedan como HISTORICO; esta entrada manda.

#### Punto exacto del desarrollo

- H3.3 funcional cerrado con excepciones aceptadas por el owner:
  `CLOSED WITH DEFERRED ACCEPTANCE ITEMS`.
- PR funcional #14 mergeado por squash. Merge SHA
  `89a1c58643fc228024243d474c47986ab272257f`.
- Candidate validado/desplegado: `43101be7835088f93267bee85b0f11c8bc879867`.
- Main CI de cierre: run `34701799998` -> success.
- Issue de seguimiento: #50 `H3.3.1 — completar RBAC/PII y asignacion manual en DEV`.

#### Runtime AWS DEV vigente (estado observado, no intencion)

- Account `821656895812`, region `us-east-2`.
- EB environment `tpi-backoffice-dev-green`, application `tpi-backoffice`.
- VersionLabel: `h3-3-crm-web-43101be-domainlocked-r1`.
- Estado: Ready / Green / Ok.
- Publico: https://dev.tupensioninteligente.cl -> HTTPS/TLS OK.
- Backoffice: https://backoffice.dev.tupensioninteligente.cl -> HTTPS/TLS OK, login operativo.
- API `/api/v1/catalogs` -> 200 (conectividad DB confirmada).
- Sin redirect a genialabs.cl.
- CNAME EB: `tpi-backoffice-dev-ecr.us-east-2.elasticbeanstalk.com`.

#### Release domain-locked (fast path version-only)

- PR #49 merge SHA `e4f63f1ba525df78ddebc8c724838978ed1f65c4`.
- Bundle SHA256 `007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f`.
- Bucket `elasticbeanstalk-us-east-2-821656895812`, key
  `tpi-backoffice/dev-releases/h3-3-crm-web-43101be-domainlocked-r1/007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f.zip`.
- El compose lleva las 4 variables TPI literales (tupensioninteligente.cl +
  zona `Z07053592LX0W8GJXNI1C`); app/caddy fijados por digest (43101be).
- Cutover: `aws elasticbeanstalk update-environment --version-label
  h3-3-crm-web-43101be-domainlocked-r1` SIN `--option-settings`.

#### Fast path DEV (lo que SÍ funciono y pasa a ser el camino de aplicacion)

1. candidate inmutable (imagenes por digest);
2. bundle determinista y verificable por SHA256;
3. Application Version nueva;
4. `update-environment --version-label <target>` (sin option settings, sin IAM/Route53/red/DB);
5. esperar Ready / Green / Ok;
6. smoke funcional inmediato;
7. rollback = `update-environment --version-label <VersionLabel conocida>`.

Para releases de aplicacion, NO modificar option settings, IAM, Route53, red ni
DB en el mismo cutover. Ver `TPI_Contrato_CICD_AWS_v2.md`.

#### Camino que NO debe repetirse (leccion registrada)

La promocion con UpdateEnvironment + option settings (cambio de configuracion)
disparo dependencias caller-side sucesivas y costosas:

- `ec2:DescribeSubnets` -> `ec2:DescribeSecurityGroups` -> `ec2:DescribeVpcs` ->
  `ec2:DescribeImages`;
- luego S3/CloudFormation: `Service:AmazonCloudFormation, Message:S3 error: Access Denied`;
- la accion Commands de CodePipeline mostro expiracion/autorizacion de token al esperar demasiado.

Leccion: NO desarrollar IAM por ciclo `AccessDenied -> agregar permiso -> retry`.
Los cambios de infraestructura requieren contrato completo, service roles/IaC y
una ruta separada del deploy de aplicacion.

#### CodePipeline / H3.2

- Promote queda disabled.
- El pipeline actual no es el camino obligatorio hasta industrializarlo en H3.2.
- No borrar el trabajo: es evidencia/base, pero requiere rediseño para separar
  promocion de aplicacion de cambios de infraestructura.

#### Rollback / artefactos a preservar (no borrar/recrear)

- `h3-3-crm-web-28cf009-r1` (runtime legacy pre-cutover; rollback version-only).
- `h3-3-domain-baseline-28cf009-caddy43101be-r1` (AV de fase-1, UNPROCESSED).
- `h3-3-crm-web-43101be-domainlocked-r1` (runtime vigente).
- No reutilizar nombres de Application Version.

#### Base de datos

- Migraciones 005 y 006 ya aplicadas y verificadas en DEV. NO reejecutar.
- Relacion operacional en `tpi.asignaciones` (`raw_payload` NO es fuente).
- Auditoria funcional en `tpi.auditoria`.

#### Deuda funcional H3.3.1 (issue #50) — pendiente funcional, no infraestructura

- CEO/CTO aun ve PII ofuscada en DEV.
- El control de asignacion manual no aparece en la UI observada.
- Diferido: smoke end-to-end de asignacion y validacion read-only de
  `tpi.leads` / `tpi.asignaciones` / `tpi.auditoria`.
- Confirmar una sola asignacion activa por lead y actor auditado.
- Al retomarlo: diagnosticar primero autorizacion/roles y renderizado de la
  accion en aplicacion. No tocar AWS/IAM/deploy salvo evidencia nueva.

#### Orden recomendado para el siguiente equipo

1. Leer esta entrada + `TPI_Contrato_CICD_AWS_v2.md`.
2. Resolver #50 H3.3.1 como cambio funcional aislado.
3. Desplegar fixes H3.3.1 por fast path version-only.
4. Smoke autenticado inmediato tras runtime green.
5. Validar DB con identidad read-only, sin exponer passwords.
6. Reanudar H3.2 solo despues: automatizar version-only + IaC/service roles.
7. Antes de PROD cerrar: IaC del control plane, service roles explicitos, smoke
   automatizado con usuario sintetico, identidad DB read-only de inspeccion,
   politica de rollback/retencion, observabilidad y evidencia por release.

#### Principios a conservar

- Seguridad server-side (PII/RBAC).
- Minimo privilegio y separacion de responsabilidades.
- Releases inmutables y reproducibles.
- Trazabilidad mecanica commit -> digest -> bundle -> Application Version -> runtime.
- Rollback explicito y probado.
- Tests unitarios, integracion, seguridad y smoke funcional.
- Ningun secreto en Git, logs o bitacora.
- Ningun cambio de infraestructura improvisado durante un release funcional.
- Diseñar DEV -> QA -> PROD sin copiar excepciones ad hoc.
- Documentar siempre estado observado, no solo intencion.

### 2026-09-11 - Remediacion minima de supply-chain de la imagen app

- El tag oficial inmutable `python:3.12.14-alpine3.24` continua resolviendo al
  digest `sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a`.
- El scan ECR del candidate no elegible atribuyo el finding a la fuente
  `util-linux 2.42.1-r0`. La inspeccion del APK DB de la base confirma que el
  unico APK instalado con ese origen es `libuuid 2.42.1-r0`; el indice oficial
  Alpine 3.24 publica `libuuid 2.42.3-r1` del mismo origen.
- Se conserva la base fijada y se actualiza exclusivamente `libuuid` con una
  version explicita. No se usa `apk upgrade` global ni se modifican dependencias
  Python, funcionalidad H3.3 ni recursos AWS.
- CI compara el inventario APK de la base y la app, exige que el unico delta sea
  `libuuid 2.42.1-r0 -> 2.42.3-r1`, conserva Python 3.12.14 y valida el
  arranque/readiness del contenedor contra PostgreSQL efimero.

### 2026-09-10 - Preparacion del cierre TLS/domain contract de H3.3

Contexto:

- La promocion H3.3 anterior termino saludable sobre
  `h3-3-crm-web-28cf009-r1`, que permanece inmutable.
- AWS Agent Toolkit confirmo en la cuenta `821656895812` que la hosted zone
  publica delegada es `dev.tupensioninteligente.cl.` con ID
  `Z07053592LX0W8GJXNI1C`; no existe una hosted zone apex TPI en la cuenta.
- El environment conservaba las direcciones historicas `genialabs.cl` y la
  policy fisica ACME ya apuntaba a la zona TPI, pero autorizaba solo el TXT del
  hostname publico.

Cambios preparados:

- Caddy obtiene el hosted zone ID desde `TPI_ROUTE53_HOSTED_ZONE_ID`.
- El Compose AWS exige las cuatro variables no secretas del contrato DEV.
- La policy Route 53 versionada limita cambios a TXT sobre los challenges
  publico y backoffice en la zona delegada TPI.
- El preflight independiente y el de promocion comparan los cuatro valores
  exactos sin imprimir el resto del environment.
- Se actualizaron los allowlists runtime del sitio publico y del backoffice y
  se agregaron pruebas de regresion.

Pendiente:

- CI, candidate inmutable nuevo, aplicacion/verificacion de la policy fisica,
  cutover controlado, promocion unica, TLS/smoke H3.3 y cierre de PR `#14`.
- Antes de mutar AWS debe resolverse mecanicamente el orden atomico entre el
  preflight exacto y el cambio de VersionLabel/configuracion, sin arrancar una
  revision de Caddy con dominio y hosted zone incompatibles.

### 2026-08-25 - Registro historico de cutover DEV

> Registro historico: los hostnames, version labels y permisos descritos a
> continuacion no representan el contrato runtime DEV vigente.

Contexto:

- Se habilito el nuevo dominio DEV oficial `https://dev.tupensioninteligente.cl`.
- El objetivo fue dejar HTTPS valido, mantener rollback y preservar `dev.genialabs.cl` como respaldo temporal.

Resumen tecnico cronologico:

- Se verifico primero la resolucion DNS y el flujo HTTP hacia el environment AWS DEV.
- El handshake HTTPS inicial fallo, por lo que se descarto un problema basico de DNS o conectividad.
- Se confirmo por logs de Caddy que el hostname nuevo llegaba a la config activa y que Caddy intentaba ACME DNS-01.
- La primera causa raiz identificada fue IAM insuficiente para Route 53.
- La segunda causa raiz fue un `hosted_zone_id` hardcodeado en `deployment/caddy/Caddyfile` que estaba compartido entre dominios y apuntaba a la zona de `dev.genialabs.cl`.
- Se separo la configuracion DNS-01 por hosted zone:
  - `dev.genialabs.cl` -> `Z0562050FYDQE12LRGMA`
  - `dev.tupensioninteligente.cl` -> `Z07053592LX0W8GJXNI1C`
- Se valido el runtime real de Caddy dentro de `tpi-backoffice-dev-green` y luego se desplego una nueva version reproducible.
- Se realizo cutover DNS controlado del alias publico para `dev.tupensioninteligente.cl` hacia `tpi-backoffice-dev-green`.
- Se confirmo TLS valido, smoke read-only y preservacion del dominio legado como respaldo temporal.

Evidencia de release:

- Commit: `47fa0c92e2fb9fc916309ac219410fffb08f7cbc`
- VersionLabel: `h2-5d-ecr-47fa0c9`
- Bundle: `s3://elasticbeanstalk-us-east-2-821656895812/deployments/h2-5d-ecr-47fa0c9.zip`
- SHA256: `e62d039cdfe4e11e1c6fc1aacf13cb6182ba2480217ca5e395eaa520e2621cb7`

Siguiente paso:

- Mantener observacion de estabilidad del nuevo dominio.
- No retirar todavia `dev.genialabs.cl` hasta que el corte de operacion quede formalmente cerrado.
- Consolidar los aprendizajes en la documentacion de despliegue reproducible.

### 2026-08-25 - Registro historico de cierre H3.3 CRM Lite Web UX

Contexto:

- H3.3 quedo validado funcionalmente en AWS DEV como CRM Lite Web UX.
- La validacion manual del producto sobre `https://backoffice.dev.genialabs.cl` fue satisfactoria.

Datos de cierre:

- Hito: `H3.3 — CRM Lite Web UX`
- Status: `CLOSED`
- Human UX Acceptance: `PASS`
- Git SHA: `1574d79920342d3da2bac8296de9020b8162c68f`
- App digest: `sha256:1f5bca0350e3f3229516643b1f1f5dcf05f6f13e826c6a444aa8640302b73922`
- EB Version: `h3-3-crm-web-1574d79-r1`
- URL: `https://backoffice.dev.genialabs.cl`

Siguiente paso:

- No realizar mas cambios funcionales ni de infraestructura sobre este hito.
- Si se requiere ajustar documentacion historica adicional, hacerlo en una PR exclusivamente documental.

Referencia canonica:

- [docs/H3_3_CRM_LITE_WEB_UX.md](H3_3_CRM_LITE_WEB_UX.md)
- [docs/PROJECT_STATUS.md](PROJECT_STATUS.md)
- [docs/DECISIONES_TECNICAS.md](DECISIONES_TECNICAS.md)

### 2026-08-22 - H3.1 CRM Lite cerrado formalmente

Contexto:

- H3.1 quedo validado funcional y tecnicamente sobre `feat/h3-1-crm-lite`.
- El cierre Git fue completado con `main` en `ad22d37048176aa80ab139f56c3ef6903f6e430e` y el runtime productivo ya habia sido verificado previamente desde `d9bc2670bca87a71130d8e7088b56dd7976b82f5`.

Datos de cierre:

- PR: `#8`
- Final PR HEAD: `58a11fdcd0b1a9b1bca6679ebe463e0964659c7f`
- Merged main: `ad22d37048176aa80ab139f56c3ef6903f6e430e`
- CI final: `#58`
- Lint: PASS
- Tests: PASS
- Security: PASS
- Docker: PASS
- Productive runtime validated from: `d9bc2670bca87a71130d8e7088b56dd7976b82f5`
- App digest: `sha256:e70d799ed6b5da252a7f90bc412b8a75ba37082377f3e3bc46ca7025571ca01b`
- AWS DEV: validated
- Database structural changes: none

Pendientes movidos a H3.2:

- reproducible deployment chain
- CI post-merge observability
- runtime verification automation
- cleanup log observability

Siguiente paso:

- Reanudar H3.2 desde el contrato de release y la documentacion ya aprobada, sin descartar ningun trabajo realizado.

### 2026-08-17 - H2.5C local demo preparation

Contexto:

- AWS account-plan work is blocked externally. A complete local rehearsal is
  required without AWS, RDS, SNS, Secrets Manager or HTTPS.

Tareas realizadas:

- Added `docker-compose.local.yml` with local PostgreSQL and the existing
  idempotent schema initializer, while keeping the AWS-oriented Compose file
  free of a database service.
- Parameterized Caddy site addresses and upstreams. The local defaults are
  loopback-only HTTP `tpi.localhost` and `backoffice.tpi.localhost`; future AWS
  deployment must set public domain addresses explicitly.
- Documented an untracked Argon2id local user, fake local HMAC, disabled SNS,
  lifecycle commands and the manual Caddy fallback.

Seguridad:

- `AUTH_USERS_JSON` is supplied only to backoffice from `.env.local`.
- H2.3 cleanup remains impossible in local mode; reset the local volume instead.
- No AWS resource, secret or network configuration was changed.

### 2026-08-17 - H2.5C idempotency hardening pending local validation

Contexto:

- The public API remains local only. No AWS, DNS, IAM, Secrets Manager, RDS or
  deployment change is authorized or executed.

Tareas realizadas:

- Renamed the idempotency HMAC configuration to the dedicated
  `API_IDEMPOTENCY_HMAC_SECRET` contract. Public API startup fails closed when
  it is absent and it is explicitly separate from database and auth secrets.
- Confirmed the PostgreSQL algorithm reserves `idempotency_key` with its primary
  key plus `INSERT ... ON CONFLICT` in the same transaction as lead creation.
  A PostgreSQL concurrency test covers two simultaneous equal requests.
- Updated the short-lived lead FK to `ON DELETE SET NULL` so the approved DEV
  cleanup path is not blocked. The migration grants only the required table
  privileges to `tpi_app`; `scripts/sql/003_drop_api_idempotency.sql` is the
  documented reversal after disabling the public API.

Pendiente:

- Complete quality gates in an environment with normal temporary, Docker and
  Git permissions before any commit or push.

### 2026-08-16 - H2.5C public static frontend and HTTP API (local only)

Contexto:

- H2.5C replaces the cloned frontend lead transport through WhatsApp with a
  same-origin, versioned HTTP API. No AWS, DNS, billing, IAM, secret, security
  group, Route 53 or deployment change is authorized or executed.

Tareas realizadas:

- Versioned `front/`, corrected JPEG extensions/MIME references, removed binary
  duplicates and added the mandatory synthetic-data DEV banner.
- Added `app/api` FastAPI adapter with `GET /api/v1/catalogs` and
  `POST /api/v1/leads`, explicit public-to-application DTO mapping, safe errors,
  request size limit, security headers, same-origin operation and no CORS.
- Added PostgreSQL-backed idempotency in `tpi.api_idempotency` through the
  versioned `scripts/sql/003_create_api_idempotency.sql` migration. It stores no
  payload or PII and uses a runtime HMAC key.
- Preserved `SolicitudService` as the only public lead business entrypoint and
  SNS publication as best effort strictly after commit.
- Changed local Compose/Caddy topology to static front + API on the public host
  and Streamlit backoffice on the private hostname.

Validacion local parcial:

- Applied the idempotency schema only to the local test database and passed the
  new integration cases for replay, conflict and notification failure.
- No AWS RDS change was made.

Pendiente:

- Complete full quality-gate validation and review before any push or AWS work.
- The runtime HMAC key must be supplied from a future exact secret; no secret
  has been created in this iteration.

Siguiente paso:

- Finish local tests, Docker/Compose/Caddy validation and commit the isolated
  H2.5C changes after review.

### 2026-08-16 - H2.5 public/private presentation separation

Contexto:

- H2.5 was corrected before AWS work: public lead capture must remain available
  without login, while the backoffice remains private.
- No AWS, billing-plan, DNS, Route 53, IAM, Secrets Manager, network, or
  deployment change is authorized in this iteration.

Tareas realizadas:

- Split Streamlit into the public `app/streamlit_app.py` entrypoint and private
  `app/backoffice_app.py` entrypoint.
- Reused `SolicitudService`, Pydantic requests, PostgreSQL repositories, and
  post-commit SNS behavior through a public presentation component.
- Kept `app/auth` unchanged in responsibility and applied it only to private
  entrypoints/pages.
- Changed Compose/Caddy declaration to route proposed public and backoffice
  hostnames to separate internal Streamlit services.
- Added public/private boundary tests and updated developer, architecture, CEO,
  and decision documentation.

Seguridad:

- The public Compose service does not receive `AUTH_USERS_JSON`.

### H2.5D temporary DEV DNS

- `dev.genialabs.cl` and `backoffice.dev.genialabs.cl` are the temporary AWS
  DEV hostnames. DNS and Caddy configuration are deployment concerns; the
  application core remains independent of the hostname.
- The public front sends `noindex,nofollow` in HTML and Caddy's
  `X-Robots-Tag`. Production TPI and its data remain outside this environment.
- Invalid auth configuration remains fail-closed for backoffice and does not
  prevent public lead capture.
- Port 8501 remains internal to Compose; no infrastructure rules changed.

Pendiente:

- Run complete local quality gates and review the refactor before any AWS work.
- After approval, separately decide account upgrade, domain registration,
  Route 53, auth secret, IAM, Caddy deployment, and access rules.

Siguiente paso:

- Complete local validation only; do not perform AWS operations.

### 2026-08-15 - H2.5 SimpleDevAuth local preparation

Contexto:

- H2.5 approved the DEV-only SimpleDevAuth, Caddy, and Docker Compose design.
- No AWS, DNS, IAM, Secrets Manager, user, Security Group, or deployment change
  is authorized until the external DNS CNAME is confirmed.

Tareas realizadas:

- Added the `app/auth` boundary with an immutable user contract, provider
  protocol, Argon2id SimpleDevAuth adapter, common guards, logout, and
  per-session throttling.
- Added safe auth settings with `AUTH_ENABLED=false` as the versioned default
  and a fail-closed mode for AWS DEV, production, malformed users config, and
  unknown auth modes.
- Prepared Docker Compose with Caddy as the only host listener and Streamlit on
  the internal Docker network.
- Added an exact-resource IAM policy template, tests, CI Compose validation,
  CEO validation guide, and development guide.

Seguridad:

- No password, password hash, user, AWS secret, IAM change, or network rule was
  created or committed.
- The future runtime secret is `tpi/dev/auth-users`; it will contain Argon2id
  hashes only and be injected only after explicit infrastructure approval.

Pendiente:

- Confirm control of the DNS zone and create the approved CNAME for
  `dev.tupensioninteligente.cl` outside this repository.
- Only then create the auth secret, attach the exact IAM permission, open
  80/443, deploy Compose, create the approved DEV user, and run the HTTPS smoke
  test.

Siguiente paso:

- Wait for DNS confirmation; do not perform AWS changes before it arrives.

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

### 2026-08-15 - H2.5 preflight SimpleDevAuth y Caddy

Contexto:

- Se reemplazo el preflight previo ALB/Cognito por una propuesta temporal y
  explicitamente DEV ONLY: Caddy HTTPS delante de Streamlit y SimpleDevAuth
  desacoplado mediante `app/auth/`.

Hallazgos y decision propuesta:

- Elastic Beanstalk Docker puede usar Docker Compose con un proxy propio; Caddy
  seria el unico contenedor que expone 80/443 y Streamlit quedaria interno en
  8501.
- La cuenta AWS no tiene Hosted Zone Route 53. El DNS publico actual delega en
  DataTecno y no existe el CNAME `dev.tupensioninteligente.cl`; se requiere
  confirmar control administrativo y aprobar el registro antes de ACME.
- El secreto propuesto `tpi/dev/auth-users` contiene solo hashes Argon2id y
  metadata minima. El role EB recibira lectura unicamente sobre su ARN exacto.
- El modo SimpleDevAuth tendra guard fail-closed, sesion Streamlit sin password
  ni hash, logout y throttle por sesion. Produccion debera migrar a HTTPS
  administrado y OIDC con un IdP profesional.

Estado:

- No se crearon ni modificaron recursos, usuarios, secretos, DNS, IAM ni
  Security Groups. Se requiere aprobacion del preflight y confirmacion DNS.
- Detalle completo: `docs/H2_5_SIMPLE_DEV_AUTH_PREFLIGHT.md`.

### 2026-08-15 - H2.4 notificaciones extensibles de leads

Contexto:

- H2.4 introduce una capacidad post-commit para notificar `lead.created` sin
  acoplar el flujo de negocio a email, SNS ni boto3.

Decisiones y hallazgos:

- `LeadCreatedEvent` es un contrato versionado y sin PII: solo UUIDs,
  timestamp UTC, ambiente y fuente.
- `SolicitudService` publica despues del commit del Repository y tolera el
  fallo del publisher; el lead confirmado nunca se revierte por SNS.
- SNS Standard usa el topic `tpi-dev-lead-created`. La suscripcion email
  aprobada no se versiona y fue confirmada manualmente antes del smoke test.
- El rol EB recibe un inline policy con `sns:Publish` solamente sobre el ARN
  exacto del topic. El secreto administrativo y PostgreSQL no se modifican.

Validacion:

- Unit e integracion cubren payload sin PII, publisher deshabilitado/fallido,
  commit antes de publicar y persistencia del lead cuando falla SNS.
- La regresion local completa paso: 226 tests, cobertura 88.49%, Ruff, Black,
  MyPy, Bandit y pip-audit verdes. Los seis warnings Altair existentes no son
  bloqueantes.
- Se desplego `h2-4-9ea12f10e674` en `tpi-backoffice-dev`, que regreso a
  `Ready/Green`; contenedor healthy y endpoints raiz y `/_stcore/health` con
  HTTP 200 desde la IP autorizada.
- Las propiedades runtime exclusivas de DEV habilitan notificaciones y apuntan
  al topic SNS; los defaults versionados permanecen apagados.
- Smoke test real: el lead ficticio se confirmo en RDS, SNS publico el evento
  sin PII, se recibio el email operacional y el UUID coincidio. La limpieza
  H2.3 posterior dejo el lead inexistente y cero consentimientos asociados.
- CloudWatch conserva logs por siete dias. La consulta de conteo de patrones
  sensibles sobre stdout/stderr no encontro coincidencias en la ventana del
  deployment; no se registraron secretos ni PII en la evidencia revisada.

Siguiente paso:

- Crear o actualizar el PR draft H2.4 contra `main` y esperar CI verde antes
  de solicitar revision. La integracion GitHub local no tiene permiso para
  crear PRs; la rama ya fue publicada.

### 2026-08-14 - H2.3 limpieza controlada de leads ficticios en AWS DEV

Contexto:

- H2.3 habilita el flujo de datos ficticios crear, consultar y limpiar solo en AWS DEV.

Decisiones y hallazgos:

- La habilitacion exige `APP_ENV=aws-dev` y `DEV_DELETE_ENABLED=true`; cualquier otro ambiente queda denegado en Service.
- El inventario de RDS encontro referencias a `leads` desde `asignaciones`, `auditoria`, `campanas_atribucion`, `citas`, `consentimientos`, `eventos_lead`, `fichas_diagnosticas` e `ingesta_google_sheets`.
- `auditoria` tambien referencia `personas`, por lo que H2.3 conserva personas y no concede DELETE sobre esa tabla.
- La transaccion borra solo consentimientos y el lead. Una FK operacional bloquea la operacion y revierte todo.
- Los scripts `scripts/sql/dev/002_enable_test_cleanup.sql` y `002_disable_test_cleanup.sql` otorgan y revocan DELETE solo en consentimientos y leads para `tpi_app` en DEV.

Validacion:

- Unit, integration PostgreSQL, E2E y security cubren guard de ambiente, UUID invalido, doble ejecucion, SQL parametrizado, persona compartida y rollback por FK.
- La UI requiere checkbox y texto `ELIMINAR`, y registra eventos sin PII usando solo el UUID interno del lead.
- Se aplico `002_enable_test_cleanup.sql` desde una conexion administrativa temporal con `tpi_admin`. `tpi_app` quedo sin atributos administrativos, sin DELETE en `personas` ni tablas operacionales, y con DELETE solo en `tpi.leads` y `tpi.consentimientos`.
- Se desplego `h2-3-3d5ded341436` en `tpi-backoffice-dev`. La configuracion versionada conserva `DEV_DELETE_ENABLED=false`; la propiedad efectiva `true` existe solo en el environment DEV.
- El contenedor desplegado esta healthy y corre como `appuser`; los checks confirmaron `APP_ENV=aws-dev`, salud PostgreSQL completa, HTTP 200 en raiz y `/_stcore/health`, y banner visible de ambiente DEV.
- El smoke test AWS con datos sinteticos completo crear, consultar, eliminar y verificar ausencia de lead/consentimiento, conservando la persona. La revision agregada de CloudWatch stdout/stderr no encontro patrones de password, token, email, telefono ni RUT; la retencion es siete dias.

Seguridad y rollback:

- `tpi/dev/database-admin-password` se usa solo desde el perfil local administrativo `tpi-dev`; el rol de Elastic Beanstalk conserva acceso unicamente al secreto de aplicacion. Ningun valor de secreto se versiona ni se registra.
- Para revertir H2.3: configurar `DEV_DELETE_ENABLED=false` en `tpi-backoffice-dev`, reiniciar o redeployar y ejecutar `scripts/sql/dev/002_disable_test_cleanup.sql` con `tpi_admin`. RDS, H2.2 y los permisos de creacion/consulta permanecen intactos.

### 2026-08-14 - H2.2 correccion de empaquetado para CI

Contexto:

- El PR H2.2 agrego el directorio declarativo `deployment/`, y setuptools intento descubrirlo como un segundo paquete Python durante la instalacion editable de CI.

Correccion:

- Se declaro `[tool.setuptools.packages.find]` con `include = ["app*"]` en `pyproject.toml`.
- `deployment/` permanece fuera del paquete distribuible y conserva su funcion de configuracion de Elastic Beanstalk e IAM.

Validacion:

- `python -m pip install --no-deps -e .` completo correctamente.
- La regresion completa, cobertura, Ruff, Black, MyPy, Bandit, pip-audit y Docker build se ejecutaron sin modificar runtime, reglas de negocio ni infraestructura AWS.

### 2026-08-14 - H2.2 despliegue real Streamlit en AWS DEV

Contexto:

- Se aprobo el pre-flight y se publico el artefacto Streamlit existente en Elastic Beanstalk, sin cambios de negocio.

Tareas realizadas:

- Se creo el SG `tpi-backoffice-dev-sg` con HTTP solo desde la IP autorizada `/32`.
- Se agrego al SG RDS existente una regla TCP 5432 con origen exclusivo en el SG de aplicacion; la regla administrativa DBeaver se mantuvo intacta.
- Se crearon los roles IAM de instancia y de servicio para Elastic Beanstalk, con lectura limitada al secreto DEV de base de datos y SSM para diagnostico sin SSH publico.
- Se creo la aplicacion `tpi-backoffice` y el environment `tpi-backoffice-dev` en Docker Amazon Linux 2023, Single Instance `t3.micro`.
- Se habilito CloudWatch Logs con retencion de siete dias.
- Se documento el despliegue, operaciones, costos, troubleshooting y rollback en `docs/H2_2_AWS_DEV_DEPLOYMENT.md`.

Seguridad y decisiones:

- `DATABASE_PASSWORD` se inyecta desde Secrets Manager por Elastic Beanstalk; no se leyo ni versiono su valor.
- La instancia tiene solo el SG dedicado. Se configuro `DisableDefaultEC2SecurityGroup=true`, no hay SSH ni 8501 expuestos, y RDS no tiene 5432 abierto a Internet.
- El primer bundle incluyo por error `docker-compose.yml`, por lo que Elastic Beanstalk intento usar servicios locales. Se corrigio con `.gitattributes` y `export-ignore`; el bundle final usa solo el Dockerfile del repositorio.

Resultados:

- Environment `Ready/Green`, instancia `running`, Docker `healthy` y usuario de contenedor `appuser`.
- `/_stcore/health` y la pagina principal respondieron HTTP 200 desde la IP autorizada.
- El healthcheck interno confirmo conexion PostgreSQL con SSL, esquema `tpi` y acceso a `tpi.leads`.
- El CI del PR termino con `194 passed`, 83.42 por ciento de cobertura y seis warnings no bloqueantes. Ruff, Black, MyPy, Bandit, pip-audit y Docker build quedaron verdes.

Riesgos y pendientes:

- El environment es HTTP temporal y Single Instance; autenticacion, HTTPS y alta disponibilidad siguen fuera de H2.2.
- RDS mantiene `PubliclyAccessible=true` por alcance aprobado; su proteccion efectiva depende del SG restringido.
- No avanzar a H2.3 sin aprobacion explicita.

### 2026-08-14 - H2.2 pre-flight completado con perfil AWS TPI

Contexto:

- Se autentico el perfil local `tpi-dev` mediante `aws login` para la cuenta TPI y se valido la identidad antes de cualquier cambio AWS.

Hallazgos:

- Cuenta validada: `8216...5812`; region efectiva para H2.2: `us-east-2`.
- RDS `tpi-postgres-dev` esta `available`, usa PostgreSQL 17.9, base `tpi`, puerto 5432 y cifrado en reposo.
- El RDS esta en la VPC por defecto `vpc-0f86145db5a906b73`, con tres subredes activas en `us-east-2a`, `us-east-2b` y `us-east-2c`.
- La VPC tiene DNS habilitado, subredes con asignacion publica y una ruta por defecto hacia Internet Gateway.
- RDS es publicamente direccionable, pero su Security Group `tpi-postgres-admin-sg` permite PostgreSQL solo desde una IP administrativa individual `/32`; no existe acceso `0.0.0.0/0` a 5432.
- Backups: un dia de retencion; Multi-AZ: deshabilitado; deletion protection: habilitado; logs PostgreSQL: habilitados.

Decision:

- Es viable crear posteriormente un Security Group de aplicacion Elastic Beanstalk en la misma VPC y autorizarlo como origen TCP 5432 en el Security Group de RDS.
- La regla administrativa existente se conserva; no se modificaron RDS, VPC, IAM, Secrets Manager ni Security Groups durante este pre-flight.

Riesgos a resolver antes del despliegue:

- RDS es `PubliclyAccessible=true`; H2.2 debe mantener su SG restringido y no agregar reglas publicas para PostgreSQL.
- La VPC actual es de subredes publicas y Single Instance; es adecuada para DEV de bajo costo, no para un entorno productivo de alta disponibilidad.

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

### 2026-08-14 - H2.2 pre-flight repetido en us-east-2 confirma cuenta AWS distinta

Contexto:

- Se recibio la correccion de region `us-east-2`, el identificador `tpi-postgres-dev` y su endpoint RDS esperado.

Resultado:

- La identidad AWS activa pertenece a la cuenta enmascarada `0514...8454`; solo existe el perfil local `default` y su region configurada sigue siendo `us-east-1`.
- La consulta se ejecuto explicitamente con `--region us-east-2` y RDS respondio `DBInstanceNotFound` para `tpi-postgres-dev`.
- El endpoint proporcionado resuelve DNS en `us-east-2`, por lo que la instancia existe, pero no pertenece a la cuenta AWS activa o no es visible para sus credenciales.

Decision:

- No se puede obtener de manera autorizada el estado, VPC, subnet group, Security Groups, cifrado, backups ni configuracion de red de RDS.
- No se crearon ni modificaron recursos AWS.

Siguiente paso:

- Configurar o asumir el perfil/rol de la cuenta propietaria de RDS y repetir el pre-flight en `us-east-2` antes de crear Elastic Beanstalk o cualquier regla de red.

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
