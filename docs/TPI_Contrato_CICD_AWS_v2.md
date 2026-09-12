# Contrato CI/CD AWS — v2 (golden path operativo)

Estado: referencia operativa vigente para releases de aplicacion en AWS DEV.
Sustituye el enfoque de promocion que mezclaba aplicacion e infraestructura.

## Principio central

Separar siempre dos preocupaciones distintas:

1. **Release de aplicacion** (codigo nuevo) — version-only, sin tocar configuracion.
2. **Cambio de infraestructura** (IAM, red, Route53, DB, service roles, control plane) —
   contrato completo por IaC, con su propia ruta y revision, nunca mezclado con un deploy funcional.

El error historico fue intentar que `UpdateEnvironment` hiciera ambas cosas a la vez.

## Golden path (fast path version-only)

1. Candidate inmutable: imagenes ECR fijadas por digest `sha256:`.
2. Bundle determinista y verificable por SHA256 (ZIP con solo `docker-compose.yml`).
3. Application Version nueva con `--source-bundle` apuntando a la key content-addressed.
4. Cutover:
   `aws elasticbeanstalk update-environment --environment-name <env> --version-label <target>`
   **sin `--option-settings`.**
5. Esperar `Ready / Green / Ok`.
6. Smoke funcional inmediato.
7. Rollback, si hace falta:
   `aws elasticbeanstalk update-environment --environment-name <env> --version-label <VersionLabel_conocida>`.

Para releases de aplicacion **no** modificar option settings, IAM, Route53, red ni DB
en el mismo cutover.

## Anti-patrones registrados (no repetir)

- **Ciclo AccessDenied -> agregar permiso -> retry.** No desarrollar IAM de forma
  incremental; derivar el contrato completo de la documentacion AWS y de IaC.
- **Usar `UpdateEnvironment` para cambiar configuracion (option settings) durante
  un release de aplicacion.** Dispara dependencias caller-side de red/EC2 y S3/CloudFormation.
- **Esperas largas dentro de la accion Commands de CodePipeline.** Expusieron
  expiracion de token (`INVALID_SECURITY_TOKEN_ERROR`). Acotar waiters o moverlos fuera del pipeline.

## Trazabilidad (obligatoria)

`commit` -> `digest (ECR)` -> `bundle SHA256` -> `Application Version` -> `VersionLabel en runtime`.

Cada release debe poder reconstruirse y verificarse por SHA256 de forma determinista
(sin varianza de compresion ni de plataforma).

## Rollback

- Rollback de aplicacion = version-only a una `VersionLabel` conocida y sana.
- No borrar ni recrear Application Versions para reutilizar nombres.
- Preservar artefactos de rollback (ver `docs/BITACORA.md` 2026-09-12).

## Seguridad y arquitectura

- Minimo privilegio; separacion de responsabilidades; service roles explicitos.
- PII/RBAC server-side; nada de PII en HTML/source para roles restringidos.
- Ningun secreto en Git, logs, bitacora ni en el bundle.
- Infraestructura como codigo para cualquier cambio de IAM/red/control plane.

## Observabilidad y evidencia

- Registrar estado observado (VersionLabel, health, HTTPS/TLS, smoke), no solo intencion.
- Evidencia por release: SHA de imagen/bundle/AV, resultado de smoke, health.
- Logs de Caddy/ACME sin errores materiales antes de dar un release por bueno.

## DEV -> QA -> PROD

- No copiar excepciones ad hoc de DEV a entornos superiores.
- Antes de PROD cerrar: IaC del control plane, service roles explicitos, smoke
  automatizado con usuario sintetico, identidad DB read-only de inspeccion,
  politica de rollback/retencion y observabilidad por release.

## Estado actual y siguiente paso

- Runtime DEV vigente: `h3-3-crm-web-43101be-domainlocked-r1` (Ready/Green/Ok).
- Deuda funcional: issue #50 (H3.3.1 — RBAC/PII y asignacion manual).
- Industrializacion del camino version-only y separacion de infraestructura: H3.2.
