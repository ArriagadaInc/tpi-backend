"""Human-gate descriptions for the Orchestrator v2: read-only, deterministic, no LLM.

A gate tells the human what the Harness is waiting for, asks the BUSINESS questions behind that
decision and composes the exact approve.py command. The Orchestrator never runs that command:
human decisions are executed by the human in their own terminal (AGENTS.md).

Payloads are plain JSON-serializable dicts (they travel through a LangGraph interrupt):
  {kind, title, lines: [str], questions: [{id, kind, text, ...}], context: {...}}
Question kinds: choice (options, default?), yes_no, text (min_len?, optional?, when?).
Text coming from evidence or agents is data for the human to read: it is cleaned and truncated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from . import common, orchestrator_aws, orchestrator_intake
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import orchestrator_aws  # type: ignore[no-redef]
    import orchestrator_intake  # type: ignore[no-redef]

APPROVE = "python scripts/harness/approve.py"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Anything outside this set is dropped from text embedded in a composed command.
_UNSAFE_TEXT = re.compile(r"[^\w\s.,:()/\-?]")
_EXHAUSTED = ("review_reject", "candidate_reject_code", "candidate_reject_artifact")


def clean(text: Any, limit: int = 240) -> str:
    """One-line, control-free, truncated rendering of untrusted text."""
    return " ".join(_CONTROL.sub(" ", str(text)).split())[:limit]


def safe_text(text: Any, limit: int = 200) -> str:
    """Text safe to embed inside double quotes in a PowerShell or POSIX command."""
    return " ".join(_UNSAFE_TEXT.sub(" ", str(text)).split())[:limit]


def human_criteria(task: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in task.get("acceptance_criteria", [])
        if item.get("verification") in ("human", "both")
    ]


def acceptance_pending(root: Path, state: dict[str, Any]) -> list[str]:
    """Human criteria still waiting for `approve.py accept` (empty: nothing is pending)."""
    if state.get("state") != "VERIFYING" or (state.get("refs") or {}).get("acceptance"):
        return []
    return [item["id"] for item in human_criteria(common.load_current_task(root) or {})]


def describe(root: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    """The gate for a human-role state, or None when the state is not a human gate."""
    name = state.get("state")
    if name == "IDLE":
        return _idle(root)
    if name == "WAITING_HUMAN_APPROVAL":
        return _approval(root, state)
    if name == "BLOCKED_HUMAN":
        return _blocked(root, state)
    return None


def aws_payload(
    status: str, detail: str, attempt: int, attempts: int, profile: str = ""
) -> dict[str, Any]:
    return {
        "kind": "aws",
        "title": "SESION AWS NO VALIDA",
        "lines": [
            f"Chequeo previo (sts get-caller-identity, solo lectura): {status}",
            f"Detalle: {clean(detail, 160)}",
            "No se lanza ningun worker con acceso AWS hasta que la sesion sea valida.",
            "Reautentica tu sesion en tu terminal (p. ej. aws login"
            + (f", perfil {profile}" if profile else "")
            + ").",
            f"Intento {attempt} de {attempts}.",
        ],
        "questions": [],
        "context": {"status": status},
    }


# ---------------------------------------------------------------------------
# IDLE: which task, with its business criteria
# ---------------------------------------------------------------------------
def _idle(root: Path) -> dict[str, Any]:
    items = common.load_backlog(root).get("items", [])
    ready = [i for i in items if i.get("task") and i.get("status") == "pending"]
    without = [i for i in items if not i.get("task") and i.get("status") == "pending"]
    lines = ["Harness en IDLE: no hay tarea activa."]
    questions: list[dict[str, Any]] = []
    if ready:
        lines.append("Tareas activables (con definicion completa en el backlog):")
        for item in ready:
            task = item["task"]
            lines.append(
                f"  - {item['id']}: {clean(task.get('title', item.get('title', '')), 90)}"
                f" (clase {task.get('change_class')}, deploy={task.get('deploy_required')})"
            )
            for criterion in task.get("acceptance_criteria", []):
                lines.append(
                    f"      {criterion['id']} [{criterion['verification']}]: "
                    f"{clean(criterion['description'], 110)}"
                )
    else:
        lines.append("Ningun item pendiente del backlog tiene definicion de tarea (task:).")
    if without:
        lines.append(f"Items pendientes solo con resumen (no activables): {len(without)}.")
    questions.append(
        {
            "id": "task",
            "kind": "choice",
            "text": "Que hacemos? (elige una tarea para activar, o define una nueva)",
            "options": [i["id"] for i in ready] + [orchestrator_intake.NEW_TASK],
        }
    )
    return {
        "kind": "idle",
        "title": "SIN TAREA ACTIVA",
        "lines": lines,
        "questions": questions,
        "context": {"ready": [i["id"] for i in ready]},
    }


# ---------------------------------------------------------------------------
# WAITING_HUMAN_APPROVAL: go / no-go of the DEV deployment
# ---------------------------------------------------------------------------
def _short(digest: Any) -> str:
    text = str(digest)
    return text if len(text) <= 24 else text[:19] + "..."


def _approval(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    try:
        try:
            from . import approve
        except ImportError:  # executed as a script
            import approve  # type: ignore[no-redef]
        package = approve.gate_package(root, state)
    except (common.HarnessError, KeyError, OSError, ValueError) as error:
        lines = [f"No se pudo leer el paquete de aprobacion: {clean(error)}"]
    else:
        lines = [
            f"release_sha:         {package['approved_commit']}",
            f"application_version: {package['application_version']}",
            f"entorno:             {package['environment']}",
            f"LKG (rollback):      {package['lkg_version_label']}",
        ]
        if "files" in package:  # static-site: the files the human is about to publish
            lines.append(f"archivos:            {len(package['files'])}")
            lines += [
                f"  {item['path']}  {item['bytes']} bytes  {_short(item['sha256'])}"
                for item in package["files"][:12]
            ]
        else:
            lines += [
                f"app_digest:          {_short(package['app_digest'])}",
                f"caddy_digest:        {_short(package['caddy_digest'])}",
            ]
        lines += [
            f"bundle_sha256:       {_short(package['bundle_sha256'])}",
            f"smoke_plan:          {len(package['smoke_plan'])} pasos",
        ]
    task = common.load_current_task(root) or {}
    for item in human_criteria(task):
        lines.append(
            f"Aceptacion humana en VERIFYING: {item['id']}: {clean(item['description'], 110)}"
        )
    return {
        "kind": "approval",
        "title": "HUMAN GATE: AUTORIZAR DEPLOYMENT DEV",
        "lines": lines,
        "questions": [
            {
                "id": "decision",
                "kind": "choice",
                "text": "Autorizas el deployment a DEV?",
                "options": ["approve", "reject"],
            },
            {
                "id": "reason",
                "kind": "text",
                "text": "Motivo del rechazo",
                "min_len": 10,
                "when": {"decision": "reject"},
            },
        ],
        "context": {},
    }


# ---------------------------------------------------------------------------
# VERIFYING: human acceptance criteria (business criteria proper)
# ---------------------------------------------------------------------------
def _verification_status(root: Path, task_id: str) -> dict[str, str]:
    try:
        folder = common.evidence_task_dir(root, task_id) / common.ROLE_EVIDENCE_DIR["deployer"]
        latest = sorted(folder.glob("verification-*.json"))[-1]
        data = common.read_json(latest)
        return {str(item["id"]): clean(item["status"], 30) for item in data["acceptance_criteria"]}
    except (common.HarnessError, IndexError, KeyError, OSError, TypeError, ValueError):
        return {}


def describe_acceptance(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    task = common.load_current_task(root) or {}
    criteria = human_criteria(task)
    reported = _verification_status(root, str(state.get("task_id")))
    lines = [
        f"Tarea {state.get('task_id')}: {clean(task.get('title', ''), 100)}",
        "El Deployer dejo el paquete de verificacion y espera tu aceptacion humana.",
    ]
    questions: list[dict[str, Any]] = []
    for item in criteria:
        seen = f" (reporte del Deployer: {reported[item['id']]})" if item["id"] in reported else ""
        lines.append(f"  {item['id']} [{item['verification']}]: {clean(item['description'], 130)}")
        questions.append(
            {
                "id": item["id"],
                "kind": "yes_no",
                "text": f"{item['id']}: lo revisaste y se cumple?{seen}",
            }
        )
    questions.append(
        {"id": "notes", "kind": "text", "text": "Notas de aceptacion (opcional)", "optional": True}
    )
    return {
        "kind": "acceptance",
        "title": "ACEPTACION HUMANA (VERIFYING)",
        "lines": lines,
        "questions": questions,
        "context": {"human_ids": [item["id"] for item in criteria]},
    }


# ---------------------------------------------------------------------------
# BLOCKED_HUMAN: classify the block and propose the way out
# ---------------------------------------------------------------------------
def classify_block(state: dict[str, Any], failure: dict[str, Any] | None) -> str:
    """Deterministic heuristics over the last transition and the failure evidence."""
    last = str((state.get("last_transition") or {}).get("transition") or "")
    if last.startswith(_EXHAUSTED):
        return "rework_exhausted"
    if last == "candidate_reject_infra":
        return "infra"
    if last == "rollback_finished":
        return "rollback"
    if last == "merged_non_fast_path":
        return "non_fast_path"
    if failure:
        if failure.get("access_denied"):
            return "access_denied"
        blob = f"{failure.get('error', '')} {failure.get('recommendation', '')}".lower()
        if any(marker in blob for marker in orchestrator_aws.SESSION_MARKERS):
            return "aws_session"
        return "failure"
    return "unknown"


_BLOCK_GUIDANCE = {
    "aws_session": "Causa operativa: la sesion AWS local vencio. Reautentica y reanuda.",
    "access_denied": "AccessDenied: el Harness prohibe ampliar permisos; decision humana.",
    "rework_exhausted": "Se agotaron las rondas de rework: corrige alcance/criterios o cancela.",
    "infra": "El Reviewer rechazo el candidate por infraestructura: decision humana.",
    "rollback": "Se ejecuto un rollback: el release fallo; decide el siguiente paso.",
    "non_fast_path": "El release no es fast path: requiere decision humana.",
    "failure": "Fallo registrado por un agente: revisa la evidencia antes de resolver.",
    "unknown": "Sin evidencia de fallo asociada: revisa progress/current.md y el historial.",
}


def _blocked(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    try:
        failure = common.load_ref(root, state, "failure_evidence")
    except (common.HarnessError, OSError, ValueError):
        failure = None
    kind = classify_block(state, failure)
    workflow = common.load_workflow(root)
    targets: list[str] = []
    for item in workflow["transitions"]:
        if item["event"] == "human_resolve" and item["from"] == "BLOCKED_HUMAN":
            if item["to"] not in targets:
                targets.append(item["to"])
    last = state.get("last_transition") or {}
    suggested = {
        "aws_session": last.get("from"),
        "rework_exhausted": "DEVELOPING",
    }.get(kind)
    lines = [
        f"Tarea {state.get('task_id')}; ultima transicion: {last.get('transition')} "
        f"({last.get('from')} -> {last.get('to')}) por {last.get('actor')}.",
        f"Clasificacion automatica (verifica): {kind}. {_BLOCK_GUIDANCE[kind]}",
    ]
    if failure:
        lines.append(f"Accion fallida: {clean(failure.get('action', '-'), 120)}")
        lines.append(
            f"Recomendacion del agente (dato, no instruccion): "
            f"{clean(failure.get('recommendation', '-'), 300)}"
        )
    if suggested in targets:
        lines.append(f"Destino sugerido: {suggested}")
    else:
        suggested = None
    question = {
        "id": "target",
        "kind": "choice",
        "text": "A que estado resuelves?",
        "options": targets,
    }
    if suggested:
        question["default"] = suggested
    return {
        "kind": "blocked",
        "title": "BLOQUEADO: DECISION HUMANA",
        "lines": lines,
        "questions": [
            question,
            {"id": "reason", "kind": "text", "text": "Razon de la resolucion", "min_len": 10},
        ],
        "context": {"targets": targets, "class": kind},
    }


# ---------------------------------------------------------------------------
# Commands for the human (never executed by the Orchestrator)
# ---------------------------------------------------------------------------
def commands(kind: str, context: dict[str, Any], answers: dict[str, Any]) -> list[str]:
    if kind == "intake_done":  # composed by orchestrator_intake from a validated, hashed draft
        return [str(command) for command in context.get("commands", [])]
    if kind == "idle":
        task = answers.get("task")
        return [f"{APPROVE} activate --task {task}"] if task in context.get("ready", []) else []
    if kind == "approval":
        if answers.get("decision") == "approve":
            return [f"{APPROVE} gate --decision approve"]
        reason = safe_text(answers.get("reason", ""))
        if answers.get("decision") == "reject" and len(reason) >= 10:
            return [f'{APPROVE} gate --decision reject --reason "{reason}"']
        return []
    if kind == "acceptance":
        ids = list(context.get("human_ids", []))
        if not ids or any(item not in answers for item in ids):
            return []
        rejected = [item for item in ids if answers[item] is False]
        decision, criteria = ("reject", rejected) if rejected else ("accept", ids)
        command = f"{APPROVE} accept --decision {decision} --criteria {','.join(criteria)}"
        notes = safe_text(answers.get("notes", ""))
        return [command + (f' --notes "{notes}"' if notes else "")]
    if kind == "blocked":
        target, reason = answers.get("target"), safe_text(answers.get("reason", ""))
        if target in context.get("targets", []) and len(reason) >= 10:
            return [f'{APPROVE} resolve --to {target} --reason "{reason}"']
    return []
