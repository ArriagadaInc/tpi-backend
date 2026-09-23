# H3.3.6 — Matriz de columnas de la exportación ejecutiva XLSX (allowlist F4)

Tarea: `H3.3.6 Exportacion ejecutiva XLSX segura`
Rol: Developer (runtime deepseek). Estado al crear esta matriz: `DEVELOPING`.

## Propósito

Fijar, de forma explícita y revisada, la allowlist de columnas que la exportación
XLSX serializa. La serialización usa **solo** esta allowlist: está prohibido
serializar objetos completos, usar reflexión o descubrir columnas dinámicamente.
Todo campo fuera de esta lista queda excluido de forma estructural (no se lee, no
se copia, no se renderiza).

## Fuente del view model

La allowlist se construye sobre el view model real del listado (la misma consulta
que usa el tablero `/leads`), **no** sobre nombres asumidos:

- Consulta: `SolicitudRepository.get_crm_solicitudes` (SELECT real).
- Campos expuestos por esa consulta:
  `id_lead, id_persona, rut, nombre_completo, email, telefono, genero_id, genero,
  estado_civil_id, estado_civil, afp_id, afp, saldo_afp, comentarios, estado_lead,
  created_at, id_asesor, asesor_nombre`.
- Visibilidad PII para CEO/CTO: `SolicitudService.can_view_full_pii` (ceo/cto ven
  PII completa; el resto no accede a la exportación por RBAC, ver F2).

La exportación reutiliza este view model **tal cual** y proyecta únicamente las
columnas de la allowlist. No se reutiliza `raw_payload`, no se agregan campos del
detalle (`fecha_nacimiento`, consentimientos, `asignado_por`, `estado_asignacion`,
`fecha_asignacion`) y no se consultan otras tablas.

## Allowlist (14 columnas)

| # | Campo origen (view model) | Encabezado humano | Tipo de celda | Formato | Grupo |
| --- | --- | --- | --- | --- | --- |
| 1 | `id_lead` | `ID Lead` | texto (UUID) | texto | Identificación del lead |
| 2 | `rut` | `RUT` | texto | texto | Identificación del lead |
| 3 | `nombre_completo` | `Nombre` | texto | texto | Identificación del lead |
| 4 | `email` | `Email` | texto | texto | Contacto |
| 5 | `telefono` | `Teléfono` | texto | texto | Contacto |
| 6 | `genero` | `Género` | texto | texto | Información previsional/comercial |
| 7 | `estado_civil` | `Estado Civil` | texto | texto | Información previsional/comercial |
| 8 | `afp` | `AFP` | texto | texto | Información previsional/comercial |
| 9 | `saldo_afp` | `Saldo AFP (CLP)` | número | `#,##0` (CLP, sin decimales) | Información previsional/comercial |
| 10 | `comentarios` | `Comentarios` | texto | texto | Información comercial |
| 11 | `estado_lead` | `Estado` | texto | texto | Fecha y estado |
| 12 | `created_at` | `Fecha Ingreso` | fecha | `dd/mm/yyyy` | Fecha y estado |
| 13 | `id_asesor` | `ID Asesor` | texto (UUID) | texto | Asignación actual / asesor |
| 14 | `asesor_nombre` | `Asesor` | texto | texto | Asignación actual / asesor |

## Campos excluidos (prohibidos, nunca serializados)

| Campo | Motivo |
| --- | --- |
| `raw_payload` | JSONB de ingestion; nunca se presenta en el CRM. |
| `id_persona` | FK interna no presentada por el CRM. |
| `genero_id`, `estado_civil_id`, `afp_id` | UUIDs internos de catálogo; el CRM muestra los nombres (`genero`, `estado_civil`, `afp`). |
| `fecha_nacimiento` | PII del detalle, no del listado; fuera del view model reutilizado. |
| `asignado_por`, `estado_asignacion`, `fecha_asignacion`, `id_asignacion` | Internos de trazabilidad de asignación, no del listado. |
| `id_consentimiento`, `acepta_terminos`, `acepta_politica_privacidad`, `finalidad_contacto`, `version_*`, `ip_origen`, `user_agent` | Consentimientos y metadata de sesión; no del listado. |
| Contraseñas / `password_hash`, secretos, tokens, cookies, datos de sesión | Prohibido por invariante del proyecto. |
| Columnas de `tpi.auditoria` (salvo las ya previstas en el evento F9) | Metadata técnica de auditoría; no se exporta contenido de auditoría. |
| Cualquier columna descubierta dinámicamente | Prohibido por diseño (allowlist explícita). |

## Reglas de serialización

- La proyección es **explícita**: una lista fija `(campo, encabezado, tipo, formato)`
  iterada en orden; jamás se itera sobre las claves de la fila de BD.
- **Números**: `saldo_afp` se escribe como celda numérica nativa con formato
  `#,##0`. Nunca se neutraliza un número.
- **Fechas**: `created_at` se escribe como celda de fecha nativa (`datetime`) con
  formato `dd/mm/yyyy`. Nunca se neutraliza una fecha.
- **Texto** (`id_lead`, `rut`, `nombre_completo`, `email`, `telefono`, `genero`,
  `estado_civil`, `afp`, `comentarios`, `estado_lead`, `id_asesor`, `asesor_nombre`):
  se escribe como texto. UUID, RUT, teléfonos y códigos conservan los ceros
  iniciales porque se escriben como texto, nunca como número.
- **Formula injection (F6)**: todo valor de texto cuyo primer carácter sea `=`, `+`,
  `-` o `@` se neutraliza prefijando una comilla simple (`'`) y la celda se fuerza a
  texto. La protección no toca fechas ni montos (se escriben como tipos nativos).
- **Nulos**: un valor `NULL` se escribe como celda vacía (o texto vacío), nunca como
  `"None"`.

## Límite de exportación (F8)

- Constante en código: `EXPORT_MAX_ROWS = 10000` (en `app/services/xlsx_export.py`).
- Justificación: openpyxl genera en memoria; con 14 columnas y DEV sintético, 10 000
  filas mantiene un pico de memoria acotado y muy por encima del volumen real del
  ambiente; el conteo es `COUNT(*)` con el mismo `WHERE` y aborta antes de construir
  el archivo si se excede (sin truncamiento silencioso).
