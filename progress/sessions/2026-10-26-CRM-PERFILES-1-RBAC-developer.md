# Sesion archivada: CRM-PERFILES-1-RBAC-developer

- Archivada: 2026-10-26T01:10:29Z
- Estado: DEVELOPING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: DEVELOPING (rol: developer)
- Tarea: CRM-PERFILES-1-RBAC
- Proximo paso: Developer: implementar, correr gates, abrir/actualizar PR, registrar evidencia y submit_for_review
- Ultima transicion: start_development (NEW -> DEVELOPING)
- Actualizado: 2026-10-26T00:40:26Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-25-CRM-ESTADOS-1-CATALOGO-closure.md

## Estado reciente
- DECISION (Developer CRM-PERFILES-1-RBAC, 2026-10-26): implementado y entregado a revision. SHA 5a1d9ead523f40e4b7cc65908a9da92a5a8a0836, rama harness/CRM-PERFILES-1-RBAC-perfiles-rbac, PR #132, CI verde (Tests + Lint & Format + Security Audit + Docker Build + Release Tooling Validation). Rol nuevo coordinator, etiquetas Runner/Coordinador/Socio (profile_label unico), alcance de cartera generalizado a has_portfolio_scope (advisor+coordinator), asignacion solo ceo/cto, simulador para coordinator (cartera propia), estados del runner sin reunion_realizada/ficha_generada/cerrado. 23 tests nuevos en tests/unit/test_crm_perfiles_rbac.py; pruebas de asignacion actualizadas sin debilitarse; actores de asignacion de integracion pasan a ceo. docs/SEGURIDAD.md con matriz de permisos por perfil + configuracion de usuarios (coordinator, ejemplo ficticio). AC-8 queda pending_verification (smoke humano en DEV tras desplegar; el humano agrega los usuarios de prueba al secreto).
- DECISION (ORQUESTADOR INTERACTIVO, 2026-10-25): CRM-ESTADOS-1-CATALOGO cerrada a mano (registrada como CANCELLED por el Harness: resolve --to IDLE). El release bfa4ede esta desplegado en DEV y los criterios AC-1 a AC-7 estan aceptados; la verificacion automatica (verification-02) fallo por 1 coincidencia del indicador fuerte secret que es una falsa alarma (linea de acceso de Caddy de un robot que pidio GET /secrets.json y recibio 404). La regla se corrige en la tarea aparte HARNESS-LOGS-FALSOS-POSITIVOS-CADDY (backlog). Decision del humano (2026-10-25): seguir con CRM-PERFILES-1-RBAC SIN corregirla y aceptar el riesgo de otra falsa alarma (se acepta rapido tras desplegar; si ocurre, cierre manual como esta vez). Detalle en docs/BITACORA.md.
- DECISION (ORQUESTADOR INTERACTIVO, 2026-10-25, para el Developer de CRM-PERFILES-1-RBAC): leccion de las tareas anteriores. (1) RUTA LITERAL del worktree en git commit y git push, sin variables ($VAR), sin `$(...)`, sin `cd ... &&` y sin encadenar nada: una orden por commit. (2) Tienes un tope duro de llamadas de herramienta por turno: agrupa comandos, no releas archivos ya leidos, corre cada gate UNA vez, y HAZ COMMIT PARCIAL (y push de la rama) en cuanto AC-1 a AC-3 pasen, para que un corte por tope no pierda trabajo (el turno de CRM-ESTADOS-1 dejo 36 archivos sin commitear). Orden sugerido: AC-1 roles y etiquetas, AC-2 funcion unica de cartera, AC-3 asignacion solo socios, AC-4 simulador, AC-5 estados por perfil, AC-6 lo que no cambia, AC-7 matriz de pruebas y docs. (3) NO toques ni leas AUTH_USERS_JSON ni usuarios reales: los ejemplos de la documentacion y de las pruebas son ficticios; el humano agrega los usuarios de prueba a DEV despues del despliegue (un rol 'coordinator' en el secreto ANTES de desplegar romperia el arranque de la version actual). (4) El payload de evidencia se escribe con Write en la ruta ABSOLUTA de la raiz de control; nunca modifiques archivos protegidos con python -c, sed ni heredocs. (5) Usa el contrato de estados de main tal cual (app/models/crm_states.py).

## Bloqueos
- Ninguno.
