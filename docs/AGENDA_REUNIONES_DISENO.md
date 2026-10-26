# Agenda de reuniones del CRM: diseño y decisiones

Estado: **decisiones del humano del 2026-10-26, confirmadas el mismo día (secciones 2 y 3); tareas definidas; sin código ni migración todavía**. Este documento fija las decisiones antes de escribir código. Las tareas que lo
implementan están en `tasks/backlog.yaml` (prefijo `CRM-AGENDA-`). Si una decisión cambia, se cambia aquí primero.

## 1. Qué se quiere

Que cuando un lead es positivo y quiere asesoría, el Runner (o el Coordinador) pueda **agendar una reunión con un Socio o un Coordinador** en un calendario del CRM, y que todos
vean quién atiende cada reunión y quién la agendó. Esta primera versión no se conecta a ningún calendario externo.

Origen: pedido del humano del 2026-10-26 y el protocolo de Runners (`TPI_Protocolo_Runners_Canal_Web.pdf`, páginas 4 a 9: la reunión se agenda con día, hora,
modalidad y socio; si el lead no llega, vuelve a «En seguimiento»).

## 2. Decisiones del humano

| # | Decisión | Valor |
|---|---|---|
| 1 | Calendario | **Propio del CRM y común**: un solo calendario para todos, sin calendarios por persona. |
| 2 | Quién lo ve | **Todos** los perfiles (Runner, Coordinador y Socio). |
| 3 | Quién agenda | **Todos** pueden agendar (con el alcance de la sección 5). |
| 4 | Qué muestra cada reunión | El **responsable de la asesoría** (el Socio o Coordinador que atiende) y **quién la agendó**. |
| 5 | Sincronizaciones y lo demás | **Versión 2** (Google Calendar y Meet, recordatorios, etc.; sección 9). |
| 6 | Quiénes son Socios | Para la agenda, **Socio = solo CEO y CTO** (Diego y Álvaro en DEV), para no sumar complejidad. Pepe y María de los Ángeles quedan fuera por ahora. |
| 7 | Quién hace la reunión con el lead | **Los Socios y los Coordinadores**: solo ellos pueden ser el responsable de la asesoría. El Runner no. |
| 8 | Supuestos B a I de la sección 3 | **Confirmados** tal como están escritos («de acuerdo con todo»). |
| 9 | Quién agenda con quién | «El Coordinador solo puede agendar sus leads y los Runner solo pueden asignar reuniones a los Socios» (2026-10-26). Detalle en el supuesto J. |
| 10 | Orden | **`CRM-NO-CONTACTAR-1` queda para después**: primero la agenda (`CRM-AGENDA-1-MIGRACION` y luego `CRM-AGENDA-2-CALENDARIO`). |

## 3. Supuestos (confirmados, salvo J)

Valores que propuse para no frenar el diseño. El humano los confirmó el 2026-10-26 (decisión 8), con el cambio de la decisión 6 en A. El supuesto J es una
consecuencia de la decisión 7 y sigue por confirmar (sección 10). Cada uno se cambia con una frase del humano antes de implementar.

| # | Tema | Valor propuesto |
|---|---|---|
| A | Responsables posibles | Los Socios (solo CEO y CTO) y los Coordinadores activos que tengan la marca `atiende_reuniones` en `tpi.asesores`. Es un dato, no código: sumar un Socio o un Coordinador es una fila o una marca. |
| B | Horario | Lunes a viernes, 09:00 a 19:00, hora de Chile (`America/Santiago`). Se guarda en UTC y se muestra en hora de Chile. |
| C | Duración | 30, 45 o 60 minutos (30 por defecto). El inicio puede caer cada 15 minutos. |
| D | Superposición | Un responsable **no puede tener dos reuniones que se pisen**. Un lead tiene como máximo **una reunión agendada** a la vez. |
| E | Lead de otra cartera | En el calendario común se ve el bloque (hora, responsable, quién agendó, modalidad) pero **sin nombre ni enlace del lead** si ese lead está fuera del alcance de quien mira. Un Socio ve todo. |
| F | Quién hace qué con una reunión | Agendar, reagendar y cancelar: quien tiene alcance sobre el lead. **Marcar realizada y no asistió: solo Coordinador y Socio** (el Runner no puede fijar `reunion_realizada` hoy, y quien atiende la reunión es un Socio o un Coordinador). Cada acción queda en la auditoría con su autor. |
| G | Avisos en la v1 | **Ninguno automático**: la reunión se ve en el calendario y en el detalle del lead. Correo, WhatsApp y recordatorios son v2. |
| H | Feriados | No se bloquean en la v1 (se ve el calendario y se decide). |
| I | Modalidad | Google Meet, Llamada o Presencial. El enlace de la reunión se pega a mano y es opcional. |
| J | Quién puede ser responsable de cada reunión | **Confirmado** (decisión 9). **Runner**: solo agenda leads de su cartera y solo puede elegir como responsable a un Socio. **Coordinador**: solo agenda leads de su cartera y puede ser el responsable o elegir a un Socio. **Socio**: agenda cualquier lead y elige a un Socio o al Coordinador dueño de la cartera de ese lead. Un Coordinador solo es responsable de leads de su propia cartera, así que quien atiende la reunión siempre puede ver al lead. El servidor lo valida con los datos de la base. La última frase (el Socio puede elegir al Coordinador dueño del lead) la deduje de la decisión; no la dijo el humano. |

