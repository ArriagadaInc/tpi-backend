# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/) y este proyecto adhiere a [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### ✅ Agregado

- **Línea de tiempo del lead: simulaciones generadas** (SIM-HISTORIAL-LINEA-TIEMPO)
  - Nueva vista de solo lectura `tpi.v_historial_simulaciones` (migración `009`, `change_class D`) sobre `tpi.auditoria` filtrada por `accion = 'simulacion_renta_vitalicia'`, que expone la evidencia completa de cada simulación (ejecutivo, escenario, versión del modelo, código de verificación, las entradas completas —causante y beneficiarios con sus fechas de nacimiento, invalidez y relación— y el resultado completo), sin censurar ningún dato registrado (decisión del humano, 2026-10-19). `security_barrier`, `REVOKE ALL FROM PUBLIC` y `GRANT SELECT` solo a `tpi_app`; sin `SELECT` directo sobre `tpi.auditoria`. Rollback idempotente en `scripts/sql/009_drop_historial_simulaciones.sql`.
  - El detalle del lead muestra cada simulación en la línea de tiempo (junto a asignaciones, cambios de estado y notas), ordenadas por fecha, con un resumen «Simulación generada» (ejecutivo, escenario, pensión mensual en UF y código) y un detalle desplegable con todas las entradas y el resultado. La aplicación lee **solo** la vista, nunca `tpi.auditoria`.
  - La visibilidad sigue las reglas vigentes del detalle del lead (un `advisor` solo ve leads de su cartera; 404 si no es visible).

- **Tablas de mortalidad del simulador reproducibles desde el repositorio** (`scripts/tablas_mortalidad/`)
  - Se incorporan el Excel de la CMF del que salen las tablas (sin editar, con `procedencia.json`: fuente, norma, fecha, tamaño y `sha256`) y el script que construye `app/simulador_pension/datos/tablas_mortalidad.npz`, con validación de encabezados y modo `--verificar`.
  - El `.npz` que ya usaba el motor se reconstruye idéntico desde el Excel; no cambia ningún valor ni la versión del modelo.
  - Prueba nueva `tests/unit/test_tablas_mortalidad.py`: el CI falla si el Excel, `procedencia.json` y el `.npz` dejan de ser coherentes.
  - Documentado en `docs/SIMULADOR_USO.md` (§8.2) y en `scripts/tablas_mortalidad/README.md`.

- **Documento de uso y mantención del simulador** (`docs/SIMULADOR_USO.md`)
  - Casos soportados y fuera de alcance, rangos de entrada, qué entrega el PDF y la precisión medida.
  - Qué hay que hacer para mantener el simulador vigente: tablas de mortalidad (origen, procedimiento de actualización), constantes empíricas y legales, tasa de venta, ventana de fechas y campaña canaria.
  - Solo documentación: sin cambios de código, base de datos ni despliegue.

- **Simulador: asistente de 3 pasos con la marca de TPI** (SIM-WIZARD-3-PASOS)
  - La pantalla del simulador (`/leads/{id}/simulador`) se rehace como un asistente de 3 pasos: 1 «Datos de la simulación», 2 «Grupo familiar» y 3 «Resultado», con un indicador de pasos conectados por una línea; los pasos completados muestran un lápiz y permiten volver conservando lo ingresado.
  - Paso 1: fecha de simulación de solo lectura (fecha actual de `America/Santiago` calculada en el servidor), tipo de pensión («Vejez edad»), tasa de venta, meses garantizados, años de período diferido, meses y % de aumento temporal, saldo en UF y valor UF opcional, con los rangos validados de la V1. «Continuar» valida este paso en el servidor y muestra los errores en el mismo paso.
  - Paso 2: el causante (el lead) aparece como primera fila sin editarse ni eliminarse; el cónyuge y hasta 4 hijos se agregan, editan y eliminan con un modal (parentesco, tipo de relación con padre/madre solo para hijos, sexo, condición de invalidez, fecha de nacimiento y edad calculada). Se respetan las reglas de la V1 (un cónyuge, máximo 4 hijos, cónyuge inválido rechazado).
  - Paso 3: tarjetas de Monto pensión, Saldo total y Tasa de venta (más Renta temporal y Meses de diferimiento en renta temporal), resumen de la simulación, grupo familiar y el aviso «Valores referenciales, no vinculantes». «Simular» calcula el resultado en pantalla **sin persistir ni auditar**; «Descargar PDF» genera el PDF en memoria y registra el evento de auditoría (como hasta ahora).
  - Marca de TPI: logo oficial (topbar compartido), paleta del CRM y azul marino `#0f243e` de la ficha (paso activo y cabecera del modal). Sin logos, nombres ni el naranja del simulador de referencia; sin librerías ni CDN nuevos (JavaScript propio en `app/web/static/js/simulador_wizard.js`).
  - El motor, la autorización (403 fuera de executive/ceo/cto), la validación, el cálculo y el escape del PDF no cambian. La relación RVD/RT queda oculta en 100 (el asistente replica la estructura del simulador de referencia, que no la expone; el motor y la API siguen aceptando 50/51–99).

