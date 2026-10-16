# Sesion archivada: SIM-UX-AJUSTES-review

- Archivada: 2026-10-15T20:09:04Z
- Estado: REVIEWING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: REVIEWING (rol: reviewer)
- Tarea: SIM-UX-AJUSTES
- Proximo paso: Reviewer: revisar SHA exacto, CI verde, registrar review y review_approve o review_reject
- Ultima transicion: start_review (READY_FOR_REVIEW -> REVIEWING)
- Actualizado: 2026-10-15T20:06:45Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-15-SIM-UX-AJUSTES-developer.md

## Estado reciente
  - 'CRM Lite' -> 'CRM' en texto visible y en las pruebas que lo afirmaban.
  - CHANGELOG y BITACORA actualizados.
- DECISION: conservar get_public_simulator_url/web_simulator_url y los enlaces 'Abrir simulador publico' de Streamlit (fuera del alcance de AC-2, que solo retira el boton del detalle web).
- DECISION: no reescribir docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md (documentacion historica de SIM-RV-V1).
- Nota local: 11 fallos preexistentes en test_executive_dashboard_* por falta de DATABASE_* (Python 3.13.13 sin DB); el CI Python 3.12 es el arbitro.

## Bloqueos
- Ninguno.
