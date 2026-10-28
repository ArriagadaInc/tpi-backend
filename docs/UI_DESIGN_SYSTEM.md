# Sistema de diseño del CRM: armonizar sin rediseñar

Estado: **aprobado por el humano el 2026-10-22** (referencia visual exacta en `docs/ui/referencia/ui1/`). La tarea
`CRM-UI-1-ARMONIA-VISUAL` reprodujo esa referencia en `app/web/`: tokens y componentes canónicos, iconos (sol/luna, salida,
exportar), tipografía **Plus Jakarta Sans alojada en el propio sitio** y la columna **Edad** en el listado de leads. Queda para la
tarea posterior la consolidación completa del CSS hacia tokens (sección 2 y métricas de la sección 2.1). Este documento fija la
dirección visual del backoffice y las reglas que siguen las tareas de interfaz. Lo usa el skill
`agents/developer/skills/tpi-ui-design/SKILL.md`.

## 1. Dirección

El humano pidió un CRM **profesional, moderno, atractivo y minimalista**, y dijo que le gusta cómo se ve hoy: **solo hay que
armonizarlo**. Por eso no se cambia la identidad (turquesa sobre azul pizarra, tarjetas blancas redondeadas, botones y chips en
píldora, tema claro y oscuro). Se ordena lo que creció por capas:

- **Una sola forma de hacer cada cosa**: un botón, un chip de estado, un encabezado de tarjeta, un campo de formulario.
- **Menos es más**: sin brillos de color en las sombras, pesos de letra más livianos, menos tamaños y radios distintos.
- **Todo sale de tokens**: ningún color, tamaño, radio ni sombra suelto fuera de `:root` y del bloque del tema oscuro.
- **Los dos temas**, claro y oscuro, y **móvil** (≥ 360 px sin scroll horizontal) se cuidan en cada cambio.

## 2. Línea base (medida con `python scripts/ui_css_audit.py`, 2026-10-22)

| Métrica | Hoy | Meta de la serie |
|---|---|---|
| Tokens en `:root` | 17 (solo color, radio y sombra) | escalas completas (secciones 4 y 5) |
| Colores sueltos fuera de los bloques de tokens | 80 distintos, 156 usos | ≤ 5 (logos y degradados puntuales) |
| Tamaños de letra distintos | 25 (0.72 a 1 rem, casi duplicados: 0.82, 0.84, 0.85, 0.86) | 8 |
| Pesos de letra | 700 (26), 800 (19), 600 (3) | 400, 500, 600, 700 |
| Radios distintos | 15 (6 a 28 px) | 4 (control, tarjeta, píldora, pequeño) |
| Sombras distintas | 13 | 3 |
| Espaciados distintos (padding, margin, gap) | 61 | los de la escala de 4 px |
| Cortes responsive | 5 (640, 800, 900, 1100, 1200) | 3 (640, 900, 1200) |
| Reglas de tema oscuro por componente | 39 | ≤ 5 (imágenes y logos) |
| `!important` / estilos en línea | 4 / 2 | 0 / 0 |

Defectos concretos que ya se ven en el código: `--shadow-sm` se usa dos veces y **no está definido** (esas sombras no se dibujan);
la tipografía **Inter está declarada pero nunca se carga** (cada dispositivo muestra otra cosa: Segoe UI, San Francisco, Arial);
htmx se carga desde `unpkg.com` sin atributo de integridad (SRI) y el backoffice no define una política de seguridad de
contenidos (CSP) (asunto de seguridad, aparte de esta serie).

### 2.1 Estado tras `CRM-UI-1-ARMONIA-VISUAL` (medido con `python scripts/ui_css_audit.py --json`, 2026-10-23)

La referencia aprobada ya aplica las escalas y los componentes canónicos sin reescribir todo el CSS a tokens. Métricas entregadas:
tamaños de letra distintos **10**, radios **9**, sombras **5**, espaciados **47**, colores sueltos distintos **73**, reglas de tema
oscuro por componente **41**, `!important` **4**. Queda para la tarea posterior de consolidación: bajar los colores sueltos
(73 → ≤ 5) y las reglas de tema oscuro por componente (41 → ≤ 5), y unificar el resto de la hoja, sin cambiar el aspecto aprobado.

## 3. Hallazgos visuales (vista previa local con datos ficticios)

1. **Cabecera de página con adornos repetidos**: el chip «Ambiente DEV» aparece en la barra superior y otra vez junto al título;
   los chips «Mostrando N leads» y «Ambiente» flotan sin alinear con el título.