- **Simulador de renta vitalicia en el CRM (perfil ejecutivo)** (SIM-RV-V1)
  - Motor puro `app/simulador_pension` que reproduce el simulador de referencia dentro de ±1 UF (435/435 casos del fixture).
  - Panel y formulario en el detalle del lead, visible solo para `executive` y superusuarios `ceo`/`cto` (403 real para el resto).
  - PDF efímero en memoria con escape de marcado, sin RUT, correo ni teléfono del lead.
  - Evento funcional append-only en `tpi.auditoria` sin PII (`app/services/simulador_auditoria.py`).
  - Dependencia nueva: `reportlab==5.0.1`.

- **Evidencia de entradas y resultado del simulador** (SIM-EVIDENCIA-ENTRADAS)
  - El evento append-only de la generación del PDF (`tpi.auditoria.detalle`, acción `simulacion_renta_vitalicia`) pasa a ser un detalle versionado (`schema_version`) que guarda, además de los metadatos funcionales (ejecutivo, escenario, versión del modelo y código de verificación), las entradas de la simulación (causante, saldo, tasa, garantía, aumento, diferimiento, relación RVD/RT, valor UF y beneficiarios: cónyuge e hijos) y el resultado (pensión y, en renta temporal, renta temporal y meses de diferimiento).
  - El detalle es de solo escritura (la aplicación no lo lee), no altera el lead y no contiene nombres, RUT, correo ni teléfono; la retención es indefinida (decisión del humano, 2026-10-19), sin purga ni expiración, y queda pendiente su revisión normativa.
  - Las entradas guardadas bastan para reproducir el resultado y el código de verificación.

### 🔄 Cambiado

- **Lifecycle de ECR compatible con rollback: conservar 100 imágenes** (H3.2-ECR-LIFECYCLE)
  - La política de lifecycle de ECR de AWS DEV (`deployment/ecr/lifecycle-policy.json`) pasa la regla de retención de `imageCountMoreThan: 20` a `imageCountMoreThan: 100`, para que el LKG y los candidatos de rollback no se expiren al acumularse publicaciones. La regla 1 (capas sin etiqueta a los 7 días) no cambia.
  - Nuevo test sin AWS (`tests/unit/test_ecr_lifecycle_policy.py`) que lee la política y rompe CI si no hay reglas, hay prioridades repetidas, una regla expira por antigüedad imágenes con etiqueta o el conteo de retención baja de 100.
  - Nuevo `docs/ECR_LIFECYCLE_POLICY.md` con el procedimiento de aplicación (put/get-lifecycle-policy y vista previa), verificación, reversa y las comprobaciones de digests del LKG que se mantienen. La aplicación en AWS DEV la ejecuta el humano.

- **Ventana de validación abierta con aviso de valores referenciales** (SIM-RV-V1-VENTANA)
  - Por decisión del humano (2026-10-14) la ventana validada del simulador queda abierta: se eliminan el estado «bloqueado», el corte de 90 días y el 422 por vencimiento, y la simulación se genera para cualquier fecha de simulación (la fecha actual de `America/Santiago`).
  - El formulario muestra siempre un aviso de que los resultados son valores referenciales (no vinculantes) y el PDF lo indica de forma explícita en la sección «Supuestos y advertencias»; desaparece el aviso condicional de ventana de validación vencida en pantalla y en el PDF.
  - El motor `app/simulador_pension/**` no cambia: conserva `VENTANA_VALIDADA` y su `warnings.warn` informativo (no llega a pantalla ni al PDF).

- **Ajustes de uso del CRM y del simulador** (SIM-UX-AJUSTES)
  - Los errores de validación del formulario del simulador (p. ej. edad fuera de rango) se muestran en la misma pantalla, en un aviso arriba del formulario, conservando lo ingresado, con HTTP 422 y mensaje claro en español; ya no se responde con una pantalla de texto aparte.
  - En el detalle del lead se elimina el botón antiguo «Abrir simulación» y queda solo «Abrir simulador» del panel nuevo (visible para `executive`, `ceo` y `cto`).
  - Cabecera del CRM: «Volver al sitio» pasa a «Home» y «Salir» pasa a «Cerrar sesión».
  - El CRM deja de llamarse «CRM Lite»: ahora se muestra «CRM» en títulos de página, cabecera, insignia, kickers, login y la app Streamlit.