## 4. Cómo funciona

Todo el flujo se hace desde el detalle del lead y desde la página **Agenda**.

| Acción | Quién | Efecto en la reunión | Efecto en el estado del lead |
|---|---|---|---|
| Agendar | Runner, Coordinador y Socio con alcance sobre el lead | Se crea con estado `agendada`, responsable, hora, duración, modalidad y nota opcional | Pasa a `reunion_agendada` |
| Reagendar | Ídem | Cambia hora, duración, responsable, modalidad o enlace; la misma reunión | Sigue en `reunion_agendada` |
| Cancelar | Ídem | Estado `cancelada`, con motivo obligatorio | Vuelve a `en_seguimiento` |
| Marcar realizada | **Solo Coordinador y Socio** con alcance | Estado `realizada` | Pasa a `reunion_realizada` |
| Marcar no asistió | **Solo Coordinador y Socio** con alcance | Estado `no_asistio` | Vuelve a `en_seguimiento` (regla del protocolo) |

Reglas:

- Solo se agenda un lead **activo** (no `cerrado`, `perdido`, `no_interesado`, `datos_erroneos` ni `no_contactado`). Cuando exista la marca «no contactar»
  (`CRM-NO-CONTACTAR-1`), un lead con esa marca no se agenda.
- El cambio de estado del lead usa **el mismo servicio y la misma auditoría** que el cambio de estado manual (`update_lead_status`), no un camino aparte. Esa regla
  ya impide al Runner fijar `reunion_realizada`, `ficha_generada` y `cerrado` (`_RUNNER_FORBIDDEN_STATUS_STATES`); la agenda no la debilita.
- No se agenda en el pasado ni fuera del horario (supuestos B y C); el servidor lo valida, no solo el formulario.
- El responsable es un Socio (CEO o CTO) o un Coordinador activo, nunca un Runner. El Runner solo elige Socios y un Coordinador solo es responsable de leads de su cartera (supuesto J).
- Si el responsable ya tiene una reunión que se pisa, se rechaza con un mensaje claro («Ese Socio ya tiene una reunión entre 15:00 y 15:45»). La regla la sostiene la
  base de datos (sección 6), así que dos personas agendando a la vez no pueden duplicar el horario.
- Una reunión `realizada`, `cancelada` o `no_asistio` no se reabre: si hace falta otra, se agenda una nueva.

## 5. Quién ve y quién hace qué

El alcance de cartera es el de `CRM-PERFILES-1-RBAC` (`has_portfolio_scope`): el Runner y el Coordinador trabajan sus leads; el Socio ve y trabaja todos.

| Perfil | Ver el calendario | Ver nombre y enlace del lead | Agendar, reagendar y cancelar | Marcar realizada y no asistió |
|---|---|---|---|---|
| Runner | Sí, todo | Solo los de su cartera | Solo leads de su cartera | No |
| Coordinador | Sí, todo | Solo los de su cartera | Solo leads de su cartera | Solo leads de su cartera |
| Socio (`ceo`/`cto`) | Sí, todo | Todos | Todos | Todos |
| Roles que hoy no escriben (`executive`, `readonly`) | Sí | Según su regla actual | No | No |
| Roles heredados que hoy escriben (`tester`, `operations`, `admin`) | Sí | Según su regla actual | Como hoy en un lead | No |

Quién puede ser **responsable** de una reunión es otra pregunta: los Socios (CEO y CTO) y los Coordinadores (con la restricción del supuesto J), nunca un Runner; el Runner
solo puede elegir a un Socio.

«Agendar» reutiliza las comprobaciones del cambio de estado (`_can_write`, el alcance de cartera del servicio y el token CSRF), sin una regla nueva. Un lead fuera
de alcance responde `404` si se intenta abrir o modificar, como hoy.

## 6. Modelo de datos (migración de clase D)

Ya existe `tpi.citas` (0 filas en DEV, sin uso): `id_cita`, `id_lead`, `id_asesor` (opcional), `fecha_hora`, `canal`, `estado_cita`, `link_reunion`, `created_at`.
Se **amplía**, no se crea otra tabla:

