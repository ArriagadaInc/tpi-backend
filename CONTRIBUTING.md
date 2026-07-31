# Guía de Contribución

¡Gracias por tu interés en contribuir a Tu Pensión Inteligente! Aquí te explicamos cómo hacerlo.

## Código de Conducta

Esperamos que todos los contribuyentes respeten un ambiente de trabajo inclusivo y profesional.

## Antes de Contribuir

1. **Fork** el repositorio
2. **Clona** tu fork localmente:
   ```bash
   git clone https://github.com/TuUsuario/tu-pension-inteligente-backoffice.git
   cd tu-pension-inteligente-backoffice
   ```

3. **Crea un entorno virtual**:
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1  # Windows
   # o
   source .venv/bin/activate  # Linux/Mac
   ```

4. **Instala dependencias de desarrollo**:
   ```bash
   pip install -e ".[dev]"
   pre-commit install
   ```

## Proceso de Contribución

### 1. Crear una rama

```bash
git checkout -b feature/descripcion-clara
# o para fixes:
git checkout -b fix/descripcion-clara
```

**Convención de ramas:**
- `feature/` - nuevas funcionalidades
- `fix/` - correcciones de bugs
- `docs/` - mejoras de documentación
- `refactor/` - refactorización de código

### 2. Hacer cambios

- Sigue el estilo de código del proyecto (ruff, black, mypy)
- Añade tests para nuevas funcionalidades
- Documenta cambios significativos

### 3. Antes de hacer commit

```bash
# Formato automático
ruff check . --fix
black app/ tests/ scripts/

# Linting
ruff check app/ tests/ scripts/
mypy app/

# Tests
pytest tests/ --cov=app
```

### 4. Commit con mensaje descriptivo

```bash
git commit -m "feat: descripción clara de cambios

- Punto 1
- Punto 2

Cierra #123"
```

**Formato de mensajes:**
- `feat:` - nueva funcionalidad
- `fix:` - corrección de bug
- `docs:` - cambios en documentación
- `refactor:` - cambios en código sin alterar funcionalidad
- `test:` - cambios en tests
- `chore:` - cambios en dependencias o configuración

### 5. Push y Pull Request

```bash
git push origin feature/descripcion-clara
```

En GitHub:
1. Abre un **Pull Request**
2. Describe los cambios claramente
3. Enlaza issues relacionados
4. Asegúrate que pasan todos los checks

## Estándares de Código

### Python Style Guide

- **Line length**: 100 caracteres
- **Formato**: Black
- **Linting**: Ruff
- **Type hints**: Mypy
- **Python**: 3.12+

### Estructura de proyecto

```
app/
├── __init__.py
├── components/      # Componentes Streamlit reutilizables
├── config/          # Configuración
├── database/        # Conexión y operaciones DB
├── models/          # Modelos de datos (Pydantic)
├── pages/           # Páginas Streamlit
├── repositories/    # Acceso a datos
├── services/        # Lógica de negocio
├── validators/      # Validadores personalizados
└── security/        # Funciones de seguridad

tests/
├── unit/            # Tests unitarios
├── integration/     # Tests de integración
├── e2e/             # Tests end-to-end
└── security/        # Tests de seguridad
```

## Testing

- Escribe tests para nuevas funcionalidades
- Cobertura mínima: 80%
- Ejecuta: `pytest tests/ --cov=app --cov-report=term-missing`

## Documentación

- Actualiza `README.md` si es necesario
- Añade docstrings a funciones públicas
- Documenta cambios arquitectónicos en `docs/`

## Reportar Bugs

Usa **GitHub Issues** con el template de bug report:

1. Descripción clara del problema
2. Pasos para reproducir
3. Comportamiento esperado
4. Comportamiento actual
5. Entorno (SO, Python, etc.)

## Reportar Vulnerabilidades de Seguridad

**NO** abras un issue público. Consulta [SECURITY.md](SECURITY.md)

## Preguntas

- Abre una **Discussion** en GitHub
- Revisa la documentación en `docs/`

---

¡Gracias por contribuir! 🚀