- **Ficha PDF «Estudio de pensión»** (SIM-FICHA-PDF)
  - El PDF del simulador pasa a carta apaisada (792 × 612 pt) con el formato de la ficha «Estudio de pensión» de TPI: banda azul marino `#0f243e` con tratamiento y nombre del cliente, título «ESTUDIO DE PENSIÓN» y fecha; fila de datos (fecha de nacimiento, cónyuge, tasa de venta y valor UF); tablas de «OPCIÓN I» (Renta Vitalicia Inmediata + Rescate Total) y «OPCIÓN II» (Aumento Temporal de Pensión + Inflación Futura 4% + Rescate Total) cuando hay aumento temporal; pie con el nombre del ejecutivo y el contacto corporativo en texto plano; y banda inferior azul marino con el logo oficial (`official-logo-on-dark.png`).
  - Cálculos derivados verificados con datos sintéticos: Rescate Total = pensión × meses garantizados; `$` Valor Actual = pensión × valor UF; Valor Futuro = Valor Actual × 1,04^años del aumento; Rescate Total de la Opción II = pensión aumentada × meses del aumento + pensión base × (meses garantizados − meses del aumento).
  - Se conservan la leyenda «Estimación referencial no vinculante», la versión del modelo, el código de verificación, el escape de marcado, los metadatos genéricos sin PII y la ausencia de RUT, correo y teléfono del lead; la renta temporal con RVD conserva su sección con la nueva apariencia.

### 🔧 Corregido

- **Línea de tiempo del lead: no fallar con simulaciones registradas antes de guardar sus entradas** (SIM-HISTORIAL-EVENTOS-ANTIGUOS)
  - Las simulaciones registradas antes de `SIM-EVIDENCIA-ENTRADAS` (2026-10-16) solo conservan el escenario, la versión del modelo y el código de verificación (la vista devuelve `entradas` y `resultado` en `NULL`). El detalle del lead dejaba de renderizar con un 500 porque la plantilla encadenaba atributos de la evidencia (`item.entradas.causante.sexo`) sobre un valor indefinido.
  - La presentación (`app/web/presentation.py`) ahora normaliza las entradas y el resultado a una forma segura (cada campo con clave fija y fallback `None`) y marca los eventos antiguos con `es_legacy`. La plantilla muestra para ellos «Simulación generada» con ejecutivo, escenario, versión del modelo y código, más la nota «Registro anterior al guardado de entradas: solo se conservan escenario, version y codigo», sin detalle desplegable de entradas.
  - La presentación y la plantilla toleran cualquier dato faltante o nulo de la evidencia (entradas o resultado ausentes, causante ausente, beneficiarios vacíos, beneficiarios con campos faltantes y fechas nulas) sin producir un 500; los eventos con evidencia completa se muestran como hasta ahora (entradas, causante, beneficiarios y resultado).

---

## [0.2.0] - 2026-10-12

### ✅ Agregado

