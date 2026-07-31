# 🔐 Guía de Seguridad

**Documento de Políticas y Consideraciones de Seguridad**

> **⚠️ MVP Importante**: Este es un prototipo demostrativo. Para producción se requieren implementaciones adicionales de seguridad.

---

## 📋 Tabla de Contenidos

1. [Principios de Seguridad](#principios-de-seguridad)
2. [Amenazas Prevenidas](#amenazas-prevenidas)
3. [Validación de Inputs](#validación-de-inputs)
4. [Protección de Datos Sensibles](#protección-de-datos-sensibles)
5. [Seguridad de Base de Datos](#seguridad-de-base-de-datos)
6. [Configuración Segura](#configuración-segura)
7. [Autenticación y Autorización](#autenticación-y-autorización)
8. [Auditoría y Logging](#auditoría-y-logging)
9. [Checklist de Seguridad](#checklist-de-seguridad)
10. [Para Producción](#para-producción)

---

## 🛡️ Principios de Seguridad

### Defense in Depth (Defensa en Profundidad)

La aplicación implementa múltiples capas de validación:

```
Cliente (Streamlit)
    ↓ Validación básica
Modelos (Pydantic)
    ↓ Validación + normalización
Repositorio (Psycopg)
    ↓ Queries parametrizadas
Base de Datos
    ↓ Constraints + Triggers
```

### Principio de Menor Privilegio

- ✅ Usuarios de BD con permisos mínimos
- ✅ Procesos ejecutan con privilegios mínimos
- ✅ Acceso a datos enmascarado por defecto

### Validación Positiva

- ✅ Whitelist de valores permitidos
- ✅ Rechazo de todo lo no permitido
- ✅ Tipado fuerte con Pydantic

---

## ⚔️ Amenazas Prevenidas

### 1. SQL Injection ✅ PREVENIDO

**Cómo se previene:**

```python
# ❌ INSEGURO (no usado)
cur.execute(f"INSERT INTO personas VALUES ('{rut}')")

# ✅ SEGURO (usado)
cur.execute(
    "INSERT INTO personas (rut, ...) VALUES (%s, ...)",
    (rut, ...)  # Parámetros separados
)
```

**Validación en código:**
- `app/repositories/solicitud_repository.py` - Todas las queries usan parámetros
- `scripts/security_audit.py` - Verifica ausencia de f-strings en execute()

**Test:**
```bash
pytest tests/security/test_security.py::TestSQLInjectionPrevention -v
```

---

### 2. XSS (Cross-Site Scripting) ✅ PREVENIDO

**Cómo se previene:**

Streamlit escapa automáticamente HTML en salida, pero validamos input:

```python
# Validación en Pydantic
class PersonaData(BaseModel):
    nombre_completo: str
    
    @field_validator('nombre_completo')
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Rechaza caracteres especiales peligrosos
        if re.search(r'[<>\"\'`]', v):
            raise ValueError('Nombre contiene caracteres no permitidos')
        return v
```

**Test:**
```bash
pytest tests/security/test_security.py::TestXSSPrevention -v
```

---

### 3. Command Injection ✅ PREVENIDO

**No se ejecutan comandos shell en la aplicación.**

Verificación:
```bash
python scripts/security_audit.py  # Busca os.system, subprocess.call
```

---

### 4. Path Traversal ✅ PREVENIDO

**No hay acceso a filesystem.** La aplicación solo:
- Lee: `.env`, archivos de código
- Escribe: Logs únicamente
- No expone rutas a usuarios

---

### 5. Information Disclosure ✅ PREVENIDO

**Enmascaramiento automático de datos sensibles:**

```python
# Antes (BD)
{
    "rut": "12345678-5",
    "email": "juan@example.com",
    "telefono": "+56912345678"
}

# Después (UI)
{
    "rut": "12.***.***-5",
    "email": "ju***@example.com",
    "telefono": "+56 9 **** 5678"
}
```

**Implementación:**
- `app/security/masking.py` - Funciones de masking
- Aplicado automáticamente en: `get_solicitudes_lista(masked=True)`
- Admin puede ver datos sin máscaras (en producción, requeriría autenticación)

---

### 6. Broken Authentication ⚠️ LIMITADO

**MVP Status:**
- ❌ Sin autenticación de usuario
- ❌ Sin sesiones
- ✅ Con protección de secretos en BD

**Para Producción:** Ver sección "Para Producción"

---

### 7. Broken Authorization ⚠️ LIMITADO

**MVP Status:**
- ❌ Sin roles/permisos de usuario
- ✅ Con enmascaramiento de datos por defecto
- ✅ Con separación de datos (no hay acceso cruzado de clientes)

**Para Producción:** Ver sección "Para Producción"

---

### 8. CSRF (Cross-Site Request Forgery) ✅ PREVENIDO

**Streamlit es stateless por defecto.** Cada acción es POST directo sin tokens predecibles.

---

## ✅ Validación de Inputs

### Validadores Implementados

#### 1. RUT Chileno (`app/validators/rut.py`)

```python
def validate_rut(rut: str) -> bool:
    """Valida RUT usando módulo 11."""
    # 1. Normaliza: 12.345.678-5 → 12345678-5
    # 2. Verifica dígito con módulo 11
    # 3. Rechaza si formato/dígito inválido
```

**Ejemplos:**
- ✅ `12345678-5` (válido)
- ✅ `12.345.678-5` (normalizado)
- ❌ `12345678-6` (dígito incorrecto)
- ❌ `1234567-5` (muy corto)
- ❌ `12345678'; DROP TABLE;` (SQL injection bloqueado)

**Test:**
```bash
pytest tests/unit/test_rut.py -v
```

#### 2. Email (`app/validators/email.py`)

```python
def validate_email(email: str) -> bool:
    """Valida email RFC 5321."""
    # 1. Formato básico con regex
    # 2. Máximo 254 caracteres
    # 3. No permite caracteres peligrosos
```

**Ejemplos:**
- ✅ `juan@example.com`
- ❌ `juan @example.com` (espacio)
- ❌ `juan<script>@example.com` (XSS)
- ❌ `a` * 255 + `@test.com` (muy largo)

**Test:**
```bash
pytest tests/unit/test_email.py -v
```

#### 3. Teléfono (`app/validators/phone.py`)

```python
def validate_phone(phone: str) -> bool:
    """Valida teléfono chileno formato +56."""
    # 1. Normaliza: 09 1234 5678 → +56912345678
    # 2. Verifica: +56 9 XXXX XXXX
    # 3. 9 dígitos después del código país
```

**Ejemplos:**
- ✅ `+56912345678`
- ✅ `09 1234 5678` (normalizado)
- ✅ `912345678` (convertido)
- ❌ `02 1234 5678` (fijo, no celular)
- ❌ `+555912345678` (código país incorrecto)

**Test:**
```bash
pytest tests/unit/test_phone.py -v
```

#### 4. Fecha de Nacimiento

```python
# En Pydantic validator
@field_validator('fecha_nacimiento')
def validate_birth_date(cls, v):
    # Debe ser datetime válido
    # No puede ser futura
    # Debe ser después de 1920
```

**Ejemplos:**
- ✅ `1990-01-15`
- ❌ `2025-01-01` (futura)
- ❌ `1800-01-01` (antes de 1920)
- ❌ `invalid` (formato incorrecto)

#### 5. Nombre Completo

```python
@field_validator('nombre_completo')
def normalize_name(cls, v):
    # 3-200 caracteres
    # Sin números puros
    # Solo caracteres alfanuméricos + acentos + espacios
```

**Ejemplos:**
- ✅ `Juan Carlos Pérez`
- ❌ `123` (solo números)
- ❌ `<script>alert('xss')</script>` (caracteres especiales)
- ❌ `A` * 300 (muy largo)

---

### Tipos de Validación

```
3 Niveles de Validación
├── Cliente (Streamlit)
│   ├── Campos requeridos
│   ├── Formato visual
│   └── Feedback inmediato
│
├── Servidor (Pydantic)
│   ├── Tipo de dato
│   ├── Rango/longitud
│   ├── Patrón regex
│   └── Lógica de negocio
│
└── Base de Datos (PostgreSQL)
    ├── Foreign keys
    ├── Not null constraints
    ├── Check constraints
    └── Índices únicos
```

---

## 🔒 Protección de Datos Sensibles

### Enmascaramiento (Masking)

**Dónde se aplica:**
- ✅ Vistas de usuario en Streamlit (`masked=True`)
- ✅ Exportación de datos (CSV)
- ✅ Logs de auditoría
- ❌ Base de datos (datos originales)
- ❌ Vistas admin (si hay autenticación)

**Campos enmascarados:**
- `rut`: `12.***.***-K`
- `email`: `us***@example.com`
- `telefono`: `+56 9 **** XXXX`

**Implementación:**
```python
# app/security/masking.py
masked = mask_row_for_display({
    "rut": "12345678-5",
    "email": "juan@example.com",
})
# Resultado:
# {
#     "rut": "12.***.***-5",
#     "email": "ju***@example.com"
# }
```

**Cómo verificar:**
```bash
pytest tests/security/test_security.py::TestSensitiveDataHandling -v
```

### Almacenamiento Seguro

- ✅ Base de datos encriptada (en producción con AWS RDS)
- ✅ Credenciales en `.env` (no en repo)
- ✅ Transacciones ACID (rollback automático en error)
- ✅ Conexión con SSL (en producción)

---

## 🗄️ Seguridad de Base de Datos

### Conexión Segura

```python
# app/database/connection.py
_connection_pool = ConnectionPool(
    conninfo="host=... user=tpi_app password=...",
    min_size=1,
    max_size=5,
    timeout=10,
    recycle=3600  # Recicla conexiones cada hora
)
```

**Características:**
- ✅ Connection pooling (reutiliza conexiones)
- ✅ Timeout (evita conexiones colgadas)
- ✅ Credenciales desde variables de entorno
- ✅ Auto-reciclaje de conexiones

### Queries Parametrizadas

```python
# ✅ SEGURO
cursor.execute(
    "SELECT * FROM personas WHERE rut = %s AND email = %s",
    (rut, email)  # Parámetros separados
)

# ❌ INSEGURO (NO USADO)
cursor.execute(f"SELECT * FROM personas WHERE rut = '{rut}'")
```

**Verificación:**
```bash
python scripts/security_audit.py  # Busca patrones inseguros
```

### Manejo de Transacciones

```python
# Garantiza atomicidad: todo o nada
with get_db_connection() as conn:
    with conn.cursor() as cur:
        # Insertar persona
        cur.execute("INSERT INTO personas ...")
        
        # Insertar lead
        cur.execute("INSERT INTO leads ...")
        
        # Insertar consentimientos
        cur.execute("INSERT INTO consentimientos ...")
        
        # Si algo falla, rollback automático
        # Si todo está ok, commit automático
```

### Permisos de BD

**Usuario de aplicación (recomendado):**
```sql
-- Crear usuario con permisos mínimos
CREATE USER tpi_app WITH PASSWORD 'contraseña_segura';

-- Solo SELECT, INSERT, UPDATE en tablas específicas
GRANT SELECT ON tpi.catalogo_* TO tpi_app;
GRANT SELECT, INSERT, UPDATE ON tpi.personas TO tpi_app;
GRANT SELECT, INSERT, UPDATE ON tpi.leads TO tpi_app;
GRANT SELECT, INSERT ON tpi.consentimientos TO tpi_app;

-- NO DELETE, NO DROP TABLE, NO ALTER
```

---

## ⚙️ Configuración Segura

### Variables de Entorno

**Archivo `.env` (LOCAL ONLY, NO COMMITEADO):**
```bash
# ✅ Correcto (en .gitignore)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=tpi_local
DATABASE_USER=tpi_app
DATABASE_PASSWORD=contraseña_local

# ❌ NUNCA en .env
# DATABASE_PASSWORD=abc123  # No usar contraseñas débiles
# DATABASE_PASSWORD=prod_password  # No usar contraseña de producción
```

**Verificación:**
```bash
# .gitignore debe contener
cat .gitignore | grep "\.env"

# .env NO debe estar en git
git log --all --full-history -- .env  # No debe haber commits
```

### Secretos Hardcodeados

**Verificación automática:**
```bash
python scripts/security_audit.py  # Busca secrets hardcodeados
```

**Patrones detectados:**
- `DATABASE_PASSWORD = "..."`
- `API_KEY = "..."`
- `SECRET_KEY = "..."`
- `password = "..."`
- `token = "..."`

---

## 🔑 Autenticación y Autorización

### MVP (Sin Autenticación)

**Limitaciones:**
- ❌ No hay login de usuario
- ❌ No hay control de acceso
- ⚠️ Solo seguridad por red (local)
- ✅ Enmascaramiento de datos por defecto

**Para usar en producción:**
- Desplegar detrás de VPN o firewall
- Limitar acceso por IP
- O implementar autenticación (ver abajo)

### Para Producción: Autenticación

**Opciones recomendadas:**

#### 1. OAuth2 + JWT

```python
# Ejemplo (no implementado en MVP)
from fastapi import Depends, HTTPException
from jose import JWTError, jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return username
```

#### 2. Azure AD / Entra ID

```python
# Integración con Microsoft Identity
from msal import PublicClientApplication

app = PublicClientApplication(config_dict=config)
result = app.acquire_token_by_username_password(
    username=email,
    password=password,
    scopes=["https://graph.microsoft.com/.default"]
)
```

#### 3. Cognito (AWS)

```python
# Integración con AWS Cognito
import boto3

cognito = boto3.client('cognito-idp')
response = cognito.initiate_auth(
    ClientId=CLIENT_ID,
    AuthFlow='USER_PASSWORD_AUTH',
    AuthParameters={
        'USERNAME': email,
        'PASSWORD': password
    }
)
```

### Para Producción: Autorización (RBAC)

**Implementar roles:**

```python
# Ejemplo (no implementado en MVP)
class Role(Enum):
    ADMIN = "admin"       # Ver todo, editar, eliminar
    OPERADOR = "operador" # Ver todo, crear
    USUARIO = "usuario"   # Ver sus datos, crear solicitudes

# En endpoint
async def get_solicitudes(
    current_user: User = Depends(get_current_user)
):
    if current_user.role == Role.ADMIN:
        # Ver todas las solicitudes
        return db.get_all_solicitudes(masked=False)
    else:
        # Ver solo solicitudes del usuario
        return db.get_user_solicitudes(current_user.id, masked=True)
```

---

## 📋 Auditoría y Logging

### Logging de Auditoría (Futuro)

**Eventos a registrar:**
- Registro de solicitudes (quién, cuándo, qué datos)
- Accesos a datos sensibles
- Cambios en solicitudes
- Errores de validación
- Intentos de acceso no autorizado

**Implementación (recomendada):**

```python
# app/security/audit.py (a crear)
import logging

audit_logger = logging.getLogger("audit")

class AuditEvent(BaseModel):
    timestamp: datetime
    user_id: str
    action: str  # "create", "read", "update", "delete"
    resource: str  # "solicitud", "persona"
    resource_id: str
    changes: dict  # Si es update
    ip_address: str
    result: str  # "success", "failure"

def log_audit_event(event: AuditEvent):
    audit_logger.info(json.dumps(event.dict()))
    # Guardar en BD: tabla tpi.audit_logs
```

### Logs de Error (Actualmente)

**Ubicación:** `logs/backoffice.log`

**Seguridad:**
- ❌ NO incluye datos sensibles en logs
- ✅ RUT, email, teléfono son enmascarados si aparecen
- ✅ Stacktraces no exponen rutas del sistema

**Verificar logs:**
```bash
# Ver últimos errores
tail -f logs/backoffice.log | grep ERROR

# Buscar intentos sospechosos
grep -i "invalid\|error\|exception" logs/backoffice.log
```

---

## ✅ Checklist de Seguridad

### Antes de Desplegar a Producción

- [ ] Cambiar contraseña de BD (usar contraseña fuerte >20 caracteres)
- [ ] Verificar `.gitignore` contiene `.env`
- [ ] Crear archivo `.env` con credenciales de producción
- [ ] Ejecutar `python scripts/security_audit.py` (todas las pruebas deben pasar)
- [ ] Ejecutar `pytest tests/security/` (todos los tests deben pasar)
- [ ] Ejecutar `pytest tests/e2e/` (validar flujos)
- [ ] Configurar SSL/TLS para BD
- [ ] Configurar CORS si tiene frontend separado
- [ ] Configurar rate limiting en API (si hay)
- [ ] Habilitar HTTPS en Streamlit
- [ ] Configurar WAF (Web Application Firewall) en AWS
- [ ] Realizar penetration testing
- [ ] Auditoría de código por terceros
- [ ] Cumplimiento LGPD/GDPR (datos personales)

### Durante Operación

- [ ] Revisar logs diariamente
- [ ] Hacer backup de BD diariamente
- [ ] Actualizar dependencias mensualmente
- [ ] Monitorear intentos fallidos de login
- [ ] Revisar cambios en datos sensibles
- [ ] Mantener documentación de incidentes

---

## 🚀 Para Producción

### Cambios Requeridos

#### 1. Autenticación
```python
# Antes (MVP)
# Sin autenticación

# Después (Producción)
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

authenticator.login()

if st.session_state["authentication_status"] is None:
    st.warning("Por favor, inicia sesión")
    st.stop()
```

#### 2. HTTPS/SSL
```bash
# Streamlit con HTTPS
streamlit run app/streamlit_app.py \
    --server.sslCertFile=/etc/ssl/certs/cert.pem \
    --server.sslKeyFile=/etc/ssl/private/key.pem
```

#### 3. Encriptación de BD
```bash
# AWS RDS con encriptación
aws rds create-db-instance \
    --db-instance-identifier tpi-db-prod \
    --engine postgres \
    --storage-encrypted \
    --kms-key-id arn:aws:kms:...
```

#### 4. Secrets Manager
```python
# Usar AWS Secrets Manager en lugar de .env
import boto3

secrets_client = boto3.client('secretsmanager')
secret = secrets_client.get_secret_value(
    SecretId='tpi/database/password'
)
password = json.loads(secret['SecretString'])['password']
```

#### 5. WAF (Web Application Firewall)
```bash
# Configurar AWS WAF para Streamlit
# - Rate limiting: 2000 req/5min por IP
# - Geo-blocking: Solo Chile
# - IP whitelisting: Solo redes conocidas
```

#### 6. Monitoreo
```python
# Cloudwatch integration
import logging

cloudwatch_handler = logging.handlers.WatchedFileHandler(
    '/var/log/streamlit/app.log'
)
logging.root.addHandler(cloudwatch_handler)
```

### Migración a Producción

**Paso 1: Preparar BD de producción**
```bash
# Dump de datos local
pg_dump tpi_local > backup_local.sql

# Restaurar en producción
psql tpi_prod < backup_local.sql

# Verificar
psql tpi_prod -c "SELECT COUNT(*) FROM tpi.personas"
```

**Paso 2: Configurar secretos**
```bash
# En AWS Systems Manager Parameter Store
aws ssm put-parameter \
    --name /tpi/prod/db-password \
    --value "contraseña_segura" \
    --type SecureString
```

**Paso 3: Deploy a ECS/Fargate**
```bash
# Build Docker image
docker build -t tpi-backoffice:1.0.0 .

# Push a ECR
aws ecr get-login-password | docker login ...
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/tpi-backoffice:1.0.0

# Deploy a Fargate
aws ecs create-service \
    --cluster tpi-prod \
    --service-name backoffice \
    --task-definition tpi-backoffice:1
```

**Paso 4: Configurar Alarms**
```bash
# CloudWatch alarms para:
# - CPU > 80%
# - Memory > 80%
# - Error rate > 1%
# - Response time > 2s
```

---

## 📞 Reporte de Vulnerabilidades

Si encuentras una vulnerabilidad:

1. **NO** la publiques en GitHub
2. Envía email a: `security@tupensioninteligente.cl`
3. Incluye:
   - Descripción de la vulnerabilidad
   - Pasos para reproducir
   - Impacto
   - Solución sugerida (si tienes)

**Respuesta esperada:** 48 horas

---

## 📚 Referencias

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- CWE/SANS Top 25: https://cwe.mitre.org/top25/
- Pydantic Security: https://docs.pydantic.dev/latest/
- PostgreSQL Security: https://www.postgresql.org/docs/current/sql-syntax.html#SQL-SYNTAX-IDENTIFIERS
- Streamlit Security: https://docs.streamlit.io/library/admin-guide/security

---

**Última actualización:** 2024  
**Versión:** 1.0.0 MVP
