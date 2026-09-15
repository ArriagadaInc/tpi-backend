# Deployer — CONTEXT (vista curada)

## Mecanismo real vigente (DEV)

- Cuenta `821656895812`, region `us-east-2`, perfil `tpi-dev` (usuario IAM humano; transitorio).
- Elastic Beanstalk: application `tpi-backoffice`, environment `tpi-backoffice-dev-green`
  (Docker AL2023, compose: caddy + api + backoffice). Detalle no secreto: `environments/dev.yaml`.
- Build unico: `.github/workflows/publish-dev-ecr-images.yml` (`gh workflow run ... -f source_sha=<release_sha>`)
  corre gates, publica `tpi-dev-app`/`tpi-dev-caddy` por SHA (IMMUTABLE), resuelve digests, exige
  scan HIGH/CRITICAL = 0 y sube artifact con manifest.
- Bundle: `build_domain_locked_bundle()` con `deployment/aws/docker-compose.domainlocked.yml`
  (ZIP determinista, solo `docker-compose.yml`, imagenes por digest, dominios literales).
- Staging: S3 `elasticbeanstalk-us-east-2-821656895812`, key
  `tpi-backoffice/dev-releases/<label>/<bundle_sha256>.zip` con `--if-none-match '*'`; AV con
  `--no-process` (UNPROCESSED es valido).
- Cutover: `update-environment --environment-name tpi-backoffice-dev-green --version-label <aprobada>`.
- CodePipeline `tpi-backoffice-dev-promotion`: Promote deshabilitado; el Harness no lo usa.

## Golden path y STOP (contrato v2 secciones 3, 4, 14)

Candidate congelado -> bundle SHA256 -> key nueva -> AV nueva -> preflight minimo (cuenta, region,
environment sano, source esperado, AV existe, sin update en curso) -> cutover version-only -> esperar
VersionLabel exacta + Ready/Green/Ok -> smoke inmediato -> evidencia.
STOP inmediato: otra cuenta; environment fuera del source esperado; bundle/digest distinto; update en
curso; necesidad de `--option-settings`; permiso de escritura nuevo; smoke con defecto de
autorizacion/PII/persistencia.

## Lecciones que cambian decisiones

- Ready/Green/Ok es salud, no identidad: verificar la cadena VersionLabel -> AV SourceBundle ->
  S3 ChecksumSHA256 -> digests (contrato principio 2; LL-13).
- Lecturas pueden tener efectos caller-side: prohibido `describe-configuration-settings` (LL-02).
- Un write fallido puede dejar residuos: inventario read-only antes de decidir (LL-04).
- UpdateEnvironment rechazado -> NO rollback; rollback solo ante degradacion de infraestructura (LL-06).
- Defecto funcional -> no endurecer deploy ni rollback automatico; puede quedar en DEV (contrato seccion 9).
- Mismo error de infraestructura dos veces -> STOP (POLICY seccion 4).
- Validar TLS con cliente independiente (curl de Windows puede fallar por schannel, LL-15).
- Orden de diagnostico: estado EB -> EB events -> CloudTrail -> logs -> resumenes (extracto v1).
- ECR lifecycle keep-20 puede borrar imagenes del LKG: verificar todos sus digests antes del gate.

## Rollback condicionado (aprobado en el mismo Human Gate)

Un unico rollback version-only al LKG nombrado, solo si: update aceptado; environment degradado,
inconsistente o sin estado esperado; LKG utilizable; imagenes del LKG en ECR; sin option settings;
no es defecto puramente funcional; sin rollback previo. Rollback fallido -> BLOCKED_HUMAN.

## No es estado actual

Version labels/SHAs de runbooks, STATUS, PROJECT_STATUS y seccion 15 del contrato. No usar sin
decision humana: `h3-3-crm-web-28cf009-r1`, `h3-3-domain-baseline-*`, `h2-5d-ecr-47fa0c9`.
No tocar `tpi-backoffice-dev` ni `tpi-backoffice-dev-ecr`. No ejecutar `promote_*.py` ni workflows historicos.
