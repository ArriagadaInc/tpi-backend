FROM python:3.12.14-alpine3.24@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Keep the Python 3.12.14/Alpine 3.24 base pinned while remediating the
# only vulnerable Alpine runtime package reported by ECR.
RUN apk add --no-cache libuuid=2.42.3-r1

RUN adduser -S -D -h /home/appuser -s /sbin/nologin appuser

COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser requirements/runtime.lock ./requirements/runtime.lock

# Keep the locked runtime dependencies cacheable across application-only changes.
RUN pip install --no-cache-dir --requirement requirements/runtime.lock

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser .streamlit ./.streamlit

RUN pip install --no-cache-dir --no-deps .

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-m", "scripts.healthcheck_runtime"]

USER appuser

CMD ["streamlit", "run", "app/streamlit_app.py"]
