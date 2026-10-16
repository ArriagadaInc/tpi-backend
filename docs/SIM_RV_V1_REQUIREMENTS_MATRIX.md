# Matriz de requisitos — SIM-RV-V1 (Simulador de renta vitalicia en el CRM con PDF efímero)

Este documento es la matriz de trazabilidad de la tarea `SIM-RV-V1`: cada criterio de aceptación (AC) se mapea a su
componente, a las pruebas que lo cubren y a la evidencia que lo demuestra. La tabla de rangos validados y la matriz de
contenido del PDF están en las secciones finales.

## 1. Componentes

| Componente | Ruta | Rol |
|---|---|---|
| Motor puro | `app/simulador_pension/` | Cálculo numérico sin I/O ni importaciones de `app` |
| Tablas de mortalidad | `app/simulador_pension/datos/tablas_mortalidad.npz` | Datos CMF 2020 versionados (package-data) |
| Servicio | `app/services/simulador_service.py` | Orquestación: autorización, escenario, PDF, auditoría, código de verificación |
| Escritor de auditoría | `app/services/simulador_auditoria.py` | INSERT append-only en `tpi.auditoria` |
| Rutas web | `app/web/routes/simulador.py` | GET formulario + POST PDF, CSRF, validación Pydantic |
| Plantillas | `app/web/templates/simulador.html`, `simulador_panel.html` | Formulario y panel del detalle |
| Registro de rutas | `app/web/main.py` | `include_router(simulador_router)` |

## 2. Trazabilidad AC → componente → prueba → evidencia

| AC | Descripción breve | Componente | Prueba | Verificación |
|---|---|---|---|---|
| AC-1 | Solo executive/ceo/cto; 403 real para el resto; anónimo → login | `app/web/routes/simulador.py` (`SimuladorService.can_simulate`) | `tests/unit/test_sim_rv_web.py::test_panel_visible_solo_para_executive_y_superusuarios`, `test_rol_no_autorizado_recibe_403`, `test_anonimo_redirige_a_login` | automated + human (smoke AC-19) |
| AC-2 | Lead concreto bajo `/leads/{id}/simulador`; 404 si inexistente/no visible | `app/web/routes/simulador.py` (resuelve con `get_solicitud_detalle_masked`) | `tests/unit/test_sim_rv_web.py::test_lead_no_visible_404` | automated |
| AC-3 | Formulario precarga sexo/nacimiento; campos por escenario; fecha del servidor | `app/web/routes/simulador.py`, `simulador.html` | `tests/unit/test_sim_rv_web.py::test_formulario_precarga_sexo_y_fecha` | automated + human |
| AC-4 | Alcance V1 exacto; rechazos con 422 y mensaje claro | `app/simulador_pension/api.py` (`NoValidadoError`), `simulador_service.py` | `tests/unit/test_sim_rv_validacion.py` | automated |
| AC-5 | Motor puro, datos versionados en el paquete; 435/435 ±1 UF | `app/simulador_pension/`, `pyproject.toml` (package-data) | `tests/unit/test_sim_rv_regresion_portal.py` | automated |
| AC-6 | Ventana abierta con aviso permanente de valores referenciales (reemplaza el fail-closed original por decisión del humano 2026-10-14) | `simulador_service.py` (`generar_pdf`), `app/web/routes/simulador.py`, `simulador.html` | `tests/unit/test_sim_rv_ventana.py`, `test_sim_rv_web.py`, `test_sim_rv_pdf.py` | automated + human (smoke AC-19) |
| AC-7 | Contenido del PDF según matriz | `simulador_service.py::generar_pdf` | `tests/unit/test_sim_rv_pdf.py` | automated + human (smoke AC-19) |
| AC-8 | Escape de marcado, español, sin enlaces/scripts, metadatos genéricos | `simulador_service.py::generar_pdf` | `tests/unit/test_sim_rv_pdf.py::test_escape_de_marcado` | automated |
| AC-9 | PDF en memoria, headers efímeros, sin logs | `app/web/routes/simulador.py` (POST) | `tests/unit/test_sim_rv_web.py::test_headers_pdf_y_auditoria` | automated + human |
| AC-10 | Entradas y resultado guardados solo como evidencia append-only de solo escritura en `tpi.auditoria.detalle` (sin alterar el lead, sin nombres ni identificadores directos) | `simulador_service.py` (auditoría), `simulador_auditoria.py` | `tests/integration/test_sim_rv_web.py::test_sin_persistencia`, `test_evidencia_reproducible`, `tests/unit/test_sim_rv_evidencia_entradas.py` | automated |
| AC-11 | Evento append-only en `tpi.auditoria` con detalle versionado (`schema_version`) y sin PII directa (sin nombres, RUT, correo ni teléfono) | `app/services/simulador_auditoria.py::record_simulacion_event` | `tests/integration/test_sim_rv_web.py::test_auditoria_sin_pii`, `tests/unit/test_sim_rv_auditoria.py` | automated |
| AC-12 | Código de verificación determinístico (sha256, 12 hex) | `simulador_service.py::codigo_verificacion` | `tests/unit/test_sim_rv_codigo_verificacion.py` | automated |
| AC-13 | Validación servidor (Pydantic en el borde), CSRF, 500 genérico | `app/web/routes/simulador.py` (modelos Pydantic) | `tests/unit/test_sim_rv_web.py::test_validacion_servidor_422`, `test_csrf_invalido_403` | automated |
| AC-14 | Solo `reportlab==5.0.1`; numpy declarado; pip-audit limpio | `pyproject.toml`, `requirements/*.lock` | CI (pip-audit, docker build) | automated |
| AC-15 | Sin regresión en listado/detalle/dashboard/export/asignación/RBAC/PII | (sin cambios en esos flujos; `app/auth/**` intacto) | suite completa existente | automated + human |
| AC-16 | Cobertura total ≥ 85% | toda la suite | CI `--cov-fail-under=85` | automated |
| AC-17 | Documentación creada | `docs/SIM_RV_V1_*.md`, `CHANGELOG.md`, `docs/BITACORA.md` | — | human (revisión) |
| AC-18 | Campaña canaria de revalidación (≥30 casos ciegos) antes del release | — | — | human (evidencia de revalidación) |
| AC-19 | Smoke humano en AWS DEV (3 escenarios + 403 + PDF legible + sin PII en logs) | — | — | human (evidencia de smoke) |

