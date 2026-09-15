---
name: python-design-patterns
role: developer
load_when: "DEVELOPING cuando la tarea implica diseñar un componente nuevo, refactorizar código enredado, decidir si agregar una abstracción, o elegir entre composición y herencia. Para cambios triviales o acotados no se carga: prevalece KISS y el cambio mínimo correcto."
sources: [python_design_patterns_skill, technical_decisions, engineering_standards]
upstream_source: https://www.skills.sh/wshobson/agents/python-design-patterns
upstream_repo: https://github.com/wshobson/agents
upstream_path: plugins/python-development/skills/python-design-patterns/SKILL.md
upstream_commit: 2cc51848c63d37a0fbe9843c43ce39601c6aeba3
imported_at: "2026-09-15"
---

# python-design-patterns

## 1. Cuando se carga
Tareas en DEVELOPING que implican diseñar un componente nuevo, refactorizar una God-class o
funcion enredada, decidir si agregar una abstraccion, o elegir entre composicion y herencia,
dentro de la arquitectura vigente (`agents/developer/CONTEXT.md`: route/API -> service/domain
-> repository -> PostgreSQL). No se carga para fixes puntuales ni cambios acotados.

## 2. Puede
- Recomendar Single Responsibility, separacion de capas, composicion sobre herencia y dependency
  injection por constructor cuando resuelven un problema real y demostrable de la tarea activa.
- Aplicar la Regla de Tres: no abstraer hasta la tercera repeticion real, salvo duplicacion que
  ya causa bugs por copias divergentes (ahi conviene extraer antes).
- Senalar una violacion de capas (p. ej. `service` importando desde `route/API`, o una ruta
  accediendo a PostgreSQL sin pasar por el `service`).

## 3. No puede (guardrail anti-sobreingenieria)
- Introducir factories, strategies, interfaces/Protocols, adapters o capas nuevas **solo porque
  el patron existe**, cuando una solucion simple ya satisface la historia y los criterios de
  aceptacion de la tarea.
- Rediseñar la arquitectura vigente route/API -> service/domain -> repository -> PostgreSQL sin
  necesidad demostrada por `tasks/current.yaml`.
- Introducir una segunda estrategia de acceso a datos, un ORM u otro framework de patrones.
- Justificar cambios fuera del alcance o los criterios de aceptacion de la tarea activa.

## 4. Precondiciones
- Historia y criterios de aceptacion de `tasks/current.yaml` leidos.
- Arquitectura vigente (`agents/developer/CONTEXT.md`) y, si aplica, `docs/DECISIONES_TECNICAS.md`.

## 5. Comandos y herramientas
- No define comandos propios; usa los gates de `tpi-testing` (ruff, black, mypy, pytest) para
  verificar que una refactorizacion no cambio comportamiento observable.
- Checklist antes de abstraer: (1) ¿una funcion simple o un `dict` de despacho ya cumple la
  historia? usar eso y detenerse. (2) ¿existen ya >= 3 instancias reales del mismo problema? si
  no, no abstraer. (3) ¿la abstraccion resuelve un problema demostrable (testabilidad,
  acoplamiento real, violacion de capas)? si no hay problema concreto, no introducirla. (4) ¿se
  puede inyectar la dependencia por constructor para testear con fakes, sin nuevas capas?

## 6. Evidencia obligatoria
- Si la tarea introduce una abstraccion nueva (clase, interfaz, capa): registrar en
  `assumptions` del payload (`developer-*.json`) que problema concreto resuelve.
- Si se evaluo y se decidio NO abstraer (KISS/Regla de Tres): no requiere evidencia adicional;
  es el camino esperado.

## 7. STOP
- El criterio de aceptacion exige un rediseño de arquitectura (nueva capa/servicio, cambio de la
  cadena route/API -> service/domain -> repository): registrar `BLOCKER:` en
  `progress/current.md` y detenerse; ese alcance corresponde a otra tarea.
- Duda razonable entre aplicar un patron y el cambio minimo correcto: prevalece el cambio minimo.

## 8. Fuentes
- Upstream: fuente `python_design_patterns_skill` (URL, repo y commit verificados en el
  frontmatter de este archivo).
- `agents/developer/CONTEXT.md` (arquitectura vigente).
- `docs/DECISIONES_TECNICAS.md`, `docs/ENGINEERING_STANDARDS.md`.
