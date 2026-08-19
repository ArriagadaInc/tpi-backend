FROM python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN adduser -S -D -h /home/appuser -s /sbin/nologin appuser

COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser requirements/runtime.lock ./requirements/runtime.lock

# Keep the locked runtime dependencies cacheable across application-only changes.
RUN pip install --no-cache-dir --requirement requirements/runtime.lock

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser .streamlit ./.streamlit

RUN pip install --no-cache-dir --no-deps .

# TPI persists exclusively in PostgreSQL; do not retain an unused SQLite runtime.
RUN apk del --no-network sqlite

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-m", "scripts.healthcheck_runtime"]

USER appuser

CMD ["streamlit", "run", "app/streamlit_app.py"]
