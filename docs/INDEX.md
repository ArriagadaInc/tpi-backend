# Indice de Documentacion

Guia de todos los documentos del proyecto. Comienza por el que corresponda a tu necesidad.

## Para Empezar

1. [QUICKSTART.md](../QUICKSTART.md): instalacion y primeros pasos.
2. [README.md](../README.md): vision general del MVP, requisitos y estructura.
3. [BITACORA.md](BITACORA.md): continuidad operativa, decisiones, riesgos y siguientes pasos.

## Documentacion Tecnica

### Etapas del proyecto

1. [ETAPA1_SCHEMA_MAPPING.md](ETAPA1_SCHEMA_MAPPING.md): analisis del esquema TPI.
2. [ETAPA2_ESTRUCTURA.md](ETAPA2_ESTRUCTURA.md): estructura, configuracion y validadores.
3. [ETAPA3_RESUMEN.md](ETAPA3_RESUMEN.md): repositorio, servicio y pruebas.
4. [ETAPA4_RESUMEN.md](ETAPA4_RESUMEN.md): paginas Streamlit y flujos UI.
5. [H2_1_PREPARACION_DESPLIEGUE.md](H2_1_PREPARACION_DESPLIEGUE.md): readiness para despliegue Streamlit.

### Arquitectura y operacion

- [DECISIONES_TECNICAS.md](DECISIONES_TECNICAS.md): decisiones arquitectonicas y limitaciones.
- [AWS_RDS_CONNECTION.md](AWS_RDS_CONNECTION.md): conexion PostgreSQL, ambientes y operacion RDS.
- [ARCHITECTURE.md](ARCHITECTURE.md): capas y componentes.
- [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md): Definition of Done, gates y reproducibilidad.
- [SEGURIDAD.md](SEGURIDAD.md): practicas de seguridad y datos sensibles.
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md): setup, quality gates, AWS DEV and authentication boundary.
- [H2_5_SIMPLE_DEV_AUTH_PREFLIGHT.md](H2_5_SIMPLE_DEV_AUTH_PREFLIGHT.md): approved H2.5 topology and DNS prerequisite.
- [H2_5_CEO_VALIDATION_GUIDE.md](H2_5_CEO_VALIDATION_GUIDE.md): DEV validation flow without credentials.
- [H3_2_DEPLOYMENT_REPRODUCIBLE_PLAN.md](H3_2_DEPLOYMENT_REPRODUCIBLE_PLAN.md): H3.2 master plan, manifest, stop rules, and rollout design.
- [DEPLOYMENT_RUNBOOK_TPI.md](DEPLOYMENT_RUNBOOK_TPI.md): deployment runbook draft.
- [DEPLOYMENT_PLAYBOOK.md](DEPLOYMENT_PLAYBOOK.md): short operational playbook draft.
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md): release checklist draft.

## Pruebas

- [tests/README.md](../tests/README.md): estructura, comandos y troubleshooting de pruebas.
- [TESTING_REPORT.md](TESTING_REPORT.md): cobertura y estrategia historica de testing.

## Orden Recomendado

1. Leer [README.md](../README.md).
2. Revisar [DECISIONES_TECNICAS.md](DECISIONES_TECNICAS.md).
3. Configurar el entorno con [QUICKSTART.md](../QUICKSTART.md).
4. Consultar [AWS_RDS_CONNECTION.md](AWS_RDS_CONNECTION.md) antes de cambiar ambiente o conexion.
5. Revisar [BITACORA.md](BITACORA.md) antes de retomar trabajo.

## Comandos Principales

```bash
# Verificacion de conexion
python scripts/verify_database_connection.py

# Pruebas y cobertura
pytest tests/

# Calidad
ruff check app tests scripts
black --check app tests scripts
mypy app --ignore-missing-imports
bandit -r app --severity-level medium --confidence-level medium
pip-audit --requirement requirements/runtime.lock

# Streamlit
streamlit run app/streamlit_app.py
```

## Notas Importantes

1. PostgreSQL debe estar disponible para las pruebas de integracion.
2. `.env` local no se versiona y debe contener solo credenciales locales.
3. Toda modificacion documental relevante debe actualizar [BITACORA.md](BITACORA.md).
4. Ninguna funcionalidad desplegable se considera cerrada sin los gates de [ENGINEERING_STANDARDS.md](ENGINEERING_STANDARDS.md).
