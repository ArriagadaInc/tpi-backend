"""Task intake assistant (Orchestrator v2): a deterministic interview, no LLM.

It turns the human's business answers (what the task must achieve, how anyone will know it is done,
what must not happen, how risky it is) into a schema-valid task DRAFT. The Orchestrator writes only
that draft, under .harness-runtime/orchestrator/drafts/ (ephemeral, gitignored, never a source of
truth). It does NOT write tasks/: the human moves the draft into the backlog with
`approve.py define --draft <path> --sha256 <hash>` (real terminal, typed confirmation, and the hash
of exactly the draft that was reviewed) and then activates it with `approve.py activate`.

Everything here is plain functions over `answers` dicts, so the interview is testable without a
terminal; the Orchestrator's TerminalUi only renders `interview()` and returns the answers.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

NEW_TASK = "+ nueva tarea (te hago preguntas)"
DRAFT_DIR = Path(".harness-runtime") / "orchestrator" / "drafts"
_ID_SERIAL = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$")
VERIFICATION = {
    "automated": "una prueba automatica lo comprueba",
    "human": "lo revisas tu a mano",
    "both": "prueba automatica y revision tuya",
}
PRIORITIES = {"P0": "urgente", "P1": "alta", "P2": "normal", "P3": "baja"}
RISKS = {"low": "bajo", "medium": "medio", "high": "alto"}
_DEFAULT_CLASSES = {
    "A": "aplicacion (codigo y pruebas)",
    "B": "configuracion no secreta",
    "C": "infraestructura o CI",
    "D": "base de datos",
    "E": "secretos",
}


@dataclasses.dataclass
class Draft:
    errors: list[str]
    task_id: str | None = None
    path: str | None = None  # repo-relative, forward slashes
    sha256: str | None = None
    summary: list[str] = dataclasses.field(default_factory=list)
    commands: list[str] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Context read from the repository (read-only)
# ---------------------------------------------------------------------------
def existing_ids(root: Path) -> set[str]:
    """Every task id already used: backlog, completed tasks and the active task."""
    ids = {str(item.get("id")) for item in (common.load_backlog(root).get("items") or [])}
    ids |= {path.stem for path in (root / "tasks" / "completed").glob("*.yaml")}
    current = common.load_current_task(root)
    if current:
        ids.add(str(current["id"]))
    return ids


def next_task_id(root: Path) -> str:
    """PREFIX-NNN continuing the highest serial found (TASK-001 when there is none)."""
    best: tuple[int, str, int] | None = None
    for ident in existing_ids(root):
        match = _ID_SERIAL.match(ident)
        if match:
            candidate = (int(match.group(2)), match.group(1), len(match.group(2)))
            best = candidate if best is None or candidate[0] > best[0] else best
    number, prefix, width = best if best else (0, "TASK", 3)
    return f"{prefix}-{number + 1:0{max(width, 3)}d}"


def deploy_possible(root: Path) -> bool:
    """True when the project has a deployment target; False (also on any doubt) otherwise."""
    try:
        state = common.load_state(root)
        env = common.load_environment(root, state.get("environment", "dev"))
        return str((env.get("deployment_target") or {}).get("type", "none")) != "none"
    except Exception:  # noqa: BLE001 - a doubt means "do not offer deployment"
        return False


def change_classes(root: Path) -> dict[str, str]:
    try:
        classes = common.load_profile(root)["release"]["change_classes"]
        return {str(key): str(spec["name"]) for key, spec in classes.items()}
    except Exception:  # noqa: BLE001 - fall back to the generic A-E names
        return dict(_DEFAULT_CLASSES)


# ---------------------------------------------------------------------------
# The interview
# ---------------------------------------------------------------------------
def interview(root: Path) -> dict[str, Any]:
    possible = deploy_possible(root)
    classes = change_classes(root)
    criterion_fields: list[dict[str, Any]] = [
        {
            "id": "description",
            "kind": "text",
            "text": "Que debe cumplirse (algo comprobable, p. ej. 'promedio([2,4,6]) devuelve 4.0')",
            "min_len": 8,
        }
    ]
    if possible:
        criterion_fields.append(
            {
                "id": "verification",
                "kind": "choice",
                "text": "Como se verifica",
                "options": list(VERIFICATION),
                "labels": VERIFICATION,
                "default": "automated",
            }
        )
    questions: list[dict[str, Any]] = [
        {"id": "title", "kind": "text", "text": "Titulo corto de la tarea", "min_len": 3},
        {
            "id": "objective",
            "kind": "text",
            "text": "Objetivo: que debe lograr, en una o dos frases",
            "min_len": 10,
        },
        {
            "id": "criteria",
            "kind": "repeat",
            "min": 1,
            "item_label": "criterio",
            "more_text": "Agregar otro criterio de aceptacion?",
            "fields": criterion_fields,
        },
        {
            "id": "constraints",
            "kind": "repeat",
            "min": 0,
            "item_label": "restriccion",
            "first_text": "Hay algo que NO se debe hacer o que se debe respetar? (p. ej. sin dependencias nuevas)",
            "more_text": "Agregar otra restriccion?",
            "fields": [{"id": "text", "kind": "text", "text": "Restriccion", "min_len": 5}],
        },
        {
            "id": "change_class",
            "kind": "choice",
            "text": "Clase de cambio",
            "options": list(classes),
            "labels": classes,
            "default": "A" if "A" in classes else next(iter(classes)),
        },
    ]
    if possible:
        questions.append(
            {
                "id": "deploy_required",
                "kind": "yes_no",
                "text": "Hay que desplegarla a un entorno al terminar?",
                "default": True,
            }
        )
    questions += [
        {
            "id": "risk",
            "kind": "choice",
            "text": "Riesgo",
            "options": list(RISKS),
            "labels": RISKS,
            "default": "low",
        },
        {"id": "risk_notes", "kind": "text", "text": "Por que ese riesgo", "optional": True},
        {
            "id": "priority",
            "kind": "choice",
            "text": "Prioridad",
            "options": list(PRIORITIES),
            "labels": PRIORITIES,
            "default": "P2",
        },
        {
            "id": "task_id",
            "kind": "text",
            "text": "ID de la tarea",
            "default": next_task_id(root),
            "min_len": 2,
        },
    ]
    intro = [
        "Te hago preguntas de negocio y dejo un BORRADOR de tarea: yo no la guardo en el backlog.",
        "Despues la guardas tu con approve.py (te pide confirmar) y la activas.",
        "Un buen criterio se puede comprobar: 'lista vacia lanza ValueError' si; 'funcione bien' no.",
    ]
    if not possible:
        intro.append(
            "Este proyecto no despliega: los criterios se verifican con pruebas automaticas y la "
            "revision del Reviewer."
        )
    return {
        "kind": "intake",
        "title": "NUEVA TAREA: ASISTENTE DE CRITERIOS",
        "lines": intro,
        "questions": questions,
        "context": {"deploy_possible": possible},
    }


# ---------------------------------------------------------------------------
# Draft (the only thing the Orchestrator writes)
# ---------------------------------------------------------------------------
def _clean(value: Any, limit: int) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(value or "")).split())[:limit]


def draft_path(root: Path, task_id: str) -> Path:
    """The draft file of a task id; refuses anything that would leave the drafts folder."""
    if not common.TASK_ID_RE.fullmatch(task_id) or len(task_id) > 40:
        raise common.HarnessError(f"id de tarea invalido: {task_id!r}")
    folder = (root / DRAFT_DIR).resolve()
    path = (folder / f"{task_id}.yaml").resolve()
    if path.parent != folder:
        raise common.HarnessError("el borrador debe quedar dentro de la carpeta de borradores")
    return path


def _build(
    root: Path, answers: dict[str, Any], errors: list[str]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    possible = deploy_possible(root)
    classes = change_classes(root)
    title = _clean(answers.get("title"), 120)
    objective = _clean(answers.get("objective"), 600)
    task_id = _clean(answers.get("task_id"), 40)
    if len(title) < 3:
        errors.append("el titulo necesita al menos 3 caracteres")
    if len(objective) < 10:
        errors.append("el objetivo necesita al menos 10 caracteres")
    if not common.TASK_ID_RE.fullmatch(task_id):
        errors.append("el ID solo admite letras, digitos, punto, guion y guion bajo")
    elif task_id in existing_ids(root):
        errors.append(f"el ID {task_id} ya existe (backlog, tareas cerradas o tarea activa)")
    criteria, seen = [], set()
    for index, raw in enumerate(answers.get("criteria") or [], 1):
        description = _clean(raw.get("description"), 300)
        verification = raw.get("verification") if possible else "automated"
        if len(description) < 8:
            errors.append(f"el criterio {index} es demasiado corto")
        if verification not in VERIFICATION:
            errors.append(f"el criterio {index} tiene una verificacion invalida")
        if description.lower() in seen:
            errors.append(f"el criterio {index} esta repetido")
        seen.add(description.lower())
        criteria.append(
            {"id": f"AC-{index}", "description": description, "verification": verification}
        )
    if not criteria:
        errors.append("hace falta al menos un criterio de aceptacion")
    constraints = [
        text
        for text in (_clean(c.get("text"), 300) for c in answers.get("constraints") or [])
        if text
    ]
    change_class = answers.get("change_class")
    if change_class not in classes:
        errors.append(f"clase de cambio invalida: {change_class!r}")
    risk, priority = answers.get("risk"), answers.get("priority")
    if risk not in RISKS:
        errors.append(f"riesgo invalido: {risk!r}")
    if priority not in PRIORITIES:
        errors.append(f"prioridad invalida: {priority!r}")
    if errors:
        return None
    deploy = bool(answers.get("deploy_required")) if possible else False
    human = any(c["verification"] in ("human", "both") for c in criteria)
    notes = _clean(answers.get("risk_notes"), 300)
    today = common.today()
    actor = common.git(root, "config", "user.name", check=False) or "desconocido"
    task: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "objective": objective,
        "source": {"type": "story", "ref": f"Definida con el asistente de tareas el {today}"},
        "change_class": change_class,
        "deploy_required": deploy,
        "requires_human_acceptance": deploy and human,
        "acceptance_criteria": criteria,
        "constraints": constraints,
        "dependencies": [],
        "risk": {"level": risk, **({"notes": notes} if notes else {})},
        "status": "active",
    }
    item: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "priority": priority,
        "category": "functional",
        "status": "pending",
        "change_class": change_class,
        "summary": objective[:200],
        "evidence": [f"definida con el asistente de tareas el {today} (actor git: {actor})"],
        "task": task,
    }
    return item, task


def summarize(item: dict[str, Any]) -> list[str]:
    task = item["task"]
    lines = [
        f"Tarea {task['id']}: {task['title']}",
        f"Objetivo: {task['objective']}",
        "Criterios de aceptacion:",
        *(
            f"  {c['id']} [{c['verification']}] {c['description']}"
            for c in task["acceptance_criteria"]
        ),
    ]
    if task["constraints"]:
        lines.append("Restricciones:")
        lines += [f"  - {text}" for text in task["constraints"]]
    lines.append(
        f"Clase {task['change_class']} | riesgo {task['risk']['level']} | prioridad "
        f"{item['priority']} | despliegue: {'si' if task['deploy_required'] else 'no'}"
    )
    return lines


def build_draft(root: Path, answers: dict[str, Any]) -> Draft:
    """Validate the answers and, only if everything is valid, write the draft file."""
    errors: list[str] = []
    built = _build(root, answers, errors)
    if built is not None:
        item, task = built
        schema_errors = common.validate_schema(
            root, "task", {"schema_version": 1, "task": task}
        ) + common.validate_schema(root, "backlog", {"schema_version": 1, "items": [item]})
        errors.extend(f"esquema: {message}" for message in schema_errors)
    if built is None or errors:
        return Draft(errors=errors)
    task_id = str(item["id"])
    path = draft_path(root, task_id)
    document = {
        "schema_version": 1,
        "kind": "task_draft",
        "created_at": common.now_iso(),
        "created_by": "orchestrator_intake",
        "item": item,
    }
    common.write_yaml_atomic(
        path,
        document,
        header="# Borrador de tarea. No es fuente de verdad; ver approve.py define\n",
    )
    relative = path.relative_to(root.resolve()).as_posix()
    digest = common.sha256_file(path)
    return Draft(
        errors=[],
        task_id=task_id,
        path=relative,
        sha256=digest,
        summary=summarize(item),
        commands=[
            f"python scripts/harness/approve.py define --draft {relative} --sha256 {digest}",
            f"python scripts/harness/approve.py activate --task {task_id}",
        ],
    )


def done_payload(draft: Draft) -> dict[str, Any]:
    return {
        "kind": "intake_done",
        "title": "BORRADOR DE TAREA LISTO",
        "lines": [
            *draft.summary,
            "",
            "Revisalo. Para que cuente, ejecuta en TU terminal (cada comando te pide confirmar):",
            "  1) define: lo guarda en el backlog (comprueba que el borrador no cambio)",
            "  2) activate: lo activa; el orquestador lo toma al reanudar",
        ],
        "questions": [],
        "context": {"commands": draft.commands},
    }


def error_payload(draft: Draft) -> dict[str, Any]:
    return {
        "kind": "intake_error",
        "title": "NO SE PUDO ARMAR EL BORRADOR",
        "lines": [
            *(f"- {message}" for message in draft.errors),
            "No se escribio nada. Vuelve a elegir 'nueva tarea' para repetir la entrevista.",
        ],
        "questions": [],
        "context": {},
    }
