# Decisiones Tecnicas

## Proposito

Este documento registra decisiones tecnicas de arquitectura, despliegue y operacion que afecten la continuidad del proyecto.
Su objetivo es dejar una referencia estable para futuros cambios, troubleshooting y rollback.

## Decision: usar `tpi-backoffice-dev-green` como environment activo para el cutover DEV

### Contexto

El dominio DEV oficial debia migrarse desde el uso temporal de `dev.genialabs.cl` hacia `dev.tupensioninteligente.cl` sin comprometer el environment previo ni la capacidad de rollback.

### Problema con `tpi-backoffice-dev`

Se intento desplegar la version `h2-5d-ecr-3074bf1-r2` sobre `tpi-backoffice-dev`, pero Elastic Beanstalk devolvio:

```text
Service role is required. It can't be removed.
```

La evidencia recopilada mostro que:

- el environment activo historico tenia una anomalia interna al actualizar solo `VersionLabel`;
- la actualizacion limpia no modificaba ninguna propiedad de IAM de forma explicita;
- el problema no dependia del bundle, sino del estado historico efectivo del environment.

### Decision tomada

Se adopto una estrategia blue/green:

- `tpi-backoffice-dev-green` paso a ser el candidato y luego el environment activo;
- `tpi-backoffice-dev` quedo como rollback temporal;
- la validacion previa al cutover se realizo sobre `dev-green` para evitar bloquear el avance.

### Justificacion

- `tpi-backoffice-dev-green` acepto correctamente los nuevos bundles.
- El environment estaba `Ready / Green / Ok`.
- Permitio validar TLS, Caddy, certificado y smoke antes del corte publico.
- Mantuvo el environment anterior disponible como respaldo inmediato.

## Decision: separar DNS-01 por hosted zone en Caddy

### Contexto

El provider Route53 de Caddy estaba compartiendo un `hosted_zone_id` global hardcodeado entre `dev.genialabs.cl` y `dev.tupensioninteligente.cl`.

### Decision

Se separo la configuracion DNS-01 por dominio:

- `dev.genialabs.cl` usa `Z0562050FYDQE12LRGMA`
- `dev.tupensioninteligente.cl` usa `Z07053592LX0W8GJXNI1C`

### Resultado

Cada dominio quedo atado a su hosted zone correcta y el certificado de `dev.tupensioninteligente.cl` pudo emitirse sin afectar `dev.genialabs.cl`.

## Decision: mantener `dev.genialabs.cl` como respaldo temporal

### Contexto

El nuevo dominio debia estabilizarse en produccion DEV antes de retirar el dominio legacy.

### Decision

`dev.genialabs.cl` se mantiene temporalmente operativo como respaldo.

### Implicacion

No se considera dominio definitivo a futuro.

## Decision: rollback por alias de Route 53

### Contexto

Durante el cutover, el riesgo principal era el DNS publico, no la infraestructura interna ya validada.

### Decision

El rollback inmediato se define como:

- restaurar el alias de Route 53 al target anterior;
- no revertir Caddy, IAM ni la version green para volver al estado anterior;
- conservar `tpi-backoffice-dev` como respaldo temporal.

## Decision: servir assets del CRM Lite con rutas same-origin

### Contexto

Durante la validacion del CRM Lite web en AWS DEV, el front se renderizaba sin estilos porque el HTML referenciaba CSS/JS con URL absolutas dependientes del esquema detectado por el proxy.

### Decision

Para recursos estaticos same-origin se usan rutas directas en la aplicacion web:

- `/static/css/app.css`
- `/static/js/app.js`

### Resultado

- se evita mixed content;
- se elimina la dependencia innecesaria del esquema absoluto;
- el CRM carga estilos y scripts de forma consistente detras de Caddy/Uvicorn.

### Leccion

Cuando el recurso es same-origin, conviene usar rutas estaticas directas si el esquema/proxy puede variar y no aporta valor funcional.

## Decision: mantener `AUTH_USERS_JSON` como secreto vivo del environment

### Contexto

Durante la operacion DEV se detecto una version corrupta del secreto `AUTH_USERS_JSON` en Secrets Manager.

### Decision

- `AUTH_USERS_JSON` se mantiene como configuracion secreta del environment;
- no se versiona en Git;
- la correccion de credenciales se aplica sobre la version viva del secreto;
- los usuarios existentes se preservan al reconstruir el payload.

### Resultado

- el login DEV depende de configuracion viva y validada;
- `diego.operaciones` queda soportado como usuario operacional;
- la autenticacion simple-dev permanece server-side y fail-closed.
