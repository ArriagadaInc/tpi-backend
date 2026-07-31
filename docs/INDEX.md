# 📚 Índice de Documentación

Guía de todos los documentos del proyecto. Comienza por el que corresponda a tu necesidad.

## 🚀 Para Empezar

1. **[QUICKSTART.md](QUICKSTART.md)** - Instalación y primeros pasos (5 min)
   - Clonar y configurar proyecto
   - Instalar dependencias
   - Ejecutar pruebas
   - Verificar que todo funciona

2. **[README.md](README.md)** - Visión general del proyecto
   - Qué es el MVP
   - Requisitos
   - Estructura general
   - Validaciones implementadas

## 📖 Documentación Técnica

### Etapas del Proyecto

1. **[docs/ETAPA1_SCHEMA_MAPPING.md](docs/ETAPA1_SCHEMA_MAPPING.md)** (Completada)
   - Análisis de esquema TPI
   - Mapeo de campos
   - Catálogos identificados

2. **[docs/ETAPA2_ESTRUCTURA.md](docs/ETAPA2_ESTRUCTURA.md)** (Completada)
   - Estructura del proyecto
   - Configuración
   - Validadores básicos
   - Modelos Pydantic

3. **[docs/ETAPA3_RESUMEN.md](docs/ETAPA3_RESUMEN.md)** (Completada)
   - Resumen ejecutivo de Etapa 3
   - Repositorio y Servicio
   - Pruebas implementadas
   - Árbol final de carpetas

4. **[docs/ETAPA4_RESUMEN.md](docs/ETAPA4_RESUMEN.md)** ✨ NUEVA
   - Resumen ejecutivo de Etapa 4
   - Páginas Streamlit (4 páginas)
   - Componentes UI reutilizables
   - Flujos de usuario
   - Arquitectura UI → Servicios

### Decisiones y Arquitectura

- **[docs/DECISIONES_TECNICAS.md](docs/DECISIONES_TECNICAS.md)** ✨ NUEVA
  - 9 decisiones arquitectónicas justificadas
  - Errores prevenidos
  - 10 limitaciones conocidas
  - Métricas de cobertura
  - Próximas etapas

## 🧪 Pruebas

- **[tests/README.md](tests/README.md)**
  - Cómo ejecutar pruebas
  - Estructura de tests
  - Marcadores (markers)
  - Troubleshooting

## 🔧 Desarrollo

### Para Entender la Arquitectura

```
Orden recomendado:
1. README.md (visión general)
2. docs/ETAPA3_RESUMEN.md (resumen de lo implementado)
3. docs/DECISIONES_TECNICAS.md (por qué decidimos así)
4. QUICKSTART.md (cómo correr el código)
```

### Para Agregar Nuevas Características

```
1. Leer docs/DECISIONES_TECNICAS.md (entender patrones)
2. Revisar app/repositories/solicitud_repository.py (patrón Repository)
3. Revisar app/services/solicitud_service.py (patrón Service)
4. Revisar tests/integration/test_solicitud_flow.py (test your changes)
```

### Para Debugging

```
1. Revisar QUICKSTART.md - Sección "Troubleshooting"
2. Ejecutar: python scripts/verify_database_connection.py
3. Ejecutar: python scripts/verify_project_structure.py
4. Ver logs: tail -f logs/backoffice.log
5. Leer docs/DECISIONES_TECNICAS.md - Sección "Errores Prevenidos"
```

## 📊 Estructura del Proyecto

```
tu-pension-inteligente-backoffice/
├── app/                          # Código principal
│   ├── config/                   # Configuración centralizada
│   ├── database/                 # BD y conexiones
│   ├── validators/               # Validadores (RUT, teléfono, email)
│   ├── models/                   # Modelos Pydantic
│   ├── security/                 # Enmascaramiento de datos
│   ├── services/                 # ✨ Lógica de negocio (Etapa 3)
│   ├── repositories/             # ✨ Acceso a datos (Etapa 3)
│   ├── components/               # ✨ Componentes UI Streamlit (Etapa 4)
│   ├── pages/                    # ✨ Páginas Streamlit (Etapa 4)
│   ├── streamlit_app.py          # ✨ App principal Streamlit (Etapa 4)
│   └── __init__.py
├── tests/                        # Pruebas
│   ├── unit/                     # Unitarias (Etapa 3)
│   └── integration/              # Integración (Etapa 3)
├── scripts/                      # Utilidades CLI
├── docs/                         # Documentación
├── QUICKSTART.md                 # Guía rápida
├── README.md                     # Visión general
├── pyproject.toml                # Dependencias
├── .env                          # Configuración local
└── .gitignore                    # Archivos ignorados
```

