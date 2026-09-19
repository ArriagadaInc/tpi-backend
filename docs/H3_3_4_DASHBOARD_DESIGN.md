# H3.3.4 — Parte B: Diseño del Dashboard Ejecutivo CRM

> Sesión exclusiva de diseño y prototipado. **Cero código productivo.** No se
> implementa Parte B en esta sesión; no se modifica Parte A; no se altera el
> alcance ni las definiciones de `tasks/current.yaml`.

- **Tarea**: H3.3.4 — Historial integral de estados y Dashboard Ejecutivo CRM
- **Fase**: Parte B (Dashboard Ejecutivo), diseño únicamente
- **Estado del Harness**: `DEVELOPING` (sin transición)
- **Worktree**: `.harness-worktrees/H3.3.4-developer-c5e738c`
- **Branch**: `harness/H3.3.4-historial-estados-dashboard-ejecutivo`
- **Skill utilizada**: `anthropic-skills:frontend-design`

---

## 1. Fuentes revisadas

Leídas directamente antes de diseñar (sin inventar estados, datos, relaciones ni
categorías):

- `AGENTS.md`, `CLAUDE.md`, `harness/state.json`, `tasks/current.yaml`
- `docs/H3_3_4_REQUIREMENTS_MATRIX.md` (REQ-B-01..30, AC-10..AC-18, definiciones
  humanas §1)
- `app/web/templates/base.html`, `leads.html`, `leads_board.html`,
  `lead_detail.html`, `lead_detail_panel.html`
- `app/web/static/css/app.css` (tokens y componentes existentes)
- `app/web/dependencies.py`, `app/web/routes/leads.py`, `app/auth/models.py`
  (roles, `is_superuser`, `can_view_full_pii`)
- `app/models/crm_states.py` (`CRM_STATE_CONTRACT`, `CRM_STATE_LABELS`,
  `CRM_STATE_TONES`)
- `docs/H3_3_CRM_LITE_WEB_UX.md`, `docs/H3_3_2_SUPERUSUARIOS_CEO_CTO.md`
- `app/repositories/solicitud_repository.py` (confirma columnas reales
  `fecha_ingreso`, `origen_lead`, `fuente_actual`)

Todos los estados, roles y categorías usados en este diseño provienen
exclusivamente de estas fuentes.

---

## 2. Usuarios y objetivo de negocio

**CEO** — volumen y evolución del negocio, leads sin asignar/estancados, carga
por asesor, problemas operacionales, panorama general.

**CTO** — mismas métricas que el CEO, más cobertura y calidad del dato
(aviso de cobertura histórica), anomalías o inconsistencias (fan-out de joins,
denominadores, estados desconocidos).

Ambos ven exactamente los mismos datos (mismo contrato server-side); la
diferencia es de énfasis de lectura, no de superficie. Esto descarta un diseño
con dos "modos" o dos layouts distintos por rol: **una sola vista**, con la
información de cobertura/calidad siempre visible (no oculta detrás de un modo
"técnico").

---

## 3. Definiciones inmutables (reproducidas, no redefinidas)

Ver `docs/H3_3_4_REQUIREMENTS_MATRIX.md` §1 para el texto canónico. Este
diseño no contradice ni reinterpreta:

- Estancado = 5 días corridos completos sin movimiento operativo (nota
  humana, asignación o cambio general de estado; nunca solo `updated_at`).
- Categorías MVP: estado, asesor, AFP, origen del lead, fuente actual.
  Género y estado civil **no aparecen** en ningún componente del dashboard.
- Cartera activa = `estado_lead NOT IN (cerrado, perdido, no_califica, duplicado)`.
- Primera gestión = primera nota humana o primer cambio general de estado
  (excluye asignación automática); `N/D` si no existe.
- Lead ingresado = `fecha_ingreso` (≠ `created_at`; la diferencia se rotula en
  la UI, no se explica con una nota larga).
- Funnel = solo transiciones observables; leads pre-cutover de la migración
  008 aportan al estado actual, nunca a tasas inventadas.
- Denominadores = `COUNT(DISTINCT id_lead)`.
- Nombre del asesor visible solo para CEO/CTO; nunca RUT/teléfono/correo de
  asesor. Cero PII de leads en cualquier parte del dashboard.

---

## 4. Fase 1 — Propuestas

### A. Resumen ejecutivo

Una sola pantalla, sin scroll operativo profundo: KPIs cardinales, alertas
prioritarias (sin asignar, estancados) y una distribución de estado. Todo lo
demás (asesor, antigüedad, funnel, tiempos) queda en enlaces o acordeones
secundarios.

