# H2.1 - Preparación técnica para desplegar Streamlit en AWS DEV

Este documento resume el estado de preparación del backoffice para un despliegue reproducible, seguro y promovible a AWS DEV.

## Diagnóstico inicial

- La aplicación se inicia con `streamlit run app/streamlit_app.py`.
- El entrypoint principal es [`app/streamlit_app.py`](../app/streamlit_app.py).
- La configuración está centralizada en [`app/config/settings.py`](../app/config/settings.py) y se resuelve desde variables de entorno o `.env`.
- La conexión a PostgreSQL usa `psycopg` + `psycopg_pool` desde [`app/database/connection.py`](../app/database/connection.py).
- Los ambientes soportados son `local`, `testing`, `aws-dev` y `production`, con alias normalizados.
- Los puertos relevantes son `8501` para Streamlit y `5432` para PostgreSQL.
- Faltaba una configuración declarativa para servidor Streamlit.
- El `Dockerfile` anterior tenía un healthcheck que no validaba la aplicación ni la base de datos.
- La aplicación no tenía un helper de runtime/logging compartido para arranque y readiness.
- Había documentación operativa útil, pero no un runbook específico de esta etapa.

## Cambios realizados

- Se agregó [`app/runtime.py`](../app/runtime.py) para logging, arranque controlado y manejo seguro de errores.
- Se agregó [`scripts/healthcheck_runtime.py`](../scripts/healthcheck_runtime.py) como readiness check del contenedor.
- Se agregó [`.streamlit/config.toml`](../.streamlit/config.toml) para ejecutar Streamlit en host no local.
- Se endureció el [`Dockerfile`](../Dockerfile) con imagen explícita, usuario no privilegiado y healthcheck real.
- Se actualizó [`docker-compose.yml`](../docker-compose.yml) para exponer un healthcheck útil en el servicio Streamlit.
- Se reforzaron [`.gitignore`](../.gitignore) y [`.dockerignore`](../.dockerignore) para secretos, llaves y artefactos locales.
- Se actualizó [`run_streamlit.bat`](../run_streamlit.bat) para abrir la app de forma portable.
- Se agregaron tests unitarios para runtime, healthcheck y alias de ambiente.
- Se agregaron tests de integración para el healthcheck completo.

## Arquitectura resultante

```text
Streamlit UI
  -> app.runtime / app.components
  -> services
  -> repositories
  -> app.database.connection
  -> psycopg_pool
  -> PostgreSQL
```

La configuración entra por variables de entorno y `.env` local. `APP_ENV`, `DATABASE_*`, `LOG_LEVEL` y `LOG_FILE` siguen siendo el contrato principal.

## Seguridad

- No se versionan secretos en código.
- `.env` y variantes locales quedan ignorados por Git.
- Las credenciales no se imprimen en logs.
- El healthcheck no expone RUT, nombres ni strings de conexión.
- El contenedor ejecuta un usuario no privilegiado.
- La aplicación sigue lista para incorporar Secrets Manager sin cambiar la lógica de negocio.

## Health Check

El readiness check verifica dos niveles:

1. La app/proceso está viva y puede ejecutar el healthcheck.
2. PostgreSQL responde y expone el esquema, la tabla `tpi.leads` y los catálogos requeridos.

Si falla, el código de salida del healthcheck es no cero y el runtime genera logs seguros.

## Logging

Se registran:

- inicio de aplicación;
- ambiente activo;
- éxito o fallo del healthcheck;
- errores de conexión;
- errores inesperados.

Se prohíbe registrar:

- contraseñas;
- `DATABASE_URL` completa;
- tokens;
- RUT completos;
- PII innecesaria;
- payloads completos con datos sensibles.

Los logs salen por `stdout/stderr`, listos para CloudWatch.

## Ejecución local

```bash
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
streamlit run app/streamlit_app.py
```

## Ejecución con Docker

```bash
docker build -t tpi-backoffice .
docker run --rm -p 8501:8501 --env-file .env tpi-backoffice
```

Con Compose:

```bash
$env:TPI_POSTGRES_PASSWORD = "<local-secret>"
docker compose up --build
```

## Variables necesarias

- `APP_ENV`: ambiente lógico (`local`, `testing`, `aws-dev`, `production`).
- `DATABASE_HOST`: host o endpoint PostgreSQL.
- `DATABASE_PORT`: puerto, normalmente `5432`.
- `DATABASE_NAME`: base de datos.
- `DATABASE_USER`: usuario de conexión.
- `DATABASE_PASSWORD`: secreto inyectado por entorno.
- `DATABASE_SCHEMA`: esquema lógico, normalmente `tpi`.
- `DATABASE_SSLMODE`: modo SSL apropiado por ambiente.
- `DATABASE_SSLROOTCERT`: CA bundle cuando aplique en producción.
- `DATABASE_CONNECT_TIMEOUT`: timeout de conexión.
- `DATABASE_POOL_MIN_SIZE`: mínimo del pool.
- `DATABASE_POOL_MAX_SIZE`: máximo del pool.
- `DATABASE_POOL_TIMEOUT`: espera para adquirir conexión.
- `LOG_LEVEL`: `INFO`, `WARNING`, `ERROR`, etc.

## Testing

```bash
pytest tests/unit -q
pytest tests/integration -q
pytest tests -q --cov-fail-under=80
ruff check app tests scripts
black --check app tests scripts
mypy app --ignore-missing-imports
bandit -r app --severity-level medium --confidence-level medium
pip-audit --requirement requirements/runtime.lock
```

## Correcciones de cierre H2.1

- La cobertura global tiene un minimo obligatorio de 80 por ciento en la suite completa de CI.
- Bandit y `pip-audit` son quality gates bloqueantes; no usan `continue-on-error`.
- CI construye la imagen Docker en cada pull request.
- Los modelos propios se migraron desde la clase Pydantic `Config` a `ConfigDict`, eliminando el warning deprecado.
- Las versiones resueltas se registran en `requirements/runtime.lock` y `requirements/dev.lock`.
- La Definition of Done permanente esta en `docs/ENGINEERING_STANDARDS.md`.

Para instalar de forma reproducible fuera de Docker:

```bash
python -m pip install --requirement requirements/dev.lock
python -m pip install --no-deps -e .
```

## Futuro despliegue

Queda listo el artefacto base para una promoción posterior a AWS DEV:

- imagen Docker reproducible;
- healthcheck de readiness;
- configuración externa;
- logging por stdout;
- tests de configuración, healthcheck e integración.

El siguiente paso será inyectar secretos desde el mecanismo elegido en AWS y publicar la imagen en el servicio objetivo.
