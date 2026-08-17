# Tu Pension Inteligente

TPI captures public pension-simulation leads and provides a separate private
backoffice for operational review in DEV.

## Quick start

```bash
python -m pip install --requirement requirements/dev.lock
python -m pip install --no-deps -e .
streamlit run app/streamlit_app.py
pytest tests/ --cov=app --cov-fail-under=85
```

The public entrypoint is `app/streamlit_app.py`; the private backoffice is
`app/backoffice_app.py`. Backoffice authentication is DEV-only and disabled by
default outside its explicitly configured boundary.

## Documentation

- [Development Guide](docs/DEVELOPMENT_GUIDE.md)
- [H2.5 Architecture](docs/H2_5_ARCHITECTURE.md)
- [Engineering standards](docs/ENGINEERING_STANDARDS.md)
- [Project log](docs/BITACORA.md)

Use only synthetic data in local and DEV environments. Never commit secrets.
