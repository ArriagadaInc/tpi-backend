"""Workflow guards: fail-closed checks over harness evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from . import common, log_scan
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import log_scan  # type: ignore[no-redef]


class GuardError(Exception):
    """Raised by a guard whose condition does not hold."""


@dataclass
class GuardContext:
    root: Path
    state: dict[str, Any]
    task: dict[str, Any] | None
    workflow: dict[str, Any]
    policies: dict[str, Any]
    profile: dict[str, Any]
    environment: dict[str, Any]
    session: str | None = None
    runtime: str | None = None

    def ref(self, key: str) -> dict[str, Any] | None:
        return common.load_ref(self.root, self.state, key)

    def require(self, key: str) -> dict[str, Any]:
        data = self.ref(key)
        if data is None:
            raise GuardError(f"falta la evidencia '{key}'")
        return data


def _check(condition: object, message: str) -> None:
    if not condition:
        raise GuardError(message)


def _max_rework(ctx: GuardContext) -> int:
    return int(ctx.policies["harness"]["max_rework_rounds"])


def _task(ctx: GuardContext) -> dict[str, Any]:
    _check(ctx.task is not None, "no hay tarea activa en tasks/current.yaml")
    assert ctx.task is not None
    return ctx.task


def _checks_pass(items: list[dict[str, Any]]) -> bool:
    return bool(items) and all(item.get("result") == "PASS" for item in items)


def g_task_selected(ctx: GuardContext) -> None:
    task = _task(ctx)
    _check(ctx.state.get("task_id") is None, "ya existe una tarea vinculada al estado")
    _check(task.get("status") == "active", "la tarea seleccionada no esta activa")


def g_task_active(ctx: GuardContext) -> None:
    task = _task(ctx)
    _check(
        task["id"] == ctx.state.get("task_id"), "tasks/current.yaml no coincide con state.task_id"
    )


def g_developer_evidence_valid(ctx: GuardContext) -> None:
    task = _task(ctx)
    dev = ctx.require("developer_evidence")
    _check(dev["tests"]["result"] == "PASS", "tests del Developer no pasan")
    gates = dev["quality_gates"]
    _check(gates and all(value == "PASS" for value in gates.values()), "quality gates no verdes")
    _check(dev["change_class"] == task["change_class"], "clase de cambio distinta a la tarea")
    _check(
        not dev["migrations_included"] or task["change_class"] == "D",
        "las migraciones solo se incluyen en tareas clase D",
    )
    reported = {item["id"]: item["status"] for item in dev["acceptance_criteria"]}
    for criterion in task["acceptance_criteria"]:
        status = reported.get(criterion["id"])
        _check(status is not None, f"criterio {criterion['id']} sin reporte del Developer")
        _check(status != "not_met", f"criterio {criterion['id']} no cumplido")


def g_reviewer_session_independent(ctx: GuardContext) -> None:
    developer = (ctx.state.get("sessions") or {}).get("developer") or {}
    _check(ctx.session, "--session es obligatorio para el Reviewer")
    _check(
        ctx.session != developer.get("session_id"),
        "el Reviewer debe actuar en una sesion distinta a la del Developer",
    )


def g_review_approved(ctx: GuardContext) -> None:
    review = ctx.require("review_evidence")
    dev = ctx.require("developer_evidence")
    _check(review["decision"] == "APPROVED", "la revision no esta APPROVED")
    _check(
        review["reviewed_sha"] == dev["head_sha"], "reviewed_sha distinto del head_sha entregado"
    )
    _check(review["pr_number"] == dev["pr_number"], "PR revisado distinto del PR entregado")
    _check(str(review["ci"]["conclusion"]).lower() == "success", "CI no verde en el SHA exacto")
    _check(
        not any(item["severity"] in ("blocker", "major") for item in review["findings"]),
        "hay hallazgos blocker/major en una aprobacion",
    )
    _check(_checks_pass(review["checks"]), "checks de revision incompletos o fallidos")
    _check(
        review.get("session_id") != dev.get("session_id"),
        "revision en la misma sesion del Developer",
    )
    tree = common.git_tree(ctx.root, review["reviewed_sha"])
    _check(tree is not None, "reviewed_sha no existe localmente (ejecutar git fetch)")
    _check(tree == review["reviewed_tree"], "reviewed_tree no corresponde al reviewed_sha")


def g_review_rejected(ctx: GuardContext) -> None:
    review = ctx.require("review_evidence")
    _check(review["decision"] == "REJECTED", "la revision no esta REJECTED")
    _check(review["findings"], "un rechazo requiere hallazgos estructurados")


def g_rework_available(ctx: GuardContext) -> None:
    _check(int(ctx.state["rework_round"]) < _max_rework(ctx), "rondas de rework agotadas")


def g_rework_exhausted(ctx: GuardContext) -> None:
    _check(int(ctx.state["rework_round"]) >= _max_rework(ctx), "aun quedan rondas de rework")


def g_candidate_rework_available(ctx: GuardContext) -> None:
    limit = int(ctx.policies["harness"]["max_candidate_artifact_rework"])
    _check(int(ctx.state["candidate_rework_round"]) < limit, "rework de artefacto agotado")


def g_candidate_rework_exhausted(ctx: GuardContext) -> None:
    limit = int(ctx.policies["harness"]["max_candidate_artifact_rework"])
    _check(int(ctx.state["candidate_rework_round"]) >= limit, "aun queda rework de artefacto")


def g_merge_valid(ctx: GuardContext) -> None:
    merge = ctx.require("merge_evidence")
    review = ctx.require("review_evidence")
    _check(review["decision"] == "APPROVED", "merge sin revision aprobada")
    _check(merge["reviewed_sha"] == review["reviewed_sha"], "merge de un SHA distinto al revisado")
    _check(merge["reviewed_tree"] == review["reviewed_tree"], "reviewed_tree inconsistente")
    _check(merge["release_tree"] == review["reviewed_tree"], "arbol mergeado distinto del revisado")
    _check(merge["pr_number"] == review["pr_number"], "PR mergeado distinto del revisado")
    _check(merge["method"] == "squash", "metodo de merge distinto de squash")
    release_tree = common.git_tree(ctx.root, merge["release_sha"])
    _check(release_tree is not None, "release_sha no existe localmente (ejecutar git fetch)")
    _check(release_tree == merge["release_tree"], "release_tree no corresponde al release_sha")


def _deployable(ctx: GuardContext) -> bool:
    classes = ctx.profile["release"]["harness_deployable_classes"]
    return _task(ctx)["change_class"] in classes


def g_deploy_required_fast_path(ctx: GuardContext) -> None:
    _check(_task(ctx)["deploy_required"] and _deployable(ctx), "no es un deploy fast path")


def g_no_deploy_required(ctx: GuardContext) -> None:
    _check(not _task(ctx)["deploy_required"], "la tarea requiere deploy")


def g_deploy_required_non_fast_path(ctx: GuardContext) -> None:
    _check(
        _task(ctx)["deploy_required"] and not _deployable(ctx),
        "no es un deploy fuera del fast path",
    )


def g_candidate_valid(ctx: GuardContext) -> None:
    cand = ctx.require("candidate_evidence")
    merge = ctx.require("merge_evidence")
    env = ctx.environment
    artifacts = env["artifacts"]
    _check(cand["release_sha"] == merge["release_sha"], "release_sha del candidate != merge")
    _check(cand["account_id"] == env["account_id"], "cuenta AWS distinta")
    _check(cand["region"] == env["region"], "region AWS distinta")
    _check(
        cand["environment"] == env["deployment_target"]["environment_name"],
        "environment distinto del target DEV",
    )
    _check(str(cand["publish_run"]["conclusion"]).lower() == "success", "publish ECR no exitoso")
    for name in ("app", "caddy"):
        image = cand["images"][name]
        _check(
            image["repository"] == artifacts["ecr_repositories"][name],
            f"repositorio ECR inesperado para {name}",
        )
        _check(
            int(image["scan"]["critical"]) == 0 and int(image["scan"]["high"]) == 0,
            f"scan ECR con HIGH/CRITICAL en {name}",
        )
    _check(cand["bundle"]["reproducible"] is True, "bundle no reproducible")
    label = cand["application_version"]["label"]
    _check(re.fullmatch(artifacts["version_label_pattern"], label), "version label fuera de patron")
    _check(cand["release_sha"][:7] in label, "version label no contiene el release SHA corto")
    expected_key = artifacts["bundle_key_pattern"].format(
        version_label=label, bundle_sha256=cand["bundle"]["sha256"]
    )
    _check(cand["s3"]["bucket"] == artifacts["bundle_bucket"], "bucket de bundle inesperado")
    _check(cand["s3"]["key"] == expected_key, "key S3 no content-addressed")
    _check(
        cand["s3"]["checksum_sha256"] == common.hex_to_b64(cand["bundle"]["sha256"]),
        "checksum S3 no corresponde al bundle",
    )
    observed = cand["environment_observed"]
    lkg = cand["lkg"]
    _check(common.env_healthy(observed), "environment no Ready/Green/Ok antes del release")
    _check(
        observed["version_label"] == lkg["version_label"],
        "el LKG debe ser la version sana observada",
    )
    _check(lkg["version_label"] != label, "LKG igual al candidate")
    _check(
        lkg["status"] in ("UNPROCESSED", "PROCESSED"), "Application Version del LKG no utilizable"
    )
    _check(lkg["option_settings_required"] is False, "el LKG requeriria option settings")
    _check(
        all(
            image["present"] is True and common.DIGEST_RE.fullmatch(image["digest"])
            for image in lkg["images"]
        ),
        "digests del LKG ausentes en ECR: STOP antes del Human Gate",
    )
    _check(
        cand["rollback_plan"]["version_label"] == lkg["version_label"], "plan de rollback != LKG"
    )
    commands = " ".join(cand["deployment_plan"]["commands"])
    _check("--option-settings" not in commands, "el plan contiene --option-settings")


def g_candidate_review_approved(ctx: GuardContext) -> None:
    review = ctx.require("candidate_review_evidence")
    cand = ctx.require("candidate_evidence")
    merge = ctx.require("merge_evidence")
    code_review = ctx.require("review_evidence")
    _check(
        review["decision"] == "APPROVED" and review["cause"] is None, "candidate review no aprobado"
    )
    _check(
        review["release_sha"] == cand["release_sha"] == merge["release_sha"],
        "release_sha inconsistente",
    )
    _check(
        review["release_tree"] == review["reviewed_tree"] == code_review["reviewed_tree"],
        "arbol del release distinto del arbol revisado",
    )
    _check(
        common.git_tree(ctx.root, review["release_sha"]) == review["release_tree"],
        "arbol git no coincide",
    )
    _check(_checks_pass(review["checks"]), "checks del candidate review incompletos o fallidos")


def g_candidate_rejected(ctx: GuardContext, cause: str) -> None:
    review = ctx.require("candidate_review_evidence")
    _check(review["decision"] == "REJECTED", "candidate review no rechazado")
    _check(review["cause"] == cause, f"causa distinta de {cause}")
    _check(review["findings"], "un rechazo requiere hallazgos")


def g_approval_valid(ctx: GuardContext) -> None:
    approval = ctx.require("approval")
    cand = ctx.require("candidate_evidence")
    candidate_review = ctx.require("candidate_review_evidence")
    _check(approval["decision"] == "approved", "la aprobacion no es approved")
    _check(
        approval["created_by"] == "scripts/harness/approve.py",
        "aprobacion no creada por approve.py",
    )
    _check(approval["interactive"] is True, "aprobacion no interactiva")
    _check(candidate_review["decision"] == "APPROVED", "candidate review no aprobado")
    _check(approval["approved_commit"] == cand["release_sha"], "approved_commit != release_sha")
    _check(approval["app_digest"] == cand["images"]["app"]["digest"], "digest app distinto")
    _check(approval["caddy_digest"] == cand["images"]["caddy"]["digest"], "digest caddy distinto")
    _check(approval["bundle_sha256"] == cand["bundle"]["sha256"], "bundle SHA256 distinto")
    _check(approval["s3_key"] == cand["s3"]["key"], "S3 key distinta")
    _check(approval["application_version"] == cand["application_version"]["label"], "AV distinta")
    _check(approval["environment"] == cand["environment"], "environment distinto")
    _check(approval["lkg_version_label"] == cand["lkg"]["version_label"], "LKG distinto")
    ref_path = ctx.state["refs"]["candidate_evidence"]
    _check(approval["candidate_evidence"]["path"] == ref_path, "aprobacion ligada a otra evidencia")
    digest = common.sha256_file(common.resolve_repo_path(ctx.root, ref_path))
    _check(
        approval["candidate_evidence"]["sha256"] == digest,
        "la evidencia del candidate cambio tras aprobar",
    )
    authorization = approval["rollback_authorization"]
    expected_conditions = set(ctx.policies["rollback_authorization"]["conditions"])
    _check(authorization["max_attempts"] == 1, "rollback autorizado con mas de un intento")
    _check(
        authorization["lkg_version_label"] == cand["lkg"]["version_label"], "rollback a otro LKG"
    )
    _check(
        set(authorization["conditions"]) == expected_conditions,
        "condiciones de rollback incompletas",
    )


def g_approval_rejected(ctx: GuardContext) -> None:
    approval = ctx.require("approval")
    _check(approval["decision"] == "rejected", "la decision no es rejected")
    _check(
        approval["created_by"] == "scripts/harness/approve.py", "decision no creada por approve.py"
    )


def g_deployment_succeeded(ctx: GuardContext) -> None:
    dep = ctx.require("deployment_evidence")
    approval = ctx.require("approval")
    _check(dep["result"] == "success", "deployment no exitoso")
    _check(dep["update_accepted"] is True, "update-environment no aceptado")
    _check(dep["approved_commit"] == approval["approved_commit"], "approved_commit alterado")
    _check(
        dep["deployed_commit"] == approval["approved_commit"], "approved_commit != deployed_commit"
    )
    _check(
        dep["application_version"] == approval["application_version"], "AV desplegada != aprobada"
    )
    _check(dep["environment"] == approval["environment"], "environment desplegado != aprobado")
    _check(dep["account_id"] == ctx.environment["account_id"], "cuenta AWS distinta")
    _check(dep["region"] == ctx.environment["region"], "region AWS distinta")
    final = dep["final_state"]
    _check(common.env_healthy(final), "environment final no Ready/Green/Ok")
    _check(
        final["version_label"] == approval["application_version"], "VersionLabel final != aprobada"
    )
    _check(
        all(value is True for value in dep["runtime_identity"].values()),
        "identidad de runtime no verificada",
    )


def g_deployment_failed(ctx: GuardContext) -> None:
    dep = ctx.require("deployment_evidence")
    _check(dep["result"] == "failure", "el deployment no registra fallo")


def g_verification_passed(ctx: GuardContext) -> None:
    task = _task(ctx)
    ver = ctx.require("verification_evidence")
    approval = ctx.require("approval")
    dep = ctx.require("deployment_evidence")
    _check(ver["result"] == "PASS", "verificacion no PASS")
    _check(ver["approved_commit"] == approval["approved_commit"], "approved_commit alterado")
    _check(
        ver["deployed_commit"] == dep["deployed_commit"] == approval["approved_commit"],
        "commit desplegado distinto",
    )
    _check(_checks_pass(ver["smoke"]), "smoke incompleto o fallido")
    # v1.1: strong indicators always block; weak ones need a recorded human classification.
    log_reasons = log_scan.check(ver["pii_log_scan"], ctx.policies)
    _check(not log_reasons, "; ".join(log_reasons))
    reported = {item["id"]: item for item in ver["acceptance_criteria"]}
    human_ids = set()
    for criterion in task["acceptance_criteria"]:
        item = reported.get(criterion["id"])
        _check(item is not None, f"criterio {criterion['id']} sin verificar")
        if criterion["verification"] in ("human", "both"):
            human_ids.add(criterion["id"])
        else:
            _check(item["status"] == "met", f"criterio {criterion['id']} no cumplido")
    if task.get("requires_human_acceptance") or human_ids:
        acceptance = ctx.require("acceptance")
        _check(acceptance["decision"] == "accepted", "aceptacion humana no otorgada")
        _check(
            acceptance["created_by"] == "scripts/harness/approve.py",
            "aceptacion no creada por approve.py",
        )
        accepted = {
            item["id"] for item in acceptance["criteria"] if item.get("status") == "accepted"
        }
        _check(human_ids <= accepted, "criterios humanos sin aceptacion")


def g_verification_failed(ctx: GuardContext) -> None:
    ver = ctx.require("verification_evidence")
    _check(ver["result"] == "FAIL", "la verificacion no registra fallo")
    _check(
        ver["failure_class"] in ("infrastructure", "functional", "observability"),
        "fallo sin clasificar",
    )


def g_rollback_permitted(ctx: GuardContext) -> None:
    pre = ctx.require("rollback_precheck_evidence")
    approval = ctx.require("approval")
    cand = ctx.require("candidate_evidence")
    _check(pre["phase"] == "precheck", "falta precheck de rollback")
    _check(not ctx.state.get("rollback_attempted"), "ya se intento un rollback")
    _check(int(pre["prior_rollback_attempts"]) == 0, "ya se intento un rollback")
    _check(approval.get("decision") == "approved", "sin aprobacion vigente")
    authorization = approval.get("rollback_authorization") or {}
    _check(authorization.get("max_attempts") == 1, "sin autorizacion condicionada de rollback")
    _check(
        pre["to_version"] == approval["lkg_version_label"] == cand["lkg"]["version_label"],
        "LKG distinto del aprobado",
    )
    _check(pre["update_accepted_prior"] is True, "UpdateEnvironment no fue aceptado: NO rollback")
    if ctx.state["state"] == "DEPLOY_FAILED":
        dep = ctx.require("deployment_evidence")
        _check(dep["update_accepted"] is True, "UpdateEnvironment rechazado: NO rollback")
    if ctx.state["state"] == "VERIFY_FAILED":
        ver = ctx.require("verification_evidence")
        _check(
            ver["failure_class"] == "infrastructure",
            "defecto funcional u observabilidad: NO rollback",
        )
    _check(
        pre["failure_class"] == "infrastructure",
        "solo degradacion de infraestructura habilita rollback",
    )
    _check(pre["lkg_usable"] is True, "LKG no utilizable")
    _check(pre["lkg_images_present"] is True, "imagenes del LKG ausentes en ECR")
    _check(pre["option_settings_required"] is False, "rollback requeriria option settings")


def g_rollback_result_recorded(ctx: GuardContext) -> None:
    result = ctx.require("rollback_evidence")
    _check(result["phase"] == "result", "falta resultado de rollback")
    _check(result.get("result") in ("success", "failure"), "resultado de rollback invalido")


def g_failure_recorded(ctx: GuardContext) -> None:
    failure = ctx.require("failure_evidence")
    _check(failure["state"] == ctx.state["state"], "la falla registrada no corresponde al estado")


def g_resolution_target(ctx: GuardContext, target: str) -> None:
    resolution = ctx.require("resolution")
    _check(
        resolution["created_by"] == "scripts/harness/approve.py",
        "resolucion no creada por approve.py",
    )
    _check(resolution["from_state"] == "BLOCKED_HUMAN", "resolucion fuera de BLOCKED_HUMAN")
    _check(resolution["to_state"] == target, f"resolucion no apunta a {target}")


GUARDS: dict[str, Callable[..., None]] = {
    "task_selected": g_task_selected,
    "task_active": g_task_active,
    "developer_evidence_valid": g_developer_evidence_valid,
    "reviewer_session_independent": g_reviewer_session_independent,
    "review_approved": g_review_approved,
    "review_rejected": g_review_rejected,
    "rework_available": g_rework_available,
    "rework_exhausted": g_rework_exhausted,
    "candidate_rework_available": g_candidate_rework_available,
    "candidate_rework_exhausted": g_candidate_rework_exhausted,
    "merge_valid": g_merge_valid,
    "deploy_required_fast_path": g_deploy_required_fast_path,
    "no_deploy_required": g_no_deploy_required,
    "deploy_required_non_fast_path": g_deploy_required_non_fast_path,
    "candidate_valid": g_candidate_valid,
    "candidate_review_approved": g_candidate_review_approved,
    "candidate_rejected": g_candidate_rejected,
    "approval_valid": g_approval_valid,
    "approval_rejected": g_approval_rejected,
    "deployment_succeeded": g_deployment_succeeded,
    "deployment_failed": g_deployment_failed,
    "verification_passed": g_verification_passed,
    "verification_failed": g_verification_failed,
    "rollback_permitted": g_rollback_permitted,
    "rollback_result_recorded": g_rollback_result_recorded,
    "failure_recorded": g_failure_recorded,
    "resolution_target": g_resolution_target,
}


def known_guard(name: str) -> bool:
    return name.split(":", 1)[0] in GUARDS


def evaluate(name: str, ctx: GuardContext) -> str | None:
    """Return ``None`` when the guard holds, otherwise the failure reason."""
    base, _, argument = name.partition(":")
    guard = GUARDS.get(base)
    if guard is None:
        return f"guard desconocido: {name}"
    try:
        if argument:
            guard(ctx, argument)
        else:
            guard(ctx)
    except GuardError as failure:
        return f"{name}: {failure}"
    except (KeyError, TypeError, ValueError, common.HarnessError) as error:
        return f"{name}: evidencia invalida ({error})"
    return None
