---
name: tpi-docs-bitacora
role: developer
load_when: "Siempre en DEVELOPING"
sources: [engineering_standards, handoff_h33]
---

# tpi-docs-bitacora

## 1. Cuando se carga
Toda tarea: la documentacion operativa es parte de la DoD.

## 2. Puede
- Actualizar documentacion tecnica afectada por el cambio dentro del PR de la tarea.
- Registrar en `progress/current.md` el estado breve y lineas `DECISION:` / `BLOCKER:`.

## 3. No puede
- Editar `docs/cicd/`, `AGENTS.md`, `CLAUDE.md` ni archivos del Harness.
- Copiar documentos completos o registrar secretos/PII.
- Presentar estado historico como actual.
- Escribir la entrada de cierre en `docs/BITACORA.md` (la genera el cierre automatico del Harness).

## 4. Precondiciones
- Saber que documentos describen el comportamiento cambiado.

## 5. Comandos y herramientas
- `python scripts/harness/context_compact.py --label <task>-developer` al terminar la etapa.

## 6. Evidencia obligatoria
- Documentos modificados listados en `files_changed`.

## 7. STOP
- Contradiccion documental relevante sin resolver: registrar `BLOCKER:` y detener.

## 8. Fuentes
- `docs/ENGINEERING_STANDARDS.md` (DoD documental).
- `docs/BITACORA.md` (reglas de actualizacion).
