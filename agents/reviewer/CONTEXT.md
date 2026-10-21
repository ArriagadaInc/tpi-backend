# Reviewer — CONTEXT (vista curada)

## Que se revisa en TPI

- Arquitectura por capas: presentacion (`app/web`, `app/api`) -> `SolicitudService` ->
  `SolicitudRepository` -> PostgreSQL. Ninguna ruta accede a BD/SNS directo.
- Seguridad server-side: RBAC, CSRF, masking de PII por rol, guards fail-closed, sin secretos.
- PII: CEO/CTO completa; roles restringidos enmascarada y **sin PII completa en el HTML servido**.
- Datos: `tpi.asignaciones` fuente operacional; `tpi.auditoria` append-only; una asignacion activa.
- Migraciones: versionadas con preflight/rollback; nunca reejecutar 005/006; ejecucion AWS fuera del Harness.
- Calidad: gates de `harness/project-profile.yaml`; cobertura >= 85%; tests de comportamiento.

## Reglas de release que el Reviewer hace cumplir (resumen con punteros)

1. Clasificacion A-E; el Harness solo despliega A/B; no mezclar clases
   (`docs/cicd/TPI_Contrato_CICD_AWS_v2.md` seccion 2).
2. Identidad del release: reviewed tree -> release SHA (merge squash) -> digests ECR -> bundle
   SHA256 -> S3 key -> Application Version -> VersionLabel (contrato seccion 12; project-profile).
3. `approved_commit == deployed_commit == release_sha`; arbol del merge == arbol revisado.
4. Imagenes por digest `sha256:`; ECR IMMUTABLE; scan HIGH = 0 y CRITICAL = 0 (contrato seccion 5).
5. Bundle domain-locked determinista, reproducible por el Reviewer (`deployment/build_eb_ecr_bundle.py`).
6. Fast path prohibe `--option-settings`, IAM, Route53, rebuild, rerun de migraciones, borrar AV
   (contrato seccion 4).
7. LKG = version sana observada; sus digests deben existir en ECR (ECR lifecycle keep-100 desde 2026-10-19, antes keep-20: riesgo menor, no eliminado).
8. Mensajes de error no son contratos; decidir por status, IDs, hashes (`docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` principio 5).
9. Read-only no es safe-to-log (`docs/AWS_DEPLOYMENT_POLICY.md` principio 11, provisional).
10. Separacion de poderes: quien construye no aprueba; el Reviewer no despliega (BEST_PRACTICES principio 8).

## AWS para el Reviewer

- MCP `aws` read-only: documentacion y skills oficiales (conocimiento).
- Lecturas de recursos: solo en CANDIDATE_REVIEW via `python scripts/harness/aws_guard.py`
  (modo `candidate_read`: STS, EB describe, S3 head-object de releases, ECR describe).
- Escrituras AWS: nunca.

## Limites del guard (formas que ya bloquearon sesiones)

El guard revisa el **texto** de cada comando y un DENIED detiene el turno; no busques rodeos, detente y reporta.
Estas formas ya costaron sesiones:

- Anotar tu decision en `progress/current.md` con un `python - <<'EOF'` que calcula la ruta (por ejemplo con
  `os.path.abspath`) se deniega («python escribe un destino no resoluble en codigo que menciona rutas protegidas»).
  Usa Edit o Write sobre `progress/current.md`; para `evidence.py` y `transition.py`, comandos simples.
- Escribe el payload de tu evidencia con Write, en la ruta absoluta de la raiz de control (el directorio que contiene
  `.harness-worktrees/`), `.../.harness-runtime/payloads/`, y no con heredocs de Bash.
- Si la evidencia de tu rol ya existe porque una sesion anterior se detuvo antes de aplicar la transicion, no repitas
  toda la revision: contrastala con la evidencia del candidato y con Git, y aplica la transicion con tu propia sesion.
- En PowerShell no uses `Remove-Item` ni borres rutas: Claude Code lo bloquea por su cuenta («Remove-Item on system
  path ... is blocked»); no es del guard del Harness.
- Un checkout local de `main` atrasado respecto de `origin/main` da diferencias falsas contra el release: compara contra
  un worktree del `release_sha`, no contra el arbol de trabajo, y declaralo como hallazgo informativo.

## No es estado actual (no usar como verdad)

- Version labels/SHAs/digests de runbooks, `AWS_DEPLOYMENT_STATUS.md`, `PROJECT_STATUS.md` y la
  seccion 15 del contrato.
- CodePipeline como camino obligatorio; Blue/Green con swap de CNAME.
- `promote_*.py`, `deploy-dev-eb.yml`, `preflight-dev-eb.yml` (historicos; no ejecutar).

## Fuentes

`harness/knowledge-sources.yaml` define autoridad y consumidores. Canonicas: contrato v2 completo,
`docs/database/`, `docs/ENGINEERING_STANDARDS.md`. Lecciones: BEST_PRACTICES y
`docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md`.
