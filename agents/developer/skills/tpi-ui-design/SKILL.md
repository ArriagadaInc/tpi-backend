---
name: tpi-ui-design
role: developer
load_when: "DEVELOPING cuando la tarea toca la interfaz del CRM: app/web/static/css/**, app/web/templates/** o el aspecto de una pantalla"
sources: [h33_web_ux]
---

# tpi-ui-design

## 1. Cuando se carga
Cualquier cambio de presentacion del backoffice (`app/web/`): CSS, plantillas Jinja, clases, textos de pantalla, tema claro/oscuro
o responsive. Complementa `docs/UI_DESIGN_SYSTEM.md`, que es la fuente de tokens, componentes y metas: **leelo completo antes de
tocar nada**. Si la tarea no menciona este skill, igual aplica a todo cambio visual.

## 2. Puede
- Reescribir el CSS para que use tokens y los componentes canonicos de la seccion 5 del documento de diseno.
- Agregar tokens a `:root` y su version en `[data-theme="dark"]`, y fusionar valores casi iguales en el paso de la escala mas cercano.
- Cambiar clases y estructura HTML solo para reutilizar un componente existente o para cumplir el patron del componente.
- Mejorar textos de pantalla a lenguaje de negocio (las frases nuevas se listan en la evidencia para aprobacion del humano).
- Agregar pruebas del CSS y de las plantillas (por ejemplo, que no haya colores sueltos nuevos fuera de los bloques de tokens).

## 3. No puede
- Cambiar comportamiento: rutas, permisos, enmascarado de PII, CSRF, HTMX, consultas, mensajes de error de negocio.
- Poner colores, tamanos, radios, sombras o espaciados sueltos; usar `style=""` o `!important`.
- Crear una clase nueva si un componente existente resuelve el caso, ni dejar dos formas de hacer lo mismo.
- Agregar dependencias, CDN, scripts, fuentes o imagenes externas (si la tarea pide una fuente, va como archivo estatico propio
  solo si la decision del humano esta en la tarea).
- Romper el tema oscuro, el foco visible, el contraste AA o el uso en 360 px de ancho sin scroll horizontal.
- Mostrar nombres de campos, variables o jerga tecnica en pantalla.

## 4. Precondiciones
- `docs/UI_DESIGN_SYSTEM.md` leido (secciones 4, 5 y 6) y la meta de la tarea escrita en cifras con `python scripts/ui_css_audit.py`.
- Medir la linea base ANTES de editar: `python scripts/ui_css_audit.py --json` (guardar la salida en la evidencia).
- Revisar `app/web/static/css/app.css` y `app/web/templates/` con busquedas (`grep`) del componente que vas a tocar, para no
  duplicarlo ni dejar usos huerfanos.

## 5. Comandos y herramientas
- Auditoria: `python scripts/ui_css_audit.py` (compara con la linea base; ninguna metrica sube).
- Calidad: `python -m ruff check app/ tests/ scripts/`, `python -m black --check app/ tests/ scripts/`.
- Pruebas: `python -m pytest tests/unit tests/integration/test_web_crm_lite.py -q` y las pruebas de seguridad de la web.
- Trabaja por tokens y por componente, en pasos chicos; tras cada paso corre la auditoria y las pruebas.
- Tu no ves la pagina renderizada: no afirmes que algo "se ve bien". Declara que la verificacion visual es de Claude (capturas en
  la vista previa local) y del humano (smoke en DEV), y entrega el listado de pantallas y componentes tocados para que lo revisen.

## 6. Evidencia obligatoria
- Auditoria antes y despues (`--json`), con las metas de la tarea cumplidas.
- Listado de componentes y pantallas tocadas, de clases eliminadas y de clases nuevas (con su justificacion).
- Listado de textos de pantalla cambiados.
- Resultado de ruff, black y de las pruebas anteriores, y confirmacion de que no cambian rutas, permisos ni consultas.

## 7. STOP
- Para cumplir la meta hay que cambiar comportamiento, estructura de datos o permisos.
- La tarea necesita una dependencia, fuente o recurso externo no autorizado.
- Un valor de la escala del documento de diseno no sirve para un caso real: propone la excepcion por escrito en la evidencia,
  no inventes un valor suelto.
- Un DENIED del guard es definitivo: detente y reporta.

## 8. Fuentes
- `docs/UI_DESIGN_SYSTEM.md` (direccion, linea base, tokens, componentes, plan y decisiones del humano).
- `docs/H3_3_CRM_LITE_WEB_UX.md` (contexto de la interfaz del CRM) y `app/web/static/css/app.css`.
- `scripts/ui_css_audit.py` (metricas de armonia).