```text
┌─────────────────────────────────────────────┐
│ Header + nav                                  │
├─────────────────────────────────────────────┤
│ Filtros (período, asesor)                     │
├───────────┬───────────┬───────────┬─────────┤
│ Total     │ Ingresados│ Activa    │ Sin asig│
├───────────┴───────────┴───────────┴─────────┤
│ Alertas: N sin asignar · N estancados         │
├─────────────────────────────────────────────┤
│ Casos por estado (barras horizontales)        │
├─────────────────────────────────────────────┤
│ ▸ Ver antigüedad / asesor / funnel (colapsado)│
└─────────────────────────────────────────────┘
```

### B. Centro de control operacional

Mayor densidad desde el primer scroll: KPIs, evolución, antigüedad,
distribución por categorías, funnel y tabla de asesor **todo expandido y
visible**, sin resumen previo diferenciado. Orientado a un analista que vive
en la pantalla, no a una lectura de 30 segundos.

```text
┌─────────────────────────────────────────────┐
│ Header + nav + filtros extendidos             │
├───────────┬───────────┬───────────┬─────────┤
│ KPI KPI KPI KPI (8 tarjetas en 2 filas)       │
├───────────────────────┬───────────────────────┤
│ Evolución (línea)      │ Antigüedad (barras)   │
├───────────────────────┼───────────────────────┤
│ Estado (barras)        │ AFP / Origen / Fuente │
├───────────────────────┴───────────────────────┤
│ Funnel                                         │
├───────────────────────────────────────────────┤
│ Tabla de asesores (cartera, estado×asesor)     │
└───────────────────────────────────────────────┘
```

### C. Híbrido (resumen arriba, detalle progresivo abajo)

Resumen ejecutivo en el primer scroll (KPIs + alertas + estado), seguido de un
segundo nivel de análisis (evolución, antigüedad, categorías) y un tercer
nivel operacional (funnel, resumen por asesor) siempre visible pero más abajo
— sin acordeones ni pestañas que escondan información al CTO.

```text
┌─────────────────────────────────────────────┐
│ Header + nav                                  │
├─────────────────────────────────────────────┤
│ Filtros (período · asesor · AFP · origen ·    │
│          fuente · estado)                     │
├─────────────────────────────────────────────┤
│ NIVEL 1 — Resumen ejecutivo                   │
│ KPI · KPI · KPI · KPI  |  Alertas operativas  │
├─────────────────────────────────────────────┤
│ Aviso de cobertura histórica (si aplica)      │
├───────────────────────┬───────────────────────┤
│ NIVEL 2 — Análisis                            │
│ Evolución (línea/área) │ Casos por estado      │
├───────────────────────┼───────────────────────┤
│ Antigüedad (ladder)    │ AFP · Origen · Fuente │
├───────────────────────┴───────────────────────┤
│ Funnel y tasas observables                     │
├─────────────────────────────────────────────┤
│ NIVEL 3 — Operacional                         │
│ Resumen por asesor (cartera, estado×asesor,   │
│ tiempos de asignación/primera gestión)         │
└─────────────────────────────────────────────┘
```

### Comparación

| Criterio | A. Resumen ejecutivo | B. Centro de control | C. Híbrido |
| --- | --- | --- | --- |
| Jerarquía visual | Muy clara, un solo foco | Plana, todo compite | Clara, en 3 niveles explícitos |
| Claridad | Alta para lectura de 30s | Media (sobrecarga inicial) | Alta en cada nivel |
| Densidad | Baja (detalle oculto) | Muy alta | Media, creciente por nivel |
| Valor para CEO | Alto de entrada, bajo si necesita detalle | Bajo (ruido antes del dato clave) | Alto: lee nivel 1 y se detiene, o sigue |
| Valor para CTO | Bajo: cobertura/calidad queda oculta en acordeones | Alto (todo a la vista) | Alto: nivel 2/3 sin fricción de clics |
| Escalabilidad (nuevas métricas) | Mala (todo lo nuevo compite por el mismo espacio "resumen") | Buena pero agrava la densidad | Buena: cada métrica nueva entra en su nivel |
| Comportamiento móvil | Bueno (poco contenido) | Malo (tablas y grillas muy anchas) | Aceptable con colapso progresivo por nivel |
| Ventajas | Rápido de leer, bajo riesgo de errores de interpretación | Ningún dato a más de un scroll | Un solo modelo mental para ambos roles; no esconde información al CTO detrás de un clic |
| Desventajas | Oculta justo lo que el CTO necesita (cobertura, antigüedad, funnel) | Se parece a un tablero de BI genérico; alto costo cognitivo inicial | Requiere más scroll que A para llegar al detalle |

### Alternativa recomendada: **C — Híbrido**

