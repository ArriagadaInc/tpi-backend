# Sesion archivada: CRM-LITE-OFFICIAL-LOGO-prepare

- Archivada: 2026-10-12T00:27:10Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: CRM-LITE-OFFICIAL-LOGO
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: merged_deploy (MERGING -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-11T23:58:54Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-11-CRM-LITE-OFFICIAL-LOGO-merge.md

## Estado reciente
- AC-2 sigue pendiente de verificacion humana en ambos temas.
- Evidencia: evidence/CRM-LITE-OFFICIAL-LOGO/reviewer/review-02.json.
- Deployer (sesion claude-202610112339-deployer): PR #64 mergeado (squash, --match-head-commit 75bcac51ad8f) como 6a5acd4d23d6 en main; release_tree 26a9d9f8725e == reviewed_tree, parent unico 7caeb822b69a; CI main run 38185530789 verde 5/5.
- DECISION [HUMANA] 2026-10-11: el auto mode classifier denego el primer `gh pr merge` (Merge Without Review, merge no ejecutado); el humano agrego una regla de permiso acotada a ese comando exacto en su config de usuario y pidio reintentar. El reintento hizo el merge una sola vez. No generaliza a otras operaciones.
- Evidencia: evidence/CRM-LITE-OFFICIAL-LOGO/deployment/merge-01.json.
- DECISION [HUMANA] 2026-10-11: la sesion AWS de tpi-dev expiro al iniciar el preflight; el `aws login` normal dio 400 en el navegador y el humano la renovo con `aws login --profile tpi-dev --remote` (funciona). Si vuelve a expirar: pedir ese comando al humano; no ingresar credenciales en su nombre.

- Deployer: preflight AWS PASS (cuenta 821656895812, env Ready/Green/Ok, LKG h3-3-7-...-6f0f5bb con digests presentes en ECR, Promote deshabilitado). Dispatch unico de publish-dev-ecr-images.yml sobre 6a5acd4d23d6 -> run 38187230651 FALLO en el gate fail-closed: tpi-dev-app y tpi-dev-caddy con HIGH=1 (CVE-2026-85091, zlib 1.3.2-r0, CVSS4 8.3). Causa: imagen base (ambas fijadas por digest), no el cambio del logo. Sin bundle, S3 ni AV; environment sin mutar. Residuos: 2 imagenes ECR inertes con tag 6a5acd4 (IMMUTABLE).
- Evidencia: evidence/CRM-LITE-OFFICIAL-LOGO/deployment/failure-01.json.

## Bloqueos
- BLOCKER: publish ECR de 6a5acd4 bloqueado por CVE-2026-85091 (zlib, HIGH) en ambas imagenes. No se puede reintentar el mismo SHA (bases fijadas por digest + tags IMMUTABLE ya ocupados). Requiere decision humana: tarea nueva para mitigar el CVE en los Dockerfiles (fuera del scope de esta tarea), o alternativa humana fuera del Harness. Ver recommendation en failure-01.json.
