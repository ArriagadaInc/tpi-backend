# Sesion archivada: SIM-UX-AJUSTES-preparing

- Archivada: 2026-10-15T21:07:30Z
- Estado: PREPARING_DEPLOYMENT

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: PREPARING_DEPLOYMENT (rol: deployer)
- Tarea: SIM-UX-AJUSTES
- Proximo paso: Deployer: preflight, publish ECR, bundle, S3, AV, plan; registrar candidate y candidate_ready
- Ultima transicion: merged_deploy (MERGING -> PREPARING_DEPLOYMENT)
- Actualizado: 2026-10-15T20:10:58Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-15-SIM-UX-AJUSTES-review.md

## Estado reciente
  - 'CRM Lite' -> 'CRM' en texto visible y en las pruebas que lo afirmaban.
  - CHANGELOG y BITACORA actualizados.
- DECISION: conservar get_public_simulator_url/web_simulator_url y los enlaces 'Abrir simulador publico' de Streamlit (fuera del alcance de AC-2, que solo retira el boton del detalle web).
- DECISION: no reescribir docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md (documentacion historica de SIM-RV-V1).
- Nota local: 11 fallos preexistentes en test_executive_dashboard_* por falta de DATABASE_* (Python 3.13.13 sin DB); el CI Python 3.12 es el arbitro.

## Bloqueos
- Sin bloqueos. (La sesion AWS vencida del preflight anterior se resolvio: el humano reautentico tpi-dev.)
- Candidate SIM-UX-AJUSTES listo (claude-202610152053-deployer-sup72e445): release 1f50505, publish run 38805792647 (6/6), AV h3-sim-ux-ajustes-1f50505-domainlocked-r1 UNPROCESSED, LKG h3-sim-rv-v1-1308441-domainlocked-r1; evidencia candidate-01.json.
