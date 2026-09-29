---
name: tpi-python-fastapi
role: developer
load_when: "DEVELOPING cuando la tarea toca app/web, app/api, templates o servicios"
sources: [technical_decisions, development_guide, h33_web_ux, engineering_standards]
---

# tpi-python-fastapi

## 1. Cuando se carga
Tareas que modifican `app/web` (backoffice FastAPI + Jinja2), `app/api` (API publica) o `app/services`.

## 2. Puede
- Modificar rutas, dependencias, templates Jinja2, CSS/JS local y servicios.
- Agregar tests unitarios/integracion/e2e/security asociados.

## 3. No puede
- Acceder a PostgreSQL o SNS desde rutas o templates (siempre via `SolicitudService`).
- Usar URLs absolutas dependientes de esquema para assets same-origin (usar `/static/...`).
- Agregar CORS wildcard, desactivar CSRF o relajar guards de autenticacion.
- Introducir una segunda estrategia de acceso a BD (no SQLAlchemy ORM).

## 4. Precondiciones
- Worktree de la tarea activo y rama `harness/<task>-*` actualizada con `origin/main`.
- Criterios de aceptacion leidos en `tasks/current.yaml`.

## 5. Comandos y herramientas
- `python -m pip install --requirement requirements/dev.lock && python -m pip install --no-deps -e .`
- `uvicorn app.web.main:app --host 127.0.0.1 --port 8501` (local, datos sinteticos).
- `pytest tests/unit tests/integration tests/security -q`
- `ruff check app/ tests/ scripts/ deployment/` y `black --check ...`, `mypy app/ --ignore-missing-imports`.

## 6. Evidencia obligatoria
- `files_changed`, resultado de tests y gates en `developer-*.json`.
- Supuestos de diseno en `assumptions` (sin datos personales reales).

## 7. STOP
- El cambio requiere option settings, IAM, DNS o secretos nuevos (clase C/E): registrar y detener.
- Contradiccion entre documentacion y codigo sobre contrato de rutas o roles.

## 8. Fuentes
- `docs/DECISIONES_TECNICAS.md` (H2.5, H2.5C, assets same-origin).
- `docs/H3_3_CRM_LITE_WEB_UX.md` secciones 4-7 (arquitectura web, estados, seguridad).
- `docs/DEVELOPMENT_GUIDE.md` (setup local; su descripcion Streamlit del backoffice esta desactualizada).
