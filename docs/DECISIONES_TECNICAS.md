# Decisiones Técnicas - Etapa 3

Documento que detalla las decisiones arquitectónicas tomadas en la implementación de la capa de datos y servicios.

## Decisiones Arquitectónicas

### H2.4. Eventos de notificacion post-commit

**Decision**: Publicar `LeadCreatedEvent` mediante una abstraccion de
publisher despues de confirmar PostgreSQL; SNS es solo el primer adapter.

**Justificacion**:
- Evita notificar leads que no llegaron a commit.
- Mantiene email, SMS y WhatsApp fuera de `SolicitudService`, Repository y UI.
- Reduce privacidad por diseno: el contrato tiene solo IDs, timestamp UTC,
  ambiente y fuente.
- Permite reemplazar SNS directo por Transactional Outbox sin cambiar el
  formulario ni el modelo de leads.

**Semantica H2.4**: la persistencia del lead es primaria. Un fallo de SNS se
registra de forma segura y no revierte el commit. La entrega garantizada,
reintentos durables y workers quedan para una evolucion posterior.

### 1. Patrón Repository

**Decisión**: Implementar patrón Repository explícito.

**Justificación**:
- Separación clara entre lógica de BD y servicios
- Facilita testing (repositorio mockeable)
- Preparado para migrar a ORM completo (SQLAlchemy) en futuro
- Cada repositorio maneja un dominio (solicitudes, personas, etc)

**Alternativa rechazada**: ORM directo en servicios
- Menos flexible para queries complejas
- Más difícil de testear

### 2. Transacciones Atómicas

**Decisión**: Implementar inserción de persona + lead + consentimientos como transacción única.

**Justificación**:
- Garantiza consistencia: no habrá leads huérfanos
- Si falla consentimiento, se revierte todo (no crea usuario fantasma)
- Rollback automático en excepción

**Código**:
```python
with get_db_connection() as conn:
    try:
        # Insert persona, lead, consentimientos
        conn.commit()  # Sucede automáticamente al salir del context
    except Exception:
        conn.rollback()  # Automático en excepción
        raise
```

### 3. Deduplicación de Personas

**Decisión**: Si persona existe (por RUT), reutilizar ID en lugar de crear duplicado.

**Justificación**:
- Una persona puede tener múltiples solicitudes
- RUT es único y estable
- Evita duplicados en tabla personas
- Mejora auditoría (un RUT = un ID)

**Implementación**:
```python
existing = get_persona_by_rut(rut)
if existing:
    return existing["id_persona"]  # ← reutilizar
```

### 4. Enmascaramiento en Display Layer

**Decisión**: Aplicar enmascaramiento SOLO en display (UI), no en BD.

**Justificación**:
- Datos permanecen íntegros en BD (no modificados)
- Permite mostrar versión enmascarada o completa
- Compatible con auditoría (acceso completo en admin)
- Performance: enmascaramiento es local, sin SQL

**Niveles**:
- `SolicitudService.get_solicitud_detalle()` → sin máscara (admin/backend)
- `SolicitudService.get_solicitud_detalle_masked()` → con máscara (UI/usuario)

### 5. Catálogos como UUID

**Decisión**: Usar UUID para FK de catálogos (no nombres de string).

**Justificación**:
- Integridad referencial garantizada (FK)
- Independiente de descripción (puedo cambiar texto sin romper referencias)
- Estándar en diseño de BD moderno
- Soportado nativamente en PostgreSQL

**Validación en Servicio**:
```python
def _validate_catalogo_ids(genero_id, estado_civil_id, afp_id):
    # Verificar que existan en BD antes de insertar
```

### 6. Validación en Dos Niveles

**Decisión**: Validación en Pydantic + Servicio + Repositorio.

**Justificación**:

| Nivel | Validaciones | Qué |
|-------|--------------|-----|
| **Pydantic** | Tipos, formatos básicos | RUT formato, email estructura |
| **Servicio** | Business logic | IDs de catálogo existen, consentimientos OK |
| **Repositorio** | Integridad de datos | FKs válidas (psycopg lo rechaza si falla) |

### 7. Paginación en Repository

**Decisión**: Implementar paginación (limit/offset) en nivel de repositorio.

**Justificación**:
- No cargar 10000+ registros en memoria
- Servicio solo pasa page/page_size
- Repository calcula offset
- Performance en listas grandes

**Uso**:
```python
def get_solicitudes_lista(page=1, page_size=10):
    offset = (page - 1) * page_size
    solicitudes, total = repository.get_all_solicitudes(limit, offset)
```

### 8. JOINs Seguros con LEFT JOIN

**Decisión**: Usar LEFT JOIN en lugar de INNER JOIN para catálogos.

**Justificación**:
- Catálogos pueden ser NULL (no fuerza su existencia)
- Retorna solicitud aunque catálogo no se encuentre
- Importante para depuración (vs error silencioso)

**Query**:
```sql
FROM tpi.leads l
LEFT JOIN tpi.catalogo_genero cg ON l.genero_id = cg.id_genero
-- ↑ Si genero_id no existe, cg.descripcion = NULL
```

### 9. Enumeraciones vs UUIDs

**Decisión**: UUIDs para FK en lugar de enums.

**Justificación**:
- PostgreSQL ENUM es rígido (requiere ALTER TYPE para cambios)
- UUIDs son flexibles (solo cambiar datos en tabla)
- Preparado para futuro (agregar nuevos géneros, AFP, etc)

**Rechazo**: Usar ENUM
- Requería cambios de esquema en producción
- Menos flexible

---

## Limitaciones Pendientes (Etapa 5)