2. **Títulos muy pesados**: el `h1` y varios `h2` usan peso 800; con el resto liviano se ve desbalanceado.
3. **Controles de distinta altura y ancho** en los filtros (selects truncados como «Todas l…», campo de búsqueda más alto que los
   demás); botones con brillo turquesa en la sombra.
4. **El chip de estado cambia entre pantallas**: coloreado y con borde en la lista; pequeño, negro y sin color junto al nombre en el
   detalle del lead.
5. **Encabezados de tarjeta sin patrón**: unas llevan una etiqueta en mayúsculas pequeñas («SIMULADOR», «ESTADO ACTUAL»), otras una
   etiqueta en minúsculas más un título, otras solo el título («Mensaje del cliente» + «Solicitud Original»).
6. **Notas y línea de tiempo con relleno desparejo**: el texto queda muy sangrado y las cajas tienen mucho espacio vacío; el
   «Sin solicitud disponible» ocupa una caja enorme.
7. **Texto técnico a la vista**: el dashboard muestra `current_snapshot`, `period_activity` y `fecha_ingreso (distinta de
   created_at)` a quien debería leer lenguaje de negocio.
8. **Móvil**: la barra superior ocupa tres filas (unos 230 px de 844) y los chips y botones de la cabecera tienen alturas distintas.

## 4. Tokens (todos con su versión en el tema oscuro)

Se conservan los nombres actuales de color. Lo nuevo se agrega junto a ellos en `:root` y en `[data-theme="dark"]`.

| Familia | Tokens | Valores (claro) |
|---|---|---|
| Color semántico | `--success`, `--warning`, `--danger` y sus `-soft` (fondo de chip) | los actuales; `--danger` pasa a ser token (hoy `#b91c1c` suelto) |
| Espaciado (4 px) | `--space-1` … `--space-9` | 4, 8, 12, 16, 20, 24, 32, 40, 48 px |
| Tipografía | `--text-xs` … `--text-3xl` | .75, .8125, .9375, 1, 1.125, 1.375, 1.75, 2.25 rem |
| Peso | `--weight-regular/medium/semibold/bold` | 400, 500, 600, 700 (se retira el 800) |
| Radios por rol | `--radius-sm`, `--radius-control`, `--radius-card`, `--radius-pill` | 8, 12, 20 px y 999 px |
| Sombras | `--shadow-1` (tarjeta), `--shadow-2` (menú, elevado), `--ring` (foco) | suaves, sin color turquesa |
| Movimiento | `--dur-1`, `--dur-2`, `--ease` | 120 ms, 200 ms, `cubic-bezier(.2,0,0,1)` |
| Capas | `--z-topbar`, `--z-popover`, `--z-toast` | 20, 40, 60 |

Cortes responsive (no admiten variables): **640, 900 y 1200 px**. Ancho de página y rellenos de tarjeta: `--page-max`, `--card-pad`.

## 5. Componentes canónicos

| Componente | Regla |
|---|---|
| Encabezado de página | etiqueta pequeña en mayúsculas (`--text-xs`, espaciado de letras) + `h1` (`--text-3xl`, peso 700) + bajada en `--muted`; acciones a la derecha; el ambiente solo en la barra superior |
| Tarjeta | fondo `--surface`, borde 1 px `--border`, `--radius-card`, relleno `--card-pad`, `--shadow-1`; encabezado: etiqueta opcional + `h2` (`--text-lg`, 600) |
| Botón | tres variantes (principal turquesa, secundario con borde, fantasma/enlace); misma altura (40 px, compacto 32), píldora; foco con `--ring` |
| Campo de formulario | altura 40 px, `--radius-control`, etiqueta arriba (`--text-sm`, 600); en filtros, rejilla de columnas iguales con mínimo 160 px |
| Chip de estado | un solo `.badge-status` con un tono por estado (neutro, info, turquesa, éxito, aviso, peligro), igual en la lista y en el detalle |
| Tabla | encabezado `--text-xs` en mayúsculas y `--muted`; filas de 52 px con resaltado al pasar; cifras alineadas a la derecha; «Ver» como botón fantasma |
| Nota / línea de tiempo | metadatos en `--text-sm` y `--muted`, cuerpo en `--text-base`, relleno `--space-4`, sin sangría de más |
| Vacío / alerta / aviso | un patrón para cada uno (icono opcional, texto breve, acción); los avisos usan los tonos semánticos |
| Barra superior | compacta; en móvil, una fila con menú que agrupa navegación y usuario |

Los patrones nuevos de la agenda (CRM-AGENDA-3-LOOK, aprobados el 2026-10-26) salen de los mismos tokens y componentes:
**cuadrícula por horas** (lunes a viernes con carriles para reuniones simultáneas y línea de «ahora»), **tonos por
responsable** (`accent`, `info`, `violet`, `warning` desde `PALETA`, con el neutro `slate` como respaldo) y **ficha de
fecha** de la tarjeta Reunión. El fondo del historial del lead (`.timeline-item`) usa `--surface-soft`, el mismo de la
solicitud original (`.original-request-box`); en el tema oscuro no cambia.