| Cambio | Detalle |
|---|---|
| `id_asesor` | Pasa a obligatorio: es el **responsable de la asesoría** (un Socio o un Coordinador de `tpi.asesores`). Se exige que la tabla esté vacía al migrar. |
| `fecha_hora_fin` | Nueva, `TIMESTAMPTZ NOT NULL`, con `CHECK (fecha_hora_fin > fecha_hora)`. |
| `agendada_por_subject`, `agendada_por_nombre` | Nuevas: quién agendó (identidad de inicio de sesión y nombre visible). Texto, sin clave foránea: la agenda no depende de que ese usuario tenga fila en `asesores`. |
| `nota` | Nueva, texto opcional (máximo 500 caracteres que valida el servicio). |
| `motivo_cancelacion` | Nueva, texto, obligatorio al cancelar. |
| `updated_at` | Nueva, `TIMESTAMPTZ NOT NULL DEFAULT now()`. |
| `estado_cita` | `CHECK` con `agendada`, `realizada`, `no_asistio`, `cancelada`. |
| `canal` | Se reutiliza como modalidad (`Google Meet`, `Llamada`, `Presencial`). |
| Índice único parcial | `UNIQUE (id_lead) WHERE estado_cita = 'agendada'`: una sola reunión agendada por lead. |
| Restricción de exclusión | `EXCLUDE USING gist (id_asesor WITH =, tstzrange(fecha_hora, fecha_hora_fin) WITH &&) WHERE estado_cita = 'agendada'`: el responsable no se pisa. Necesita la extensión `btree_gist`; **hay que comprobar que RDS la permite al usuario `tpi_admin`** antes de fijar el diseño (alternativa: comprobar dentro de la transacción con `pg_advisory_xact_lock` por responsable). |
| `tpi.asesores.atiende_reuniones` | Nueva, `BOOLEAN NOT NULL DEFAULT false`: marca quién puede ser responsable de una reunión. Es verdadera para CEO y CTO y para los Coordinadores. |
| Índice de lectura | Por `fecha_hora`, para pintar el calendario por semana. |
| Privilegios | `tpi_app` recibe `SELECT, INSERT, UPDATE` sobre `tpi.citas` (nunca `DELETE`: la reunión se cancela, no se borra). Hoy no los tiene (`docs/AWS_RDS_CONNECTION.md`). |

Los dos Socios (CEO y CTO) entran como filas de `tpi.asesores` con `rol = 'socio'` y `atiende_reuniones = true`. Esto **no** los mete en el reparto automático ni en la
cartera: las consultas de asignación y de cartera filtran por `rol = 'asesor'` (`app/repositories/solicitud_repository.py`). Los Coordinadores **conservan** `rol = 'asesor'`
(la cadena de cartera lo exige) y se distinguen solo por la marca `atiende_reuniones = true`. La lista de responsables es `atiende_reuniones` y
`estado_disponibilidad = 'activo'`. Las altas y las marcas las hace un script humano con `tpi_admin` (se extiende `scripts/dev_usuarios.py`).

La migración sigue el patrón de clase D del proyecto: script humano con `tpi_admin` (`plan`, `apply`, `verify`, `rollback`), probado antes en la base local desechable, y
documentación en `docs/database/` (se actualizan `02_PHYSICAL_SCHEMA.md` y `08_DEV_DATA_INVENTORY.md`).

## 7. Pantallas

- **Agenda** (`/agenda`), en el menú para todos los perfiles. Vista **semana** (días por horas, con navegación anterior, siguiente y hoy) y vista **lista** de las
  próximas reuniones (la única en pantalla de celular). Filtro por responsable. Cada bloque muestra hora, responsable, quién agendó, modalidad y estado; el lead se
  muestra o se oculta según la sección 5.
- **Detalle del lead**: una tarjeta «Reunión» con la reunión agendada (o la última) y el botón **Agendar reunión**. El formulario pide fecha, hora, duración,
  responsable, modalidad, enlace y nota. Las acciones de reagendar, cancelar y marcar asistencia están en la misma tarjeta y en el bloque del calendario.
- Se aplica el sistema visual vigente (`docs/UI_DESIGN_SYSTEM.md`, `docs/ui/referencia/`) y las mismas protecciones de formularios que el cambio de estado.

## 8. Auditoría y resguardos

- Cada acción deja un evento en `tpi.auditoria` (append-only): `cita_agendada`, `cita_reagendada`, `cita_cancelada`, `cita_realizada` y `cita_no_asistio`, con
  `tabla_afectada = 'tpi.citas'`, el sujeto que actuó y los datos de la reunión (id, responsable, hora anterior y nueva). **Sin nombre ni datos personales del lead**
  en el detalle.
