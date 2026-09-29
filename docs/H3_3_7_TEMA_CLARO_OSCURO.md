# H3.3.7 — Tema claro y oscuro para CRM Lite

Cambio de presentacion exclusivamente client-side (clase A). No toca backend, autenticacion,
RBAC, PII, datos, reglas de negocio ni APIs.

## Diseno

| Pieza | Archivo | Comportamiento |
| --- | --- | --- |
| Tema por defecto | `app/web/templates/base.html` | El servidor siempre renderiza `<html data-theme="light">`. Sin JavaScript la app queda en claro. |
| Aplicacion temprana | `app/web/static/js/theme.js` | Script externo sincrono en `<head>`, antes de `app.css`: lee `localStorage["tpi-theme"]` y fija `data-theme` antes del primer pintado (sin destello del tema claro). Archivo same-origin, compatible con una CSP `script-src 'self'`. |
| Control | `base.html` (barra superior, tambien en login) | `<button type="button" data-theme-toggle aria-pressed>` con nombre accesible "Tema oscuro"; `aria-pressed="true"` cuando el oscuro esta activo. Operable con teclado (boton nativo) y fuera de cualquier formulario. |
| Persistencia | `theme.js` | Solo se guardan `light` o `dark`. Valor ausente o invalido => claro. Si `localStorage` no existe o lanza error, el cambio aplica a la pagina actual y la app sigue funcional. Nunca usa cookies ni red. |
| Estilos | `app/web/static/css/app.css`, seccion "Tema claro / oscuro (H3.3.7)" | Los tokens `:root` (tema claro) no cambian. `[data-theme="dark"]` redefine los tokens y sobrescribe las reglas con colores claros fijos (topbar, tarjetas, inputs/select/textarea, tablas, badges de estado, dashboard, detalle, modal, toast). Todas las reglas nuevas estan acotadas a `[data-theme="dark"]` o al propio control. |

Botones rellenos en oscuro usan `--accent-strong` (#0f766e) para que el texto blanco mantenga
contraste; el acento claro (#2dd4bf) queda para texto, lineas y graficos.

## Trazabilidad de criterios

Pruebas en `tests/unit/test_h3_3_7_theme.py` (el comportamiento de `theme.js` se ejecuta en Node con
DOM y storage simulados; en CI Node es obligatorio).

| AC | Evidencia automatizada | Verificacion humana |
| --- | --- | --- |
| AC-1 control visible | `test_every_page_renders_light_by_default_and_the_theme_toggle`, `test_toggle_lives_in_the_topbar_and_outside_any_form` | Si |
| AC-2 oscuro coherente y legible | `test_dark_theme_overrides_hard_coded_light_surfaces`, `test_dark_palette_meets_wcag_contrast`, `test_dark_status_and_alert_colours_are_readable`, `test_dark_filled_buttons_keep_white_labels_readable`, `test_dark_theme_uses_very_dark_backgrounds_and_light_text` | Si |
| AC-3 claro sin regresiones | `test_light_tokens_keep_the_baseline_values`, `test_dark_rules_are_all_scoped_to_the_dark_theme` + suite web existente | Si |
| AC-4 persistencia | `test_toggle_persists_across_reloads`, `test_stored_preference_is_applied_on_load` | No |
| AC-5 claro por defecto | `test_without_preference_the_app_starts_light`, `test_invalid_stored_values_fall_back_to_light`, `test_storage_errors_never_break_the_page` | No |
| AC-6 sin cambios de backend | `test_theme_script_never_talks_to_the_server_or_uses_cookies`; el diff no toca codigo Python de `app/` | No |

Las pruebas automatizadas no sustituyen la revision visual humana de AC-1..AC-3.