Los patrones nuevos del simulador (CRM-SIM-1-PAGINA-UNICA, aprobados el 2026-10-28) también salen de los mismos tokens y
componentes: **formulario con panel de resultado fijo** (dos tarjetas a la izquierda y el resultado a la derecha, que se
mantiene al desplazarse y en celular pasa debajo con desplazamiento automático), **tarjeta de resultado destacada** (azul
marino `#0f243e` de la ficha, con texto claro `#b8cce4` y `#ffffff`) y **opciones plegables** (`<details>` para «Opciones
de la renta», abierta solo cuando algún valor es distinto de cero).

## 6. Reglas para quien programa la interfaz

- Reutilizar antes de crear: si un componente de la sección 5 hace el trabajo, se usa; una clase nueva se justifica por escrito.
- Nada de colores, tamaños, radios, sombras ni espaciados sueltos; nada de `style=""` ni `!important`.
- El tema oscuro sale de los tokens; una regla `[data-theme="dark"] .componente` solo se acepta para imágenes y logos.
- Sin dependencias, CDN, scripts ni fuentes externas sin decisión del humano (hoy el backoffice ya carga htmx desde un CDN y no
  define CSP; no se agrega nada más de afuera).
- Lenguaje de negocio en pantalla: nunca nombres de campos ni de variables internas.
- Una tarea de interfaz no cambia comportamiento, permisos, HTMX, CSRF ni consultas: solo presentación.

## 7. Plan por tareas (todas clase A, con aceptación humana visual)

1. **Fundación**: tokens completos, `--shadow-sm` corregido, escalas, pesos, tipografía (según decisión 1); el CSS existente se
   reescribe a tokens sin cambiar el aspecto más de lo debido; prueba que impide colores sueltos nuevos.
2. **Cabecera y barra superior** (escritorio y móvil) y componentes comunes: botón, chip, tarjeta, campo.
3. **Lista de leads y filtros** (tabla, rejilla de filtros, paginación).
4. **Detalle del lead** (cabecera, tarjetas de datos, notas y adjuntos, línea de tiempo).
5. **Dashboard ejecutivo y simulador** (tarjetas de métricas, filtros, copy sin jerga).
6. **Pulido y tema oscuro**: pasada final de contraste, foco y estados vacíos.

Cada tarea declara su meta medible con `python scripts/ui_css_audit.py --json` (antes y después) y se prueba por capturas en la
vista previa local; el humano acepta con su smoke visual en DEV.

## 8. Decisiones del humano (resueltas el 2026-10-22)

1. **Tipografía**: **Plus Jakarta Sans alojada en el propio sitio** (`app/web/static/fonts/PlusJakartaSans-latin.woff2`, licencia SIL
   OFL 1.1 en `OFL.txt`), con `@font-face { font-display: swap; }` y sin pedidos a `fonts.googleapis.com` ni `fonts.gstatic.com`. No se
   usa Inter ni la pila del sistema.
2. **Peso de los títulos**: 800 a 700. *Aplicado.*
3. **Sombras sin brillo turquesa** en botones y tarjetas. *Aplicado.*
4. **Botones en píldora**: se mantienen (es parte de lo que gusta). *Mantenido.*
5. **Barra superior en móvil**: una fila compacta con menú. *Aplicado.*
6. **Texto técnico del dashboard** a lenguaje de negocio. *Aplicado.*
7. **Iconos** (sol/luna del tema, cerrar sesión, exportar XLSX): botones de icono accesibles con `aria-label` y `title`. *Aplicado.*
8. **Tonos de chip**: un tono por estado (neutro, aviso, turquesa, información, pizarra, éxito, peligro). *Aplicado.*
9. **Edad en el listado**: la tabla de leads muestra **Edad** en lugar de RUT; la búsqueda por RUT sigue funcionando y el detalle
   conserva el RUT completo para quien puede verlo.

## 9. Cómo se verifica

- `python scripts/ui_css_audit.py` y pruebas del CSS: las métricas de la sección 2 bajan hacia su meta y no suben.
- Suite existente (`tests/unit`, `tests/integration/test_web_crm_lite.py`, pruebas de seguridad de la web) sin cambios.
- Capturas en escritorio (1440 px), tableta y móvil (390 px), tema claro y oscuro, de la lista, el detalle, el dashboard y el login,
  desde la vista previa local con datos ficticios; las revisa el humano antes de aceptar.