- El calendario común es el único lugar donde alguien ve filas de leads que no son suyos: por eso la consulta del servidor **ya entrega los datos recortados** (no se
  envía el nombre al navegador para luego ocultarlo), y la prueba lo verifica leyendo la respuesta, no solo la pantalla.
- Fechas y horas: se guardan en `TIMESTAMPTZ` y se calculan con `zoneinfo` (`America/Santiago`), con pruebas en los dos cambios de hora del año.
- Una reunión nunca se borra: queda como `cancelada` con su motivo.

## 9. Qué no entra en la v1 (v2 y siguientes)

- Sincronización con Google Calendar y creación del enlace de Meet; invitaciones `.ics`.
- Recordatorios (día antes y una hora antes), por correo o WhatsApp, y aviso al Socio al agendar.
- Disponibilidad por Socio (bloquear horarios), feriados de Chile y reuniones fuera de horario.
- Vincular el inicio de sesión de cada Socio y Coordinador con su fila de `asesores` para un filtro «mis reuniones».
- Más Socios (Pepe y María de los Ángeles): cuando se decida, es una fila nueva con la marca, sin cambios de código.
- El resto del protocolo, que sigue en `CRM-AGENDAMIENTO`: registro de intentos y cadencia, calificación del lead, mensajes de WhatsApp copiables y el panel por runner
  con los seis criterios.

## 10. Preguntas: respuestas y lo que sigue abierto

Respuestas del humano del 2026-10-26 («de acuerdo con todo»), con sus cambios:

1. **Socios responsables** (A): solo CEO y CTO (decisión 6). Además, la reunión con el lead la hacen **Socios y Coordinadores** (decisión 7).
2. **Horario y duración** (B y C): confirmados.
3. **Calendario común y privacidad** (E): confirmado.
4. **Quién hace qué** (F): confirmado.
5. **Avisos** (G): confirmado, sin avisos automáticos en la v1.
6. **Orden**: `CRM-NO-CONTACTAR-1` queda para después (decisión 10). Mientras tanto la agenda no debe usarse con datos reales: la ley obliga a esa tarea antes de cargarlos
   (2026-12-01).

También quedó resuelto el punto J (quién puede ser responsable): ver el supuesto J de la sección 3. No quedan preguntas abiertas.

## 11. Tareas y criterios para darla por terminada

Tareas (definidas en `tasks/backlog.yaml`; el humano activa la primera con `approve.py activate`, en este orden):

1. `CRM-AGENDA-1-MIGRACION` (clase D): ampliar `tpi.citas`, privilegios, script humano con `plan`/`apply`/`verify`/`rollback`, columna `atiende_reuniones`, alta de CEO y CTO como
   responsables, marca de los Coordinadores y documentación de la base. La aplica el humano en DEV.
2. `CRM-AGENDA-2-CALENDARIO` (clase A, con despliegue y aceptación humana): servicio, rutas, pantallas y pruebas. Depende de la anterior.
3. Opcional, después: siembra de reuniones de prueba en DEV (extender `scripts/dev_reset_leads.py`: futuras para los leads en `reunion_agendada`, pasadas para
   `reunion_realizada`). No está definida como tarea; la prueba humana puede agendar a mano.

La función está terminada cuando:

- **AC-1**: la migración está aplicada y verificada en DEV, y el rollback se probó en la base local.
- **AC-2**: agendar desde el detalle del lead guarda la reunión con su responsable y quién la agendó, y el lead pasa a `reunion_agendada`.
- **AC-3**: dos reuniones del mismo responsable no se pisan, tampoco con dos solicitudes simultáneas; el mensaje de error es claro.
- **AC-4**: un lead tiene como máximo una reunión agendada.
- **AC-5**: reagendar, cancelar (con motivo), marcar realizada y marcar no asistió funcionan y dejan el estado del lead que indica la sección 4.
- **AC-6**: todos los perfiles ven el calendario; un lead fuera de alcance aparece sin nombre ni enlace, y la respuesta del servidor no contiene sus datos.
- **AC-7**: la matriz de permisos está probada completa: lectura y escritura, `GET` y `POST`, entre carteras, y un rol de solo lectura que no puede escribir.
- **AC-8**: cada acción queda en la auditoría con su autor.
- **AC-9**: horario, duración, pasado y cambio de hora de Chile se validan en el servidor.
- **AC-10**: la lista de responsables trae solo a CEO, CTO y a los Coordinadores marcados; un Runner no puede ser responsable, solo elige Socios, y un Coordinador solo lo es
  en leads de su cartera.
- **AC-11** (humano, en DEV): un Runner agenda con un Socio, un Coordinador ve el calendario y atiende y marca como realizada la reunión de un lead de su cartera, y un
  Socio marca como realizada la de un lead de un Runner.
