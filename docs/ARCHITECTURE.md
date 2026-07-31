# Diagrama de Arquitectura - Etapa 3

## Flujo de Registro de Solicitud

```mermaid
graph TD
    A["🖥️ Streamlit UI<br/>(Etapa 4)"] -->|"RegistrarSolicitudRequest<br/>(JSON)"| B["SolicitudService"]
    B -->|"Valida IDs<br/>de catálogo"| C{{"ID Catálogo<br/>válido?"}}
    C -->|"❌ No"| D["ValueError"]
    C -->|"✅ Sí"| E["SolicitudRepository"]
    E -->|"1️⃣ get_persona_by_rut"| F[("PostgreSQL")]
    F -->|"Persona existe?"| G{{"RUT<br/>existe?"}}
    G -->|"✅ Sí"| H["Reutilizar id_persona"]
    G -->|"❌ No"| I["2️⃣ create_persona"]
    H --> J["3️⃣ create_lead<br/>+ consentimientos<br/>(TRANSACCIÓN)"]
    I --> J
    J -->|"INSERT persona"| F
    J -->|"INSERT lead"| F
    J -->|"INSERT consentimientos"| F
    J -->|"COMMIT ✅"| K["SolicitudResponse<br/>(id_lead)"]
    K -->|"JSON"| A
    D -->|"Error"| A
```

## Arquitectura en Capas

```mermaid
graph LR
    subgraph UI["🖥️ PRESENTACIÓN (Etapa 4)"]
        A["Streamlit App"]
        B["Páginas"]
        C["Componentes"]
    end
    
    subgraph SERVICE["⚙️ NEGOCIO (Etapa 3)"]
        D["SolicitudService"]
        E["Validaciones"]
        F["Enmascaramiento"]
    end
    
    subgraph REPO["📦 DATOS (Etapa 3)"]
        G["SolicitudRepository"]
        H["CRUD"]
        I["Transacciones"]
    end
    
    subgraph DB["🗄️ BASE DE DATOS"]
        J["PostgreSQL"]
        K["tpi.personas"]
        L["tpi.leads"]
        M["tpi.consentimientos"]
        N["tpi.catálogos"]
    end
    
    A --> D
    B --> D
    C --> D
    
    D --> E
    D --> F
    D --> G
    
    G --> H
    G --> I
    
    H --> J
    I --> J
    
    J --> K
    J --> L
    J --> M
    J --> N
```

## Validación en Tres Niveles

```mermaid
graph TD
    A["Input JSON"] -->|"Datos crudos"| B["1️⃣ Validación Pydantic<br/>(models/solicitud.py)"]
    B -->|"✅ Objeto Python validado"| C["2️⃣ Validación Service<br/>(services/solicitud_service.py)"]
    C -->|"✅ IDs de catálogo existen"| D["3️⃣ Repository CRUD<br/>(repositories/solicitud_repository.py)"]
    D -->|"✅ INSERT con FK constraints"| E["PostgreSQL"]
    E -->|"❌ FK violation"| F["Rechazado"]
    
    B -->|"❌ Tipo inválido<br/>Formato incorrecto"| G["ValueError"]
    C -->|"❌ ID catálogo<br/>no existe"| H["ValueError"]
    D -->|"❌ Error BD<br/>FK violation"| I["Exception"]
    
    G --> J["Error Response"]
    H --> J
    I --> J
```

## Flujo de Consulta de Solicitudes

```mermaid
graph TD
    A["🔍 Usuario consulta<br/>solicitudes"] -->|"get_solicitudes_lista<br/>(page, page_size)"| B["SolicitudService"]
    B -->|"Valida paginación"| C["SolicitudRepository"]
    C -->|"Calcula offset"| D["SELECT * FROM leads<br/>LIMIT + OFFSET"]
    D -->|"LEFT JOIN catálogos"| E["PostgreSQL"]
    E -->|"Lista paginada"| F["SolicitudService"]
    F -->|"¿Masked?"| G{{"Aplicar<br/>enmascaramiento?"}}
    G -->|"✅ Sí"| H["mask_row_for_display<br/>RUT, Email, Teléfono"]
    G -->|"❌ No (Admin)"| I["Datos completos"]
    H --> J["JSON enmascarado"]
    I --> J
    J -->|"Response"| A
```

## Tablas y Relaciones

