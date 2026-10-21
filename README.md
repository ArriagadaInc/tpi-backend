# Tu Pension Inteligente

TPI captures public pension-simulation leads and provides a separate private
backoffice for operational review in DEV.

## Quick start

```bash
python -m pip install --requirement requirements/dev.lock
python -m pip install --no-deps -e .
uvicorn app.web.main:app --host 0.0.0.0 --port 8501
pytest tests/ --cov=app --cov-fail-under=85
```

The public API entrypoint is `app/api/main.py` (FastAPI, port 8000); the private
backoffice web is `app/web/main.py` (FastAPI + Jinja2, port 8501). Backoffice
authentication is DEV-only and disabled by default outside its explicitly
configured boundary. The legacy Streamlit UI was retired (see
`docs/SEGURIDAD.md` and the changelog).

## Agent harness

This repository is a repository-native agent harness. Any compatible coding agent starts with
[AGENTS.md](AGENTS.md) and `./init.sh --runtime <runtime>`.

## Documentation

- [Development Guide](docs/DEVELOPMENT_GUIDE.md)
- [H2.5 Architecture](docs/H2_5_ARCHITECTURE.md)
- [Engineering standards](docs/ENGINEERING_STANDARDS.md)
- [Project log](docs/BITACORA.md)

Use only synthetic data in local and DEV environments. Never commit secrets.