### 1. Sin Edición de Solicitudes
- **Limitación**: Las solicitudes registradas son inmutables
- **Impacto**: Usuario no puede corregir datos
- **Solución futura**: Endpoint PATCH con auditoría de cambios

### 2. Sin Eliminación de Solicitudes
- **Limitación**: No hay soft-delete ni hard-delete
- **Impacto**: Datos persisten indefinidamente
- **Solución futura**: Soft-delete con estado = 'eliminada'

### 3. Sin Auditoría de Cambios
- **Limitación**: No hay tabla de logs de quién cambió qué
- **Impacto**: Imposible trazar historial de cambios
- **Solución futura**: Tabla `audit_log` con triggers en PostgreSQL

### 4. Sin Envío de Notificaciones
- **Limitación**: No se envían emails de confirmación
- **Impacto**: Usuario no recibe confirmación de registro
- **Solución futura**: Integración con SendGrid o AWS SES

### 5. Sin Búsqueda Avanzada
- **Limitación**: Solo filtro simple por RUT
- **Impacto**: No puedo buscar por fecha rango, estado, etc
- **Solución futura**: Full-text search en PostgreSQL

### 6. Sin Caché
- **Limitación**: Cada request consulta BD (sin Redis)
- **Impacto**: Performance degrada con usuarios concurrentes
- **Solución futura**: Caché en Redis para catálogos y consultas frecuentes

### 7. Sin Autenticación
- **Limitación**: Acceso abierto (cualquiera puede registrar)
- **Impacto**: **CRÍTICO para producción** - requiere OAuth2/JWT
- **Solución futura**: Implementar autenticación en Etapa 4

### 8. Sin Rate Limiting
- **Limitación**: No hay límite de requests por usuario
- **Impacto**: Vulnerable a abuso (DDoS, spam)
- **Solución futura**: Rate limiter en API Gateway o Streamlit

### 9. Sin Validación de Catálogos en BD
- **Limitación**: Se valida en Servicio (llamadas SQL extra)
- **Impacto**: Performance (3 queries para validar IDs)
- **Solución futura**: Usar CHECK constraints en PostgreSQL

### 10. Sin Backups Automatizados
- **Limitación**: No hay estrategia de backup
- **Impacto**: Pérdida de datos en desastre
- **Solución futura**: Backup diario a S3 (AWS)

---

## Errores Prevenidos

### 1. RUT Inválido (módulo 11 incorrecto)
```python
# ✅ Rechazado por validador
validate_rut("12345678-4")  # DV incorrecto

# ✅ Aceptado
validate_rut("12345678-5")  # DV correcto
```

### 2. Teléfono Fijo en lugar de Celular
```python
# ✅ Rechazado (código de teléfono fijo)
validate_phone("+56212345678")  # '2' = fijo

# ✅ Aceptado (código de celular)
validate_phone("+56912345678")  # '9' = celular
```

### 3. Email Inválido
```python
# ✅ Rechazado
validate_email("invalid@domain")  # Sin TLD

# ✅ Aceptado
validate_email("user@domain.com")
```

### 4. ID de Catálogo No Existe
```python
# ✅ Rechazado en servicio
solicitud_service.registrar_solicitud({
    ...
    "afp_id": "00000000-0000-0000-0000-000000000000",  # No existe
})  # → ValueError: ID de AFP inválido

# ✅ Aceptado
solicitud_service.registrar_solicitud({
    ...
    "afp_id": "12345678-1234-1234-1234-123456789012",  # Existe en BD
})
```

### 5. Lead Huérfano (sin persona)
```python
# ✅ Transacción atómica
# Si create_persona() falla, NO se crea lead
# Si create_lead() falla, se rollback todo

# ❌ Evitado: lead sin persona
```

### 6. Nombre con Números
```python
# ✅ Rechazado
PersonaData(nombre_completo="Juan 123")  # ValueError

# ✅ Aceptado
PersonaData(nombre_completo="Juan Carlos")
```

### 7. Fecha Futura
```python
# ✅ Rechazado
PersonaData(fecha_nacimiento=date(2026, 12, 31))  # Futura

# ✅ Aceptado
PersonaData(fecha_nacimiento=date(1990, 1, 1))
```

### 8. Consentimientos Incompletos
```python
# ✅ Rechazado
ConsentimientosData(
    acepta_terminos=False,  # ← FALLA
    acepta_politica_privacidad=True,
    finalidad_contacto=True,
)  # ValueError: Todos deben ser True

# ✅ Aceptado
ConsentimientosData(
    acepta_terminos=True,
    acepta_politica_privacidad=True,
    finalidad_contacto=True,
)
```

---

## Métricas de Cobertura (Etapa 3)

| Componente | Pruebas | Coverage |
|-----------|---------|----------|
| Validadores | 80+ tests | 95%+ |
| Repositorio | Integración | 80%+ (Etapa 5) |
| Servicio | Integración | 75%+ (Etapa 5) |
| Modelos | Implícito en Pydantic | 90%+ |

---

## Próximas Etapas

### Etapa 4: UI Streamlit
- Página 1: Registrar solicitud (formulario)
- Página 2: Consultar solicitudes (tabla)
- Página 3: Trazabilidad (métricas)
- Componentes reutilizables

### Etapa 5: Testing y Seguridad
- Pruebas E2E
- Pruebas de carga
- Auditoría de seguridad
- Documentación de deployment
- Pruebas en producción (staging)

### Post-MVP: Producción
- Migrar a PostgreSQL RDS (AWS)
- Implementar autenticación OAuth2
- Agregar API REST (FastAPI)
- Integración con servicios de SMS/Email
- Monitoreo y alertas
