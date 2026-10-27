# Referencia visual aprobada de la agenda (v1, 2026-10-26)

Esta carpeta guarda **el resultado aprobado por el humano** de la vista previa local del nuevo aspecto de la agenda de reuniones, del
contraste del historial del lead y de la barra superior (el logo lleva al sitio y se retira el botón Home). Es la fuente exacta de la tarea `CRM-AGENDA-3-LOOK`: el Developer **no inventa el diseño**, lo reproduce.
Se retira de `main` cuando la tarea esté cerrada.

## Qué contiene

| Ruta | Para qué |
|---|---|
| `app/web/templates/base.html` | Barra superior sin el botón **Home**: el logo es el enlace al sitio público (solo con sesión y con la URL aprobada, en pestaña nueva y con `rel="noopener noreferrer"`) |
| `app/web/templates/agenda.html` | Página Agenda: barra con navegación por semanas y selector Semana/Lista, leyenda de responsables que filtra, resumen de la semana, cuadrícula por horas (lunes a viernes) y lista agrupada por día |
| `app/web/templates/agenda_macros.html` | Iconos en línea (mismo trazo del CRM), iniciales y marcas de estado y modalidad |
| `app/web/templates/reunion_card.html` | Tarjeta Reunión del detalle del lead: ficha de fecha, responsable con avatar, modalidad, botón «Unirse a la reunión» y acciones en una fila |
| `app/web/templates/agenda_form_fields.html` | Formulario de agendar y reagendar: responsables como tarjetas, duración y modalidad como botones |
| `app/web/static/css/app.css` | Hoja de estilos completa de `main` (`dae6d58`) con el bloque de la agenda reescrito, el fondo del historial del lead (`.timeline-item`) igual al de la solicitud original y el bloque `.brand-link` del logo |
| `app/web/agenda_presentation.py` | Funciones de presentación nuevas: colores por responsable, rango de fechas, carriles de reuniones simultáneas, cuadrícula de la semana, resumen, agrupación por día y ficha de fecha |
| `app/web/routes/agenda.py` | La ruta `GET /agenda` arma el contexto nuevo (cuadrícula, leyenda, resumen, vistas, enlaces) |

## Cómo se generó

La vista previa se construyó sobre `main` con datos ficticios (17 reuniones, tres perfiles) y se revisó en el navegador en escritorio y celular,
en tema claro y oscuro. Las 101 pruebas de agenda existentes pasan sin cambios con esta versión.

## Cómo se aplica

Copiar cada archivo de esta carpeta a su ruta de destino (la ruta relativa dentro de esta carpeta es la ruta destino). El resultado debe ser
**idéntico a la referencia** ignorando diferencias de fin de línea (`git diff --no-index --ignore-cr-at-eol <referencia> <destino>` sin diferencias).
Si `app/web/static/css/app.css` cambió en `main` desde `dae6d58`, hay que reaplicar solo las tres partes propias (el bloque `Agenda de reuniones`, la
regla `.timeline-item` y el bloque `.brand-link` del final), no reemplazar el archivo entero.

## Qué NO es

No es un rediseño del resto del CRM ni autoriza cambios de comportamiento: reglas de la agenda, permisos, privacidad de los leads ajenos, CSRF y
rutas no cambian. Tampoco agrega tipografías, scripts ni librerías.