## 3. Matriz de contenido del PDF (AC-7 de SIM-RV-V1, con el formato de `SIM-FICHA-PDF`)

Desde `SIM-FICHA-PDF` el PDF es la ficha «Estudio de pensión» (carta apaisada 792 × 612 pt, diseño en
`docs/specs/SIM_FICHA_PDF_SPEC.md`). El contenido, de arriba a abajo:

| # | Elemento | Origen | PII |
|---|---|---|---|
| 1 | Banda superior azul marino `#0f243e`: tratamiento (`Sr.`/`Sra.`) + nombre del cliente, título «ESTUDIO DE PENSIÓN» y fecha de generación (dd-mm-aaaa) | `lead.nombre_completo`, sexo del causante y servidor | nombre **sí** (permitido; sin RUT/correo/teléfono) |
| 2 | Fila de datos con borde: «FECHA DE NAC», «CÓNYUGE» (solo si hay), «T» (tasa de venta) y celda destacada con el valor UF (solo si se informó) | lead y formulario | fecha de nacimiento (dato del causante); sin RUT/correo/teléfono |
| 3 | «OPCIÓN I»: tabla «Renta Vitalicia Inmediata» + «Rescate Total» (Capital, T, Años, `[UF]`, `[$]Valor Actual`, flecha `>>>>`, rescate en UF) | motor + formulario | no |
| 4 | «OPCIÓN II» (solo con aumento temporal): «Aumento Temporal de Pensión» + «Renta Vitalicia Inmediata» («Sin Excedente», «Inflación Futura 4%», «Rescate Total») | motor + formulario | no |
| 5 | Pie: nombre del ejecutivo y contacto corporativo en texto plano (correo, sitio, dirección), sin enlaces activos | `AuthenticatedUser.display_name` + literal | no (nombre funcional) |
| 6 | Banda inferior azul marino con el logo oficial | `app/web/static/img/official-logo-on-dark.png` | no |
| 7 | «Supuestos y advertencias»: aviso permanente de que los resultados son valores referenciales (no vinculantes), la leyenda «Estimación referencial no vinculante», la versión del modelo y el código de verificación | literal, `app.simulador_pension.__version__`, `codigo_verificacion()` | no |
| 8 | Paginación (una página) | reportlab | no |

**Excluido del PDF:** RUT, correo y teléfono del lead (ni siquiera enmascarados), saldo del lead, enlaces
activos, scripts, adjuntos, la fila «RP (AFP)», el bloque «PGU / BAC / TOTAL», el estado civil, el teléfono
personal del ejecutivo y la comparativa de varias opciones (ver `docs/SIM_RV_V1_PENDIENTES.md`).

## 4. Tabla de rangos validados (AC-4/AC-13)

| Campo | Rango validado | Fuera de rango |
|---|---|---|
| Saldo UF | 500 – 100.000 (renta temporal desde 1.000) | 422 |
| Tasa de venta (%) | 0,5 – 8 (0,5–7,5 en renta inmediata; 8 en renta temporal) | 422 |
| Valor UF (CLP, opcional) | mayor que 0, finito, hasta 1.000.000 | 422 |
| Causante (edad) | individual 60–100; con cónyuge 60–92; con hijos 62–92; RT 59–88 | 422 |
| Cónyuge (edad) | 46–96 | 422 |
| Hijos | 0–4; edad 0–41; invalidez no/parcial/total; común o no | más de 4 → 422; edad fuera de 0–41 → 422 |
| Garantía (meses) | 0 – 480 | 422 |
| Aumento temporal (meses / %) | 0 – 600 / 0 – 100 | 422 |
| Diferimiento (años) | 1 – 10 | 422 |
| Relación RVD/RT (%) | 100, 50, entero 51–99 | 422 |

**Rechazos incondicionales de la V1 (422):** bono de reconocimiento, vejez anticipada, invalidez y sobrevivencia como tipo
de pensión, otros parentescos, cónyuge inválido, renta temporal con cónyuge/hijos/garantía/aumento.