- **Logo oficial de CRM Lite** (#64)
  - Reemplaza el logo temporal por el logo oficial de Tu Pensión Inteligente.
  - Se renderiza en la cabecera y en la pantalla de acceso de CRM Lite.
  - Servido como recurso estático local (`app/web/static/img/official-logo-on-light.png` y `app/web/static/img/official-logo-on-dark.png`), sin cargas desde orígenes externos.
  - Variante para tema oscuro (`official-logo-on-dark.png`) seleccionada vía CSS.
  - Texto alternativo accesible en ambas instancias.

### 🔒 Seguridad

- **Mitigación de CVE-2026-85091 (zlib)** (#65)
  - Se fija `zlib=1.3.2-r1` en la imagen de la aplicación (`Dockerfile`).
  - Se actualiza `zlib` en la imagen de Caddy (`deployment/caddy/Dockerfile`).
  - Se actualizan los contratos de supply chain y el test de imagen de la aplicación.

## [0.1.0] - 2026-07-31

### ✅ Agregado

- **Validación Completa MVP1**
  - Validación de conexión a PostgreSQL
  - Validación de catálogos (género, estado civil, AFP)
  - Flujo completo de registro (persona → lead → consentimientos)
  - Documentación de validación detallada

- **Documentación Actualizada**
  - README.md mejorado con estado de validación
  - Nuevo documento: [docs/MVP1_VALIDACION.md](docs/MVP1_VALIDACION.md)
  - Nuevo documento: [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
  - Nuevo documento: CHANGELOG.md (este archivo)

- **Herramientas de Validación**
  - Script: `test_connection.py` - Validar conexión a BD
  - Script: `test_solicitud_flow.py` - Validar flujo de registro
  - Script: `explore_schema.py` - Explorar estructura de tablas
  - Script: `generar_informe.py` - Generar reporte de validación
  - Script: `check_postgres.py` - Verificar usuarios de BD
  - Script: `check_streamlit.py` - Verificar importación de Streamlit
  - Script: `list_tables.py` - Listar tablas del esquema

- **GitHub Actions CI/CD**
  - Workflow `.github/workflows/ci.yml` para:
    - Linting (ruff, black)
    - Type checking (mypy)
    - Pruebas unitarias
    - Cobertura de código
    - Auditoría de seguridad

### 🔧 Corregido

- **Problema 1:** Credenciales incorrectas en `.env`
  - Usuario `tpi_app` no existe
  - Solución: Usar usuario `postgres` con contraseña correcta

- **Problema 2:** Módulo `psycopg.pool` no disponible
  - psycopg v3 separó pool en paquete independiente
  - Solución: Instalar `psycopg-pool` y actualizar imports

- **Problema 3:** URL de conexión con prefijo SQLAlchemy
  - `ConnectionPool` requiere formato `postgresql://` no `postgresql+psycopg://`
  - Solución: Actualizar `get_database_url()` en `app/config/settings.py`

- **Problema 4:** Parámetro `row_factory` inválido en constructor
  - `psycopg_pool.ConnectionPool` no acepta `row_factory` en constructor
  - Solución: Aplicar `row_factory` en `get_connection()` después de obtener conexión

- **Problema 5:** Columnas faltantes en INSERT de `leads`
  - Query no incluía columnas requeridas: `fecha_ingreso`, `origen_lead`, `fuente_actual`
  - Solución: Agregar columnas y parámetros correspondientes

- **Problema 6:** Columna `id_persona` faltante en INSERT de `consentimientos`
  - Tabla requiere `id_persona` pero no se insertaba
  - Solución: Incluir `id_persona` en parámetros de INSERT

### 📋 Cambios

- Actualizar archivo `.env` con credenciales correctas
- Actualizar `app/config/settings.py` para URL de conexión correcta
- Actualizar `app/database/connection.py` para psycopg_pool compatible
- Actualizar `app/repositories/solicitud_repository.py` con INSERT correcto
- README.md completamente reescrito con información de validación
- Agregar documentación de seguridad en SECURITY.md

### 📚 Documentación

- [x] Documento de validación MVP1 completo
- [x] Estado del proyecto documentado
- [x] Roadmap detallado
- [x] Métricas y cobertura
- [x] Pasos siguiente claros

---

## [0.0.1] - 2026-07-30 (Initial Release - Anterior a esta validación)

### ✅ Agregado

- Estructura base Streamlit con 3 páginas
- Conexión a PostgreSQL con pool
- Modelo de datos completo
- Validadores (RUT, email, teléfono)
- Catálogos dinámicos
- Suite de pruebas unitarias
- GitHub Actions workflow
- Documentación arquitectura
- Docker y docker-compose
- License MIT
- Contributing guide
- Security policy

### 📋 Conocidos

- Sin autenticación (es MVP)
- Sin rate limiting (es MVP)
- Validadores secundarios necesitan revisión

---

## Cómo Contribuir

Para contribuir cambios a este changelog:

1. Crea una rama: `git checkout -b feature/description`
2. Haz tus cambios
3. Actualiza este CHANGELOG.md con:
   - Sección `[Unreleased]` si aún no existe
   - Categorías: Added, Changed, Deprecated, Removed, Fixed, Security
4. Commit con mensaje descriptivo
5. Push y abre Pull Request

---

## Versionado

Este proyecto sigue [Semantic Versioning](https://semver.org/):

- MAJOR: Cambios incompatibles
- MINOR: Funcionalidades nuevas compatibles
- PATCH: Correcciones de bugs

**Versión Actual:** 0.2.0  
**Próxima Versión:** 0.3.0 (por definir)

---

## Histórico de Versiones

| Versión | Fecha | Estado | Hito |
|---------|-------|--------|------|
| 0.2.0 | 12 Oct 2026 | 🚀 RELEASE DEV | Logo oficial de CRM Lite + mitigación zlib |
| 0.1.0 | 31 Jul 2026 | ✅ VALIDADO | MVP1 Completado |
| 0.0.1 | 30 Jul 2026 | ✅ INICIAL | Estructura Base |

---

**Última actualización:** 12 Octubre 2026  
**Responsable:** Equipo TPI Back-office  
**Contacto:** dev@tupensioninteligente.cl
