# Agenda de reuniones del CRM: guía de uso

La agenda de reuniones es el calendario común del CRM (un solo calendario para todos los
perfiles). Permite agendar una reunión de asesoría desde el detalle de un lead, verla en
el calendario semanal o en la lista de próximas reuniones, y registrar su desenlace. No se
conecta a ningún calendario externo (Google Calendar, Meet) en esta versión.

Fuente de las decisiones: `docs/AGENDA_REUNIONES_DISENO.md`.

## 1. Quién puede hacer qué

El alcance de cartera es el de siempre (`has_portfolio_scope`): el Runner y el Coordinador
trabajan sus leads; el Socio (CEO/CTO) ve y trabaja todos.

| Perfil | Ver calendario | Ver nombre/enlace del lead | Agendar, reagendar y cancelar | Marcar realizada / no asistió |
|---|---|---|---|---|
| Runner (`advisor`) | Todo | Solo su cartera | Solo leads de su cartera | No |
| Coordinador (`coordinator`) | Todo | Solo su cartera | Solo leads de su cartera | Solo leads de su cartera |
| Socio (`ceo`/`cto`) | Todo | Todos | Todos | Todos |
| Roles que hoy no escriben (`executive`, `readonly`) | Sí | Según su regla actual | No | No |
| Roles heredados que escriben (`tester`, `operations`, `admin`) | Sí | Según su regla actual | Como hoy en un lead | No |

Un lead fuera del alcance responde como hoy (404) si se intenta abrir o modificar. En el
calendario, un lead fuera del alcance aparece sin nombre, sin identificador y sin enlace;
el bloque dice «De otra cartera».

## 2. Quién puede ser el responsable de la reunión

El responsable es una fila activa de `tpi.asesores` con `atiende_reuniones = true`. Solo
los **Socios** (CEO y CTO, rol `socio`) y los **Coordinadores** (rol `asesor` con la marca)
pueden ser responsables; el Runner nunca.

- **Runner**: solo elige como responsable a un Socio.
- **Coordinador**: elige a un Socio o se elige a sí mismo (solo en leads de su cartera).
- **Socio**: elige a un Socio o al Coordinador dueño de la cartera de ese lead.

Un Coordinador solo es responsable de leads de su propia cartera. El servidor valida todo
contra la base, no con lo que envía el formulario, y el formulario solo ofrece las opciones
válidas.

## 3. Reglas de horario y modalidad

- Lunes a viernes, de **09:00 a 19:00** hora de Chile (`America/Santiago`).
- El inicio cae cada **15 minutos**; la duración es de **30, 45 o 60 minutos** (30 por
  defecto). La reunión debe terminar a más tardar a las 19:00.
- No se agenda en el pasado.
- Modalidad: **Google Meet**, **Llamada** o **Presencial**. El enlace y la nota son
  opcionales (la nota hasta 500 caracteres).
- Un responsable no puede tener dos reuniones que se pisen (lo sostiene la base). Un lead
  tiene como máximo una reunión agendada.

## 4. Estados de la reunión y efecto en el lead

| Acción | Estado de la reunión | Estado del lead |
|---|---|---|
| Agendar | `agendada` | `reunion_agendada` |
| Reagendar | `agendada` (la misma reunión) | sigue en `reunion_agendada` |
| Cancelar (motivo obligatorio) | `cancelada` | `en_seguimiento` |
| Marcar realizada | `realizada` | `reunion_realizada` |
| Marcar no asistió | `no_asistio` | `en_seguimiento` |

Una reunión `realizada`, `cancelada` o `no_asistio` no se reabre: si hace falta otra, se
agenda una nueva. La reunión nunca se borra.

## 5. Dónde se usa

- **Página Agenda** (`/agenda`, en el menú superior para todos los perfiles):
  - **Vista Semana**: cuadrícula de lunes a viernes con una fila por hora (09:00 a 19:00);
    cada reunión se ubica según su hora y duración, y las reuniones simultáneas se reparten
    en carriles lado a lado. El día de hoy se resalta y, dentro del horario, muestra una
    línea con la hora actual. La cabecera tiene navegación anterior/siguiente/hoy y el
    selector Semana/Lista, que conservan el filtro y la fecha en la URL.
  - **Leyenda de responsables**: chips con un tono por responsable que filtran el calendario
    (con «Todos» para quitar el filtro).
  - **Resumen de la semana**: contador de reuniones agendadas, realizadas, no asistidas y
    canceladas de la semana visible.
  - **Vista Lista**: las próximas reuniones agrupadas por día (Hoy, Mañana o la fecha), con
    hora, duración, responsable, modalidad y estado. En pantalla de celular se usa esta vista.
- **Detalle del lead**: la tarjeta «Reunión» muestra la reunión agendada (o la última) con una
  ficha de fecha y el responsable con su tono, además de los botones para agendar, reagendar,
  cancelar y marcar realizada o no asistió, según el perfil. El formulario de agendar y
  reagendar ofrece los responsables como tarjetas y la duración y la modalidad como botones,
  con el token CSRF y las mismas protecciones del cambio de estado.
- **Barra superior**: el logo de TPI lleva al sitio público (solo con sesión y con la URL
  aprobada, en pestaña nueva); se retiró el botón «Home».

## 6. Auditoría

Cada acción deja un evento en `tpi.auditoria` (`tabla_afectada = 'tpi.citas'`):
`cita_agendada`, `cita_reagendada`, `cita_cancelada`, `cita_realizada` y `cita_no_asistio`,
con el sujeto que actuó, el identificador de la reunión, el responsable y las horas
anterior y nueva. El detalle no lleva nombre ni datos personales del lead.

## 7. Historial del lead (Seguimiento y Notas Internas)

Los eventos de la agenda también aparecen en la línea de tiempo del historial del lead,
mezclados en orden cronológico con las notas humanas, los cambios de estado y las
simulaciones. La aplicación **nunca** lee `tpi.auditoria` directamente para esto: lee la
vista de solo lectura `tpi.v_historial_agenda` (migración 011), que solo expone las cinco
acciones de la agenda con sus columnas sanitizadas, unida a `tpi.asesores` para el nombre
del responsable.

Cada evento se muestra con la insignia «Automático» y el actor, con estos textos (fechas en
`DD/MM/AAAA HH:MM`, hora de Santiago):

| Acción | Texto |
|---|---|
| Agendada | `Reunión agendada para <fecha> con <responsable>` |
| Reagendada | `Reunión reagendada: <fecha anterior> → <fecha nueva> (con <responsable>)` |
| Cancelada | `Reunión cancelada (era el <fecha> con <responsable>)` |
| Realizada | `Reunión realizada (<fecha> con <responsable>)` |
| No asistió | `El lead no asistió a la reunión (<fecha> con <responsable>)` |

Si el responsable no se puede resolver, se escribe «responsable no disponible». No se
muestran la nota ni el motivo de cancelación (no están en la auditoría de la agenda) ni
ningún id interno. Los eventos se cargan solo cuando el usuario puede abrir el lead (el
mismo control de alcance del detalle): un Runner no ve eventos de un lead de otra cartera.
Si la lectura de la vista falla, el detalle sigue funcionando (200) con el resto del
historial, sin las líneas de agenda y sin registrar el error.

