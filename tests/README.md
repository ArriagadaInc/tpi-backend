# Pruebas de la Aplicación

Este directorio contiene todas las pruebas automatizadas del proyecto.

## Estructura

```
tests/
├── conftest.py                 # Configuración global de pytest
├── unit/                       # Pruebas unitarias
│   ├── test_rut.py            # Validador de RUT
│   ├── test_phone.py          # Validador de teléfono
│   └── test_email.py          # Validador de email
└── integration/               # Pruebas de integración
    └── test_solicitud_flow.py # Flujo completo de solicitudes
```

## Ejecutar pruebas

### Todas las pruebas

```bash
pytest
```

### Solo pruebas unitarias

```bash
pytest tests/unit/
```

### Solo pruebas de integración

```bash
pytest tests/integration/
```

### Con salida verbosa

```bash
pytest -v
```

### Generar reporte de cobertura

```bash
pytest --cov=app --cov-report=html
# Abrir htmlcov/index.html en navegador
```

### Ejecutar un test específico

```bash
pytest tests/unit/test_rut.py::TestValidateRut::test_valid_ruts
```

## Requisitos previos

### Para pruebas unitarias
- Solo dependencias de `requirements.txt`

### Para pruebas de integración
- PostgreSQL debe estar ejecutándose
- Variables de entorno `.env` deben estar configuradas
- Base de datos TPI debe estar disponible
- Script `scripts/verify_database_connection.py` debe pasar

Verificar:
```bash
python scripts/verify_database_connection.py
```

## Cobertura esperada

### Etapa 3 (actual)
- ✅ RUT: formato, validación, enmascaramiento
- ✅ Teléfono: normalización, validación, enmascaramiento
- ✅ Email: validación, normalización, enmascaramiento
- ✅ Flujo de solicitudes: creación, consulta, catálogos
- ✅ Validaciones de negocio: IDs de catálogo, consentimientos

### Etapa 5 (pendiente)
- Servicios y repositorios (cobertura completa)
- Casos edge complejos
- Manejo de errores
- Transacciones BD

## Marcadores (markers)

```bash
# Ejecutar solo tests rápidos
pytest -m "not slow"

# Ejecutar solo tests que necesitan BD
pytest -m integration
```

Los marcadores se definen en `pyproject.toml`.

## Troubleshooting

### "Base de datos no disponible"
```bash
# Verificar conexión
python scripts/verify_database_connection.py

# Ver detalles en logs
tail -f logs/backoffice.log
```

### "Module not found"
```bash
# Asegurar que .env está configurado
cp .env.example .env
# Editar .env con credenciales reales
```

### "Import error"
```bash
# Reinstalar en modo editable
pip install -e ".[dev]"
```

## Notas de desarrollo

- Las pruebas de integración requieren datos reales en BD
- Los tests crean datos con RUT de test (18777777-7, 18888888-8, etc)
- Las pruebas son **idempotentes** (pueden ejecutarse múltiples veces)
- No se hace cleanup automático (datos persisten para auditoría)

## Próximas etapas

- [ ] Pruebas de rendimiento (Etapa 5)
- [ ] Pruebas de seguridad (SQL injection, XSS)
- [ ] Pruebas de carga (múltiples usuarios concurrentes)
- [ ] Pruebas E2E con Streamlit (Etapa 4)