```mermaid
erDiagram
    PERSONAS ||--o{ LEADS : "1 persona<br/>N leads"
    LEADS ||--o{ CONSENTIMIENTOS : "1 lead<br/>1 consentimiento"
    CATALOGO_AFP ||--o{ LEADS : "0+ leads<br/>per AFP"
    CATALOGO_GENERO ||--o{ LEADS : "0+ leads<br/>per género"
    CATALOGO_ESTADO_CIVIL ||--o{ LEADS : "0+ leads<br/>per estado"
    
    PERSONAS {
        uuid id_persona PK
        string rut UK
        string nombre_completo
        string email
        string telefono
        date fecha_nacimiento
        timestamp created_at
    }
    
    LEADS {
        uuid id_lead PK
        uuid id_persona FK
        uuid genero_id FK
        uuid estado_civil_id FK
        uuid afp_id FK
        decimal saldo_afp
        string comentarios
        string estado_lead
        timestamp created_at
    }
    
    CONSENTIMIENTOS {
        uuid id_consentimiento PK
        uuid id_lead FK
        boolean acepta_terminos
        boolean acepta_politica_privacidad
        boolean finalidad_contacto
        timestamp created_at
    }
    
    CATALOGO_AFP {
        uuid id_afp PK
        string descripcion
        int estado
    }
    
    CATALOGO_GENERO {
        uuid id_genero PK
        string descripcion
        int estado
    }
    
    CATALOGO_ESTADO_CIVIL {
        uuid id_estado_civil PK
        string descripcion
        int estado
    }
```

## Ciclo de Testing

```mermaid
graph TD
    A["Código modificado"] -->|"pytest"| B["Tests Unitarios<br/>(tests/unit/)"]
    B -->|"✅ Pasan"| C["Tests Integración<br/>(tests/integration/)"]
    B -->|"❌ Fallan"| D["Arreglar código"]
    D --> A
    C -->|"✅ Pasan"| E["Coverage > 80%?"]
    C -->|"❌ Fallan"| D
    E -->|"✅ Sí"| F["Linting<br/>(ruff check)"]
    E -->|"❌ No"| D
    F -->|"✅ Limpio"| G["✅ LISTO PARA MERGE"]
    F -->|"❌ Errores"| H["ruff format"]
    H --> A
```

## Enmascaramiento de Datos

```mermaid
graph TD
    A["Datos en BD<br/>(Íntegros)"] -->|"rut: 12345678-5<br/>email: user@domain.com<br/>phone: +56912345678"| B["mask_row_for_display<br/>(security/masking.py)"]
    B -->|"Display (UI)"| C["ENMASCARADO<br/>rut: 12.***.***-5<br/>email: us***@domain.com<br/>phone: +56 9 **** 5678"]
    B -->|"Admin (Internal)"| D["COMPLETO<br/>rut: 12345678-5<br/>email: user@domain.com<br/>phone: +56912345678"]
    C --> E["Streamlit Pages"]
    D --> F["Admin Console"]
```

## Decisiones de Diseño - Alternativas

```mermaid
graph TD
    A["Decisión:<br/>¿Cómo validar FKs?"] 
    A -->|"OPCIÓN A<br/>En Servicio"| B["✅ ELEGIDA<br/>Costo: 3 queries<br/>Beneficio: Control explícito"]
    A -->|"OPCIÓN B<br/>En PostgreSQL<br/>(CHECK constraints)"| C["❌ NO ELEGIDA<br/>Error tardío<br/>Menos control"]
    A -->|"OPCIÓN C<br/>No validar"| D["❌ NO ELEGIDA<br/>Riesgo: FK inválidas"]
    
    E["Decisión:<br/>¿Cómo persistir datos?"]
    E -->|"OPCIÓN A<br/>Transacción atómica"| F["✅ ELEGIDA<br/>Todo o nada<br/>Consistencia garantizada"]
    E -->|"OPCIÓN B<br/>Inserts separados"| G["❌ NO ELEGIDA<br/>Riesgo: leads huérfanos"]
    
    H["Decisión:<br/>¿Enmascarar dónde?"]
    H -->|"OPCIÓN A<br/>En display layer"| I["✅ ELEGIDA<br/>Datos íntegros en BD<br/>Flexible para UI/Admin"]
    H -->|"OPCIÓN B<br/>En la BD"| J["❌ NO ELEGIDA<br/>Datos modificados<br/>Imposible recuperar"]
```

---

**Generado**: 2026-07-31  
**Arquitectura**: Capas (UI → Service → Repository → DB)  
**Patrón**: Service-Repository  
**Validación**: Pydantic + Service + PostgreSQL
