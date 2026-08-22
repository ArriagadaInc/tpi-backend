# H3.1 CRM Lite para Backoffice

## Estado

**CLOSED**

## Cierre formal

- PR: `#8`
- Final PR HEAD: `58a11fdcd0b1a9b1bca6679ebe463e0964659c7f`
- Merged main: `ad22d37048176aa80ab139f56c3ef6903f6e430e`
- CI final: `#58`
- Lint: PASS
- Tests: PASS
- Security: PASS
- Docker: PASS
- Productive runtime validated from: `d9bc2670bca87a71130d8e7088b56dd7976b82f5`
- App digest: `sha256:e70d799ed6b5da252a7f90bc412b8a75ba37082377f3e3bc46ca7025571ca01b`
- AWS DEV: validated
- Database structural changes: none

## Pendientes trasladados a H3.2

- reproducible deployment chain
- CI post-merge observability
- runtime verification automation
- cleanup log observability

## Objetivo

La bandeja privada de backoffice evoluciona a una vista tipo CRM Lite, pensada para lectura rápida, filtros y apertura de detalle sin cambiar la estructura de PostgreSQL.

## Restricción de esquema

No se modifica la base de datos.

No se crean tablas, columnas, constraints, migraciones ni nuevos estados persistidos.

## Matriz de soporte

| Funcionalidad | Soportada hoy | Requiere cambio BD |
| --- | --- | --- |
| Listar leads | Sí | No |
| Buscar leads por RUT / texto | Sí | No |
| Filtrar por estado y AFP | Sí | No |
| Ordenar y paginar | Sí | No |
| Ver detalle del lead | Sí | No |
| Acceso a simulación desde la UI | Parcial, solo navegación contextual | No |
| Editar estado del lead | No | Sí |
| Asignar responsable | No | Sí |
| Comentarios administrativos estructurados | No | Sí |
| Flujo CRM persistido `Nuevo -> Cerrado` | No exacto, solo presentación | Sí |

## Alcance implementado

- Bandeja principal con densidad alta de información.
- Búsqueda por texto reutilizando campos existentes.
- Filtros de estado y ordenamiento.
- Panel de detalle para un lead seleccionado.
- Conservación del guardrail DEV de eliminación controlada.

## Fuera de alcance por la restricción de esquema

- Estados CRM nuevos persistidos.
- Responsable asignado.
- Comentarios administrativos estructurados.
- Edición de campos que hoy no expone el backend.
- Cualquier motor nuevo de simulación o almacenamiento asociado.

## Nota de arquitectura

La UI no accede a PostgreSQL directamente.
La lectura y paginación viven en `app/services/solicitud_service.py` y `app/repositories/solicitud_repository.py`.

## Despliegue Elastic Beanstalk

`ServiceRole` es administrado por el environment de Elastic Beanstalk.
No debe definirse en `.ebextensions`.
Los despliegues de nuevas versiones deben preservar la configuración existente
del environment y actualizar solamente `VersionLabel`.
