# Referencia visual aprobada (v1, 2026-10-22)

Esta carpeta guarda **el resultado aprobado por el humano** de la vista previa local del CRM armonizado. Es la fuente exacta de las
tareas `CRM-UI-1-ARMONIA-VISUAL` y `CRM-ESTADOS-1-CATALOGO`: el Developer **no inventa el diseño**, lo reproduce. Se retira de `main` cuando
ambas tareas estén cerradas.

## Qué contiene

| Ruta | Para qué |
|---|---|
| `ui1/app/web/static/css/app.css` | Hoja de estilos final: valores ajustados a las escalas, capa de armonía (tokens, componentes, tonos de chip) y `@font-face` local |
| `ui1/app/web/templates/base.html` | Barra superior (logo, botón de tema sol/luna, salida con icono) sin tipografía externa |
| `ui1/app/web/templates/leads.html` y `leads_board.html` | Lista de leads: sin bajada, exportar con icono, columna Edad en lugar de RUT |
| `ui1/app/web/templates/executive_dashboard.html` | Dashboard: sin la bajada técnica y sin el chip de ambiente repetido |
| `ui1/app/web/templates/lead_detail_panel.html` | Detalle: sin el aviso de la migración 008 y sin el espacio vacío de notas y solicitud original |
| `ui1/edad_en_listado.diff` | Único cambio de código Python de la tarea de interfaz: la edad en la consulta del listado |
| `estados/crm_states.py` | Contrato de los 12 estados (valores, etiquetas, tonos y alias) de `CRM-ESTADOS-1-CATALOGO` |
| `ui1/fonts/` | Tipografía Plus Jakarta Sans (archivo `woff2` del subconjunto latino y su licencia SIL OFL), a copiar a `app/web/static/fonts/` |

## Cómo se generó

La vista previa se construyó a partir del CSS y las plantillas de `main` con `scripts/ui_css_audit.py` como medida de avance, y se
revisó en el navegador (escritorio y móvil, tema claro y oscuro) con datos ficticios. La referencia es la versión de **producción**: la
tipografía va alojada en el propio sitio (la vista previa la cargaba de Google Fonts).

## Cómo se aplica

1. Copiar cada archivo de `ui1/` a su ruta de destino dentro de `app/` (la ruta relativa dentro de `ui1/` es la ruta destino). El
   resultado debe ser **idéntico a la referencia** ignorando diferencias de fin de línea
   (`git diff --no-index --ignore-cr-at-eol <referencia> <destino>` sin diferencias).
2. Aplicar `ui1/edad_en_listado.diff` a `app/repositories/solicitud_repository.py`.
3. Copiar `ui1/fonts/*` a `app/web/static/fonts/`.
4. Actualizar las pruebas que dependan de lo que cambió (textos, columnas, controles de icono) sin debilitarlas.

## Qué NO es

No es un rediseño nuevo ni autoriza cambios de comportamiento: rutas, permisos, enmascarado de datos personales, CSRF y HTMX no cambian. La
refactorización completa del CSS hacia tokens (colores sueltos y reglas de tema oscuro por componente) es una tarea posterior.