Justificación: el CEO y el CTO comparten el mismo contrato de datos y el
mismo nivel de acceso (ambos superusuarios); no hay razón de negocio para
esconder cobertura, antigüedad o funnel detrás de un acordeón como en A —
eso penalizaría exactamente el objetivo del CTO ("comprobar limitaciones
históricas", "detectar anomalías"). Al mismo tiempo, un dashboard sin
jerarquía (B) obliga a ambos roles a escanear la misma densidad para llegar
a los cuatro números que el CEO revisa primero. El híbrido resuelve ambos
casos: la lectura de 30 segundos del CEO termina en el nivel 1 sin necesidad
de interacción, y el CTO sigue bajando sin clics adicionales para llegar a
calidad de dato y detalle operacional. Además, este orden (resumen → análisis
→ operación) es el mismo principio que ya usa `lead_detail_panel.html`
(hero → estado → info → seguimiento), manteniendo coherencia con el patrón
de lectura del CRM existente.

---

## 5. Fase 2 — Arquitectura visual (alternativa C)

| # | Elemento | Pregunta de negocio | Métrica | Dimensión | Visualización | Prioridad | Interacción | Responsive | Equivalente accesible | Razón de diseño |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Encabezado y navegación | ¿Dónde estoy y quién soy? | — | — | Reutiliza `.topbar` de `base.html` + entrada de nav "Dashboard Ejecutivo" | Alta | Ninguna (estático) | Se apila igual que hoy bajo 800px | N/A (ya accesible: `role="banner"`) | Cero aprendizaje nuevo: mismo header que Leads |
| 2 | Barra de filtros | ¿Qué período/corte quiero ver? | — | período, asesor, AFP, estado, origen, fuente | `<form>` con `<select>`/`<input date>`, mismo patrón que `.filters-grid` de `leads.html` | Alta | Combinables, aplican por GET (recargable/enlazable); sin JS obligatorio | Colapsa a 1 columna bajo 800px igual que `leads.html` | Labels asociados por `for`/`id`; `fieldset`/`legend` para agrupar | Reutiliza el único patrón de filtros que ya conoce el usuario del CRM |
| 3 | Primera fila de KPIs | ¿Cuánto negocio hay y cuánto entró en el período? | total leads, ingresados (`fecha_ingreso`), cartera activa, sin asignar | — | Tarjetas KPI (`.kpi-card`) con período explícito en el subtítulo | Alta | Ninguna (los filtros del punto 2 las recalculan) | Grid de 4→2→1 columnas | Cada tarjeta es `<dl>` (`<dt>` etiqueta, `<dd>` valor), leíble por lector de pantalla sin depender del layout visual | Un número sin período es ambiguo; el período va impreso en la tarjeta, no en un tooltip |
| 4 | Alertas operacionales | ¿Hay algo que requiera acción hoy? | leads sin asignar, leads estancados (con umbral) | — | Chips de alerta con ícono textual (no solo color) + texto explícito ("N leads sin asignar hace más de X días") | Alta | Cada chip enlaza (ancla) a la sección de detalle correspondiente (antigüedad o asesor) | Se apilan verticalmente en móvil | Texto autosuficiente sin el color (nunca "●" solo) | El objetivo explícito del CEO es "detectar leads sin asignar o estancados": esto va antes de cualquier gráfico |
| 5 | Distribución por estado | ¿Cómo se reparte la cartera entre estados? | `COUNT(DISTINCT id_lead)` por estado | estado (13 valores del contrato) | Barras horizontales, un único color de marca, ordenadas por volumen descendente, con conteo y % (con denominador visible) | Alta | Click/enter en una barra aplica el filtro de estado (mismo patrón que un link) | Lista vertical siempre (nunca tabla ancha) | `<table>` oculta visualmente (`.sr-only`) con los mismos datos, o lista `<ul>` con `aria-label` | 13 categorías descartan un donut (ilegible) y descartan color-por-categoría (13 colores no son distinguibles ni memorizables) |
| 6 | Evolución temporal | ¿El volumen sube, baja o se estanca? | ingresos por `fecha_ingreso` | diario / semanal / mensual (selector) | Línea/área simple server-rendered (SVG), un solo color, sin relleno degradado | Alta | Selector de granularidad (diario/semanal/mensual); hover muestra valor exacto vía `<title>` SVG nativo | Altura fija, ancho fluido (`viewBox`); en móvil se reduce el número de marcas de eje, no el gráfico | `<table>` con fecha/valor equivalente, visualmente oculta | Serie temporal simple no necesita 3D, animación ni librería: SVG + `<polyline>` es suficiente y accesible |
| 7 | Antigüedad | ¿Qué tan vieja es la cartera abierta? (elemento distintivo) | `COUNT(DISTINCT id_lead)` por bucket | 0-2, 3-7, 8-15, 16-30, +30 días corridos | "Escalera de antigüedad": 5 barras horizontales apiladas de arriba (más nuevo) a abajo (más viejo), con intensidad de borde creciente hacia el bucket +30 (nunca color como único significado: cada barra lleva el rango y el conteo en texto) | Alta | Click en un bucket filtra la tabla de asesor por ese rango | Se mantiene vertical en todos los anchos (ya es 1 columna) | `<table>` con bucket/conteo/porcentaje | Es el elemento señal del diseño: conecta antigüedad con estancamiento sin duplicar el concepto de "estancado" (que es un umbral operativo distinto, ver alertas) |
| 8 | Distribución por categorías | ¿De dónde viene la cartera? | `COUNT(DISTINCT id_lead)` | AFP, origen del lead, fuente actual (3 listas) | 3 listas de barras horizontales cortas (top categorías), mismo estilo que el punto 5 | Media | Ninguna obligatoria; opcionalmente enlazan al filtro correspondiente | 3 columnas → 1 columna apilada bajo 1024px | Igual patrón de tabla oculta que el punto 5 | Estado, AFP, origen y fuente son las únicas categorías MVP: se muestran con el mismo lenguaje visual para que "categoría" sea reconocible como un concepto único en toda la pantalla |
| 9 | Funnel | ¿Dónde se cae la conversión? | tasas de transición observables | etapas observables del contrato de estados | Barras horizontales decrecientes con la tasa impresa junto al conteo (`origen → destino: 42% (n=118/280)`) | Media (condicional a cobertura) | Ninguna | Igual que el punto 5 | `<table>` con etapa/conteo/tasa/base | Se oculta o se reemplaza por el aviso de cobertura cuando la cobertura pre-cutover es insuficiente: nunca se inventa una tasa |
| 10 | Resumen por asesor | ¿Cómo está repartida la carga y dónde hay riesgo por asesor? | cartera total, cartera activa, casos por estado, tiempo a asignación, tiempo a primera gestión | asesor (nombre visible solo CEO/CTO) | Tabla con encabezados ordenables (cartera total, activa, estancados, tiempo medio) — mismo componente visual que `.board-table` | Alta | Orden por columna (por `<a>` en el `<th>`, sin JS obligatorio: recarga con `?sort_by=`) | `.table-wrap` con `overflow-x:auto` (igual patrón que `leads_board.html`), nunca recorta filas | Encabezados con `scope="col"`; orden actual anunciado con `aria-sort` | Reutiliza el único patrón de tabla que ya existe en el CRM; evita crear un segundo lenguaje visual de tablas |
| 11 | Aviso de cobertura | ¿Desde cuándo son confiables el funnel y los tiempos? | fecha de cutover de la migración 008 | — | Banner informativo (`.notice-soft`), no un ícono suelto | Alta (para el CTO) | Ninguna | Ancho completo, texto que hace wrap normal | Es texto plano, ya accesible | Es requisito explícito (AC-15) que la cobertura sea visible y honesta, no un tecnicismo escondido |
| 12 | Estados vacíos y de error | ¿Qué veo si no hay datos, hay un filtro sin resultados o falla una consulta? | — | — | Reutiliza `.empty-state` (cero datos) y `.alert-error` (error parcial) ya existentes en `leads_board.html`/`lead_detail.html` | Alta | El estado de error indica qué sección falló sin ocultar las demás que sí cargaron | Igual que el resto de la página | Mensaje de texto explícito, nunca solo un ícono | Consistencia: el CRM ya resuelve esto para leads; el dashboard no necesita un lenguaje nuevo |

---

## 6. Visualizaciones: criterio aplicado

**Usadas** (todas justificadas arriba): tarjetas KPI con período explícito;
barras horizontales para estado, antigüedad y categorías; línea/área simple
para evolución; tabla con jerarquía y orden para asesores; alertas con texto
+ enlace; funnel condicionado a cobertura.

**Explícitamente evitadas y por qué**:

- Gráficos 3D / velocímetros: no aportan precisión, sí ambigüedad de lectura
  a distancia (proyección/ángulo).
- Donuts con muchas categorías: el contrato tiene 13 estados; un donut de 13
  porciones es ilegible y obliga a una leyenda aparte.
- Color como único significado: cada barra/celda lleva texto (nombre,
  conteo, %); el color nunca es la única señal (aplica también a los tonos
  ya definidos en `CRM_STATE_TONES`, que en el dashboard se usan como
  *acento* de la fila, no como codificación exclusiva).
- Gradientes decorativos y animaciones: el único gradiente con significado
  es el de intensidad de borde en "Antigüedad" (punto 7), que codifica
  urgencia real, no decoración.
- Tablas excesivamente anchas: todas las tablas usan `.table-wrap` con
  scroll horizontal contenido, igual que `leads_board.html`.
- Rankings que confunden carga con desempeño: el resumen por asesor separa
  "cartera activa" (carga) de "tiempo a primera gestión" (velocidad de
  respuesta) en columnas distintas, nunca en un único "score".
- Porcentajes sin denominador / falsa precisión: todo porcentaje se imprime
  junto al par `n/base` (`42% (118/280)`), sin decimales más allá de lo que
  el tamaño de muestra justifica.

---

## 7. Decisión técnica de gráficos

| Criterio | A. HTML/CSS + SVG server-rendered | B. Librería JS liviana vendida localmente | C. Librería vía CDN |
| --- | --- | --- | --- |
| Seguridad | Sin JS de terceros; superficie de ataque mínima | Requiere auditar y fijar versión del vendor local | Depende de disponibilidad e integridad de un host externo en cada carga |
| CSP | Compatible con una CSP estricta (`script-src 'self'`) sin excepciones | Compatible si se vendoriza bajo `'self'` | Exige agregar el dominio del CDN a `script-src`, debilitando la CSP |
| Accesibilidad | `<table>` semántica siempre disponible como fuente única (el SVG es una proyección de la misma tabla) | Depende de que la librería exponga buenas etiquetas ARIA; variable entre librerías | Igual que B, más el riesgo de que una versión futura del CDN cambie el comportamiento sin control de despliegue |
| Bundle | Cero KB adicionales (Jinja + SVG inline) | Aumenta el peso de `app/web/static/js/` (hoy 47 líneas) | Cero peso local, pero dependencia de red en cada carga |
| Mantenimiento | Vive en el mismo lenguaje que el resto del backoffice (Python/Jinja); un solo stack que mantener | Nueva dependencia de terceros a versionar y actualizar | Nueva dependencia externa fuera del control de versión del repo |
| Pruebas | Testeable como cualquier otro render Jinja (`pytest` + parseo de HTML), igual que el resto del backoffice | Requiere pruebas de integración JS o mocks adicionales | Igual que B, más el riesgo de que el test dependa de una CDN real o de un mock adicional |
| Responsive | `viewBox` + CSS puro; se comporta igual que cualquier otro bloque del layout | Depende de la librería (la mayoría lo resuelve, pero agrega su propio sistema de contenedores) | Igual que B |
| Integración FastAPI/Jinja | Nativa: el servidor ya calcula agregados: el mismo dato que arma el HTML arma el SVG | Requiere serializar los agregados a JSON e inicializar la librería en el cliente | Igual que B, con una capa de red adicional |
| JS requerido | Ninguno para renderizar los gráficos (JS opcional solo para filtros interactivos no obligatorios) | Sí, para cada gráfico | Sí, para cada gráfico, más la carga del script externo |

### Recomendación: **A — HTML/CSS + SVG server-rendered**

Los gráficos que exige Parte B (barras, línea/área simple, tabla) no
requieren zoom, tooltips ricos ni brushing: son exactamente el caso de uso
para el que SVG generado en el servidor es suficiente y superior en
seguridad, CSP y mantenimiento. No se recomienda C (CDN) salvo excepción
demostrable, y no aplica aquí: no hay ninguna visualización de Parte B que
una librería JS resuelva y SVG server-rendered no pueda. Si en una iteración
futura se necesitara interacción rica (zoom en la serie temporal, tooltips
dinámicos), la ruta sería B (librería vendorizada localmente bajo
`app/web/static/js/vendor/`, nunca CDN), evaluada en ese momento con datos
reales de necesidad, no de forma especulativa ahora.

Nota de contexto: `base.html` ya carga `htmx` desde `unpkg.com` (CDN
existente, anterior a esta tarea). Esta decisión no lo reemplaza ni lo
valida como precedente para los gráficos; es una dependencia previa fuera
del alcance de H3.3.4 y no se propone repetir ese patrón para Parte B.

---

## 8. Sistema visual: tokens y estilo reutilizados

Ninguna variable ni componente nuevo reemplaza al existente. Se reutiliza
`app/web/static/css/app.css` tal cual:

- Color: `--bg`, `--surface`, `--surface-soft`, `--surface-muted`, `--text`,
  `--muted`, `--border`, `--primary`, `--accent` (`#0d9488`, ya es el color
  de marca del CRM), `--accent-soft`, `--success`, `--warning`, `--info`,
  `--slate`, más `#dc2626` (danger, ya usado por `.danger`/`.alert-error`).
- Radios: `--radius` (22px, tarjetas grandes), `--radius-sm` (14px,
  controles).
- Sombra: `--shadow` (tarjetas), sombra suave existente en `.info-card-v2`
  para tarjetas KPI.
- Tipografía: Inter (ya cargada), `.mono`/`font-variant-numeric: tabular-nums`
  para todas las cifras del dashboard (igual que `saldo_afp` en
  `leads_board.html`).
- Layout: `.page-shell`, `.card`, `.filters`/`.filters-grid`, `.table-wrap`,
  `.board-table`, `.empty-state`, `.notice`/`.alert-error`, `.pill`/`.pill-accent`.
- Navegación: mismo `.topbar` de `base.html`, con un nuevo `<a>` de
  navegación ("Dashboard Ejecutivo") visible solo cuando el rol es CEO/CTO
  (la ausencia del enlace para otros roles es una consecuencia de datos, no
  el control de acceso: el control real es 403 server-side, ver REQ-B-02).

### Extensiones necesarias (nuevas clases, mismo lenguaje)

Estas clases **no existen aún**; se documentan aquí como especificación para
la implementación futura, no se crean en `app.css` en esta sesión (fuera de
alcance de una sesión de diseño):

- `.kpi-grid` / `.kpi-card`: grid de 4 columnas → 2 → 1, mismo radio/sombra
  que `.info-card-v2`.
- `.alert-chip`: variantes `.alert-chip--warning` (sin asignar) y
  `.alert-chip--danger` (estancados), reutilizando la paleta de
  `.status-badge.perdido` (rojo) y `.status-badge.citado` (ámbar/azul según
  corresponda) para no introducir tonos nuevos.
- `.bar-list` / `.bar-row` / `.bar-track` / `.bar-fill`: barras horizontales
  de estado/AFP/origen/fuente, un único color de relleno (`--accent`).
- `.age-ladder` / `.age-step`: la "escalera de antigüedad" (elemento
  distintivo, punto 7), con `border-left` de intensidad creciente usando
  `--warning` → `#dc2626` en 5 pasos, nunca como único portador de
  información.
- `.timeseries` (contenedor del SVG de evolución) + `.timeseries-table`
  (equivalente accesible, `.sr-only` u oculto por defecto con alternancia
  "ver como tabla").
- `.funnel-list` / `.funnel-row`: mismo patrón que `.bar-list` con la tasa
  impresa a la derecha.
- `.coverage-banner`: alias semántico de `.notice-soft` para el aviso de
  cobertura (punto 11), sin cambiar su apariencia.

Ninguna de estas clases reemplaza componentes existentes; todas heredan
color, radio, tipografía y espaciado de las variables ya definidas.

---

## 9. Accesibilidad (WCAG AA)

- Contraste verificado contra los tokens existentes: `--text` (#0f172a)
  sobre `--surface`/`--bg` ≈ 17.9:1; `--muted` (#64748b) sobre blanco ≈
  4.6:1 (AA para texto normal); `--accent` (#0d9488) sobre blanco ≈ 3.9:1,
  por lo que **nunca se usa `--accent` como color de texto de cuerpo**, solo
  como relleno de barra o fondo con texto oscuro encima (mismo criterio que
  ya aplica `.btn-primary-simulator`, que usa texto blanco sobre `--accent`
  a tamaño de botón, no de párrafo).
- Foco visible: se reutiliza el `box-shadow` de foco ya definido en
  `input:focus, select:focus`; todo control nuevo (enlaces de barra,
  encabezados ordenables, chips de alerta) es un elemento nativo (`<a>`,
  `<button>`) para heredar el foco del navegador sin re-implementarlo.
- Navegación por teclado: filtros, orden de tabla y enlaces de alerta son
  formularios/enlaces reales (sin `div` con `onclick`); el orden de tabulación
  sigue el orden visual (nivel 1 → 2 → 3).
- Contenido comprensible sin color: cada barra, chip y celda lleva su
  etiqueta y valor en texto; el color es siempre un refuerzo, nunca la única
  vía (aplica en particular a `.age-ladder` y a los tonos heredados de
  `CRM_STATE_TONES`).
- Equivalente accesible de cada gráfico: tabla de datos subyacente, oculta
  visualmente (no con `display:none`, para que lectores de pantalla la
  lean) o revelable con un control "Ver como tabla".
- Español, formato chileno: fechas `dd/mm/aaaa` (igual que
  `lead_detail_panel.html`), separador de miles `.` y decimales `,`
  (mismo criterio que `format_currency_clp`), sin mezclar formato `en-US`.
- `prefers-reduced-motion`: el diseño no depende de animación para
  comunicar nada (ninguna transición es portadora de información); se
  hereda la regla existente de transiciones cortas en botones y se añadirá
  `@media (prefers-reduced-motion: reduce)` para anularlas por completo en
  la implementación.
- Sin fuentes externas obligatorias (Inter con fallback del sistema, igual
  que hoy) y sin imágenes decorativas.

---

## 10. Responsive

Reutiliza los quiebres ya existentes en `app.css` (`1200px`, `800px`) y
agrega los puntos de verificación pedidos:

| Viewport | Comportamiento |
| --- | --- |
| 375×812 (móvil) | KPIs en 1 columna; alertas apiladas; barras de estado/antigüedad/categorías a ancho completo; tabla de asesor con scroll horizontal contenido (`.table-wrap`); filtros en 1 columna (igual que `leads.html` bajo 800px) |
| 768×1024 (tablet vertical) | KPIs en 2 columnas; categorías (AFP/origen/fuente) en 1 columna; evolución y estado se apilan |
| 1024×768 (tablet horizontal / notebook chico) | KPIs en 2-4 columnas según ancho real; evolución y estado lado a lado; categorías en 2 columnas |
| 1440×900 (escritorio) | Layout completo de la Fase 2: KPIs en 4 columnas, evolución+estado y antigüedad+categorías lado a lado, funnel y tabla de asesor a ancho completo |

No se introduce ningún `min-width` mayor al viewport más chico soportado;
las únicas cajas con overflow permitido son `.table-wrap` (tabla de asesor) y
el contenedor del SVG de evolución, ambas con `overflow-x: auto` contenido,
igual que el patrón ya usado en `leads_board.html`.

---

## 11. Prototipo

- **Archivo**: `docs/prototypes/H3_3_4_dashboard_prototype.html`
- HTML autocontenido, sin build step, sin CDN, sin llamadas de red, sin
  autenticación, sin PII (nombres/AFPs/asesores sintéticos, marcados como
  tales).
- Banner permanente "PROTOTIPO — DATOS SINTÉTICOS" en el encabezado.
- Controles de demostración (no conectados a ninguna ruta real) para
  alternar entre 4 estados: **Normal**, **Cero datos**, **Error parcial**,
  **Cobertura histórica limitada** — implementados con un atributo
  `data-demo-state` en `<body>` y CSS/objetos de datos ya embebidos (sin
  `fetch`).
- Reproduce los 12 elementos de la Fase 2 con la alternativa C.
- No queda enlazado a ninguna ruta de `app/web/routes/`; es un archivo
  estático de documentación.

---

## 12. Revisión visual

**Limitación de herramientas de esta sesión**: no hay navegador ni
herramienta de captura de pantalla disponible en este entorno de diseño, por
lo que no fue posible tomar capturas reales de los 4 viewports. La revisión
se realizó de forma **estática**, sobre el código del prototipo:

- Overflow: verificado que ningún selector define `min-width` mayor a
  `320px` fuera de `.table-wrap`/`.timeseries-scroll`; el `viewBox` del SVG
  de evolución es proporcional (`preserveAspectRatio="none"` sobre un
  contenedor de altura fija), por lo que no puede desbordar horizontalmente.
- Clipping: `overflow: hidden` solo se usa en contenedores que también
  definen `border-radius` (tarjetas), nunca sobre contenido de texto que
  pueda truncarse sin indicarlo.
- Contraste: recalculado para cada combinación texto/fondo nueva
  introducida por el prototipo (chips de alerta, pasos de la escalera de
  antigüedad); todas ≥ 4.5:1 para texto normal o ≥ 3:1 para texto grande
  (encabezados de KPI).
- Foco: todo elemento interactivo del prototipo (toggle de estado de demo,
  enlaces de las barras) es `<button>`/`<a>` nativo; no se removió el
  `outline` del navegador en ningún selector.
- Textos largos: nombres de asesor y AFP sintéticos incluyen un caso de
  nombre largo para verificar `text-overflow`/wrap en la tabla y en las
  barras de categoría.
- Tablas: la tabla de asesores usa `.table-wrap` con scroll horizontal
  contenido; se verificó que en 375px no fuerza scroll de la página
  completa (`overflow-x: hidden` en `body`, `overflow-x: auto` solo en el
  contenedor de tabla).
- Foco de filtros y comportamiento de filtros: los controles de filtro del
  prototipo son elementos de formulario reales; al no haber backend, no
  disparan navegación, pero se verificó que son alcanzables por teclado en
  el orden correcto.
- Estados vacíos/error: verificados visualmente en el código para los 3
  estados alternativos (cero datos, error parcial, cobertura limitada),
  confirmando que cada uno reemplaza únicamente la sección afectada y no
  oculta el resto del dashboard (excepto "cero datos", donde por definición
  no hay nada que mostrar en ninguna sección basada en conteos).

### Hallazgos y cambios de la ronda 1

1. **Hallazgo**: en el primer borrador, `.age-ladder` usaba únicamente el
   color del borde para diferenciar los 5 buckets, sin refuerzo textual
   suficiente para el bucket "+30" (solo un símbolo "▲"). **Cambio**: se
   reemplazó el símbolo por el texto completo "Prioridad alta" junto al
   conteo, eliminando cualquier dependencia del color para entender el
   riesgo.
2. **Hallazgo**: los porcentajes del funnel se mostraban sin el par
   `n/base`, lo que viola el criterio "porcentajes sin denominador".
   **Cambio**: se agregó `(n/base)` a cada tasa del funnel y de las listas
   de categorías.

No fue necesaria una segunda ronda: tras aplicar estos dos cambios, la
revisión estática no encontró incumplimientos adicionales de la lista de
verificación anterior. Se recomienda una verificación humana en navegador
real (los 4 viewports) antes de considerar el diseño definitivo para
implementación.

---

## 13. Próximos pasos para implementar Parte B

Fuera de alcance de esta sesión (solo documentado como referencia para la
siguiente sesión de desarrollo):

1. Router `app/web/routes/dashboard.py` con dependencia server-side
   `require_executive_access` (403 real para cualquier rol que no sea
   `ceo`/`cto`, incluido anónimo).
2. Capa de agregación en `SolicitudService`/`SolicitudRepository` para cada
   métrica de la Fase 2 (KPIs, evolución, antigüedad, categorías, funnel,
   resumen por asesor, tiempos), reutilizando `COUNT(DISTINCT id_lead)` como
   denominador único.
3. Plantilla `app/web/templates/executive_dashboard.html` + parciales por
   sección, siguiendo la Fase 2 y las clases documentadas en §8.
4. Extensión de `app/web/static/css/app.css` con las clases de §8 (sin
   modificar las existentes).
5. Suite de pruebas automatizadas por REQ-B (ver
   `docs/H3_3_4_REQUIREMENTS_MATRIX.md` §4) para cero datos, límites de
   fecha, filtros combinados, estados desconocidos, leads sin asesor y
   fan-out de joins.
6. Smoke humano en AWS DEV (AC-18) incluyendo el 403 real para roles no
   autorizados.

---

## 13 bis. Aclaraciones factuales tras la implementación

Registradas en la sesión de interfaz productiva. No cambian el diseño aprobado
(alternativa C) ni ninguna definición; sólo precisan cómo quedó implementado.

| Punto del diseño | Aclaración factual |
| --- | --- |
| §8 `.funnel-list` / `.funnel-row` | No fueron necesarias: el funnel reutiliza `.bar-list`/`.bar-row`, que es el mismo lenguaje visual que §6 ya describe para las barras horizontales. No se creó una segunda familia de clases equivalente. |
| §8 `.coverage-banner` | Implementada como alias semántico de `.notice-soft`, tal como se especificó, sin cambiar su apariencia. |
| §5 punto 6 y §9 "equivalente accesible" | La tabla equivalente de cada gráfico se expone con un `<details>` nativo ("Ver como tabla") en lugar de una tabla oculta con `.sr-only`, para que la alternancia no dependa de JavaScript y la tabla sea alcanzable también visualmente. |
| §5 punto 5 "click en una barra aplica el filtro" | Implementado sólo para **casos por estado**, donde el valor del filtro es reproducible. Las barras de AFP/origen/fuente no enlazan: el filtro de AFP usa el id del catálogo (ausente en el agregado) y los buckets `Sin origen`/`Sin fuente` son etiquetas sintetizadas sin valor filtrable. Se prefirió no enlazar antes que crear un enlace decorativo. |
| §5 punto 10 "encabezados ordenables" | No implementado en esta iteración: la tabla de asesores se sirve en el orden reproducible del repositorio (cartera total descendente, luego nombre). El orden por columna queda como mejora posible, no como alcance diferido de un requisito: ningún AC exige ordenamiento interactivo. |
| §5 punto 2 "período" | El selector de período del prototipo se implementó como dos campos de fecha explícitos más enlaces de rango rápido que el servidor resuelve a fechas concretas, de modo que toda URL es reproducible. |
| §7 nota sobre el CDN de htmx | Sigue vigente y fuera de alcance: `base.html` continúa cargando htmx desde `unpkg.com`. La Parte B no agregó ninguna dependencia externa; los gráficos son SVG generados en el servidor. |
| §12 revisión visual | En la sesión de implementación sí hubo navegador. Se auditaron los cuatro viewports (0 px de overflow global en todos) y se capturaron 1440×900 y 375×812; la captura del panel resultó intermitente con viewports altos, por lo que la comparación pixel a pixel queda en el checklist humano (`docs/H3_3_4_REQUIREMENTS_MATRIX.md` §12.10). |

---

## 14. Confirmaciones

- Cero código productivo modificado o creado en esta sesión.
- Cero acceso a AWS/RDS en esta sesión.
- Cero transición de Harness ejecutada; `STATE` permanece `DEVELOPING`.
- Cero cambio de alcance, de definiciones humanas o de AC-10..AC-18.
- Parte A no fue tocada.
