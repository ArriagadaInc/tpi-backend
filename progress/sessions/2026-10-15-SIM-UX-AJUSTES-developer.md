# Sesion archivada: SIM-UX-AJUSTES-developer

- Archivada: 2026-10-15T20:05:49Z
- Estado: DEVELOPING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: DEVELOPING (rol: developer)
- Tarea: SIM-UX-AJUSTES
- Proximo paso: Developer: implementar, correr gates, abrir/actualizar PR, registrar evidencia y submit_for_review
- Ultima transicion: start_development (NEW -> DEVELOPING)
- Actualizado: 2026-10-15T19:44:06Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-14-SIM-RV-V1-closure.md

## Estado reciente
- SIM-UX-AJUSTES (DESARROLLO): implementados los 5 ajustes de UX. PR #75 (SHA 01b8d50c684c) con CI verde.
  - Simulador: los errores 422 re-renderizan el formulario en la misma pantalla (aviso arriba + valores conservados); ya no responden PlainTextResponse.
  - Detalle: retirado el boton antiguo 'Abrir simulacion'; queda 'Abrir simulador' (executive/ceo/cto).
  - Cabecera: 'Volver al sitio' -> 'Home' y 'Salir' -> 'Cerrar sesion'.
  - 'CRM Lite' -> 'CRM' en texto visible y en las pruebas que lo afirmaban.
  - CHANGELOG y BITACORA actualizados.
- DECISION: conservar get_public_simulator_url/web_simulator_url y los enlaces 'Abrir simulador publico' de Streamlit (fuera del alcance de AC-2, que solo retira el boton del detalle web).
- DECISION: no reescribir docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md (documentacion historica de SIM-RV-V1).
- Nota local: 11 fallos preexistentes en test_executive_dashboard_* por falta de DATABASE_* (Python 3.13.13 sin DB); el CI Python 3.12 es el arbitro.

## Bloqueos
- Ninguno.