## 📈 Progreso del Proyecto

| Etapa | Status | Documentación |
|-------|--------|---------------|
| 1: Análisis | ✅ Completa | Verificación de esquema TPI |
| 2: Estructura | ✅ Completa | Configuración, validadores, modelos |
| 3: Datos/Servicios | ✅ Completa | **[ETAPA3_RESUMEN.md](docs/ETAPA3_RESUMEN.md)** ← TÚ ESTÁS AQUÍ |
| 4: UI Streamlit | ⏳ Pendiente | Próxima fase |
| 5: Testing/Prod | ⏳ Pendiente | Tests E2E, deployment |

## 🎯 Comandos Principales

```bash
# Verificar BD
python scripts/verify_database_connection.py

# Verificar estructura
python scripts/verify_project_structure.py

# Correr pruebas
pytest                                    # Todas
pytest tests/unit/                       # Solo unitarias
pytest tests/integration/                # Solo integración
pytest --cov=app --cov-report=html      # Con cobertura

# Linting
ruff check .                              # Verificar
ruff format .                             # Formatear

# Iniciar Streamlit (Etapa 4)
# streamlit run app/streamlit_app.py
```

## 🔗 Enlaces Relacionados

- **Repositorio de ingesta**: [tpi-data-pipeline](../tpi-data-pipeline)
  - Base de datos que alimenta este MVP
  - Scripts de setup_db
  - Verifica que BD esté disponible

- **PostgreSQL**: 
  - Debe estar corriendo localmente
  - Base de datos: `tpi_local`
  - Esquema: `tpi`

## ❓ Preguntas Frecuentes

### "¿Por dónde empiezo?"
→ [QUICKSTART.md](QUICKSTART.md)

### "¿Cuál es la arquitectura?"
→ [docs/DECISIONES_TECNICAS.md](docs/DECISIONES_TECNICAS.md)

### "¿Cómo corro las pruebas?"
→ [tests/README.md](tests/README.md)

### "¿Qué fue implementado en Etapa 3?"
→ [docs/ETAPA3_RESUMEN.md](docs/ETAPA3_RESUMEN.md)

### "¿Qué características faltan?"
→ [docs/DECISIONES_TECNICAS.md](docs/DECISIONES_TECNICAS.md) - Sección "Limitaciones"

### "¿Cómo agrego una nueva validación?"
→ [docs/DECISIONES_TECNICAS.md](docs/DECISIONES_TECNICAS.md) - Sección "Validación en Dos Niveles"

### "¿Cómo debuggeo un problema?"
→ [QUICKSTART.md](QUICKSTART.md) - Sección "Troubleshooting"

## 📝 Notas Importantes

1. **PostgreSQL debe estar corriendo** - Requerido para pruebas de integración
2. **`.env` debe estar configurado** - Con credenciales correctas
3. **Leer DECISIONES_TECNICAS.md** - Entiende por qué cada decisión
4. **Ejecutar verify_database_connection.py** - Antes de Etapa 4

## 🎓 Para Aprender del Código

### Ejemplo 1: Cómo se valida un RUT
- Leer: `app/validators/rut.py` (implementación)
- Probar: `tests/unit/test_rut.py` (pruebas)

### Ejemplo 2: Cómo se registra una solicitud
- Leer: `app/services/solicitud_service.py` (orquestación)
- Ver: `app/repositories/solicitud_repository.py` (datos)
- Test: `tests/integration/test_solicitud_flow.py` (verificación)

### Ejemplo 3: Cómo se enmascaran datos
- Leer: `app/security/masking.py` (implementación)
- Test: Ver uso en servicios

---

**Versión**: 0.1.0 (MVP)  
**Última actualización**: 2026-07-31  
**Status**: ✅ Etapa 3 COMPLETA

Comienza por **[QUICKSTART.md](QUICKSTART.md)** si es tu primera vez.
