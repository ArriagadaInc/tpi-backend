"""Single controlled entrypoint for AWS CLI operations of harness agents.

Usage:
  python scripts/harness/aws_guard.py [--dry-run] <service> <operation> [options...]

The permitted operation set depends on ROLE (derived from state) + STATE + ENVIRONMENT
(harness/policies.yaml). Profile and region are always forced. Output is redacted.
AccessDenied means STOP: failure evidence is written and no retry is attempted.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from . import common, evidence
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]
    import evidence  # type: ignore[no-redef]

BOOLEAN_FLAGS = {
    "--no-process",
    "--process",
    "--no-auto-create-application",
    "--auto-create-application",
    "--no-include-deleted",
    "--include-deleted",
    "--no-paginate",
    "--no-cli-pager",
    "--start-from-head",
    "--interleaved",
}
ALWAYS_DENIED_FLAGS = {
    "--cli-input-json",
    "--cli-input-yaml",
    "--generate-cli-skeleton",
    "--debug",
    "--ca-bundle",
}
COMMON_OUTPUT_FLAGS = {
    "--output",
    "--query",
    "--no-cli-pager",
    "--no-paginate",
    "--max-items",
    "--page-size",
}
CANONICAL_REMOTE = "ArriagadaInc/tpi-backend"


@dataclass
class ParsedCommand:
    service: str
    operation: str
    options: dict[str, list[str | None]]
    tokens: list[str]

    @property
    def key(self) -> str:
        return f"{self.service} {self.operation}"

    def one(self, name: str) -> str | None:
        values = self.options.get(name)
        if not values:
            return None
        if len(values) != 1:
            raise common.HarnessError(f"opcion repetida: {name}")
        return values[0]


@dataclass
class Decision:
    allowed: bool
    state: str
    role: str
    mode: str
    operation: str
    reasons: list[str] = field(default_factory=list)
    argv: list[str] = field(default_factory=list)
    maintenance: bool = False


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def parse(tokens: list[str]) -> ParsedCommand:
    positionals: list[str] = []
    options: dict[str, list[str | None]] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            if "=" in token:
                name, value = token.split("=", 1)
                options.setdefault(name, []).append(value)
                index += 1
            elif (
                token in BOOLEAN_FLAGS
                or index + 1 >= len(tokens)
                or tokens[index + 1].startswith("--")
            ):
                options.setdefault(token, []).append(None)
                index += 1
            else:
                options.setdefault(token, []).append(tokens[index + 1])
                index += 2
        elif token.startswith("-"):
            raise common.HarnessError(f"opcion corta no permitida: {token}")
        else:
            positionals.append(token)
            index += 1
    if len(positionals) != 2:
        raise common.HarnessError(
            "se requiere exactamente <service> <operation> sin posicionales extra"
        )
    return ParsedCommand(positionals[0], positionals[1], options, list(tokens))


def _expand_mode(modes: dict[str, list[str]], mode: str) -> set[str]:
    result: set[str] = set()
    for entry in modes.get(mode, []):
        if entry.startswith("@"):
            result |= _expand_mode(modes, entry[1:])
        else:
            result.add(entry)
    return result


def _audit_records(root: Path, task_id: str | None) -> list[dict[str, Any]]:
    if not task_id:
        return []
    path = common.evidence_task_dir(root, task_id) / "aws-audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _release_sha(root: Path, state: dict[str, Any]) -> str:
    merge = common.load_ref(root, state, "merge_evidence")
    if not merge or not common.SHA_RE.fullmatch(merge.get("release_sha", "")):
        raise common.HarnessError("sin merge_evidence con release_sha")
    return str(merge["release_sha"])


def _only_options(cmd: ParsedCommand, allowed: set[str]) -> list[str]:
    extra = sorted(set(cmd.options) - allowed - COMMON_OUTPUT_FLAGS - {"--profile", "--region"})
    return [f"opcion no permitida para {cmd.key}: {name}" for name in extra]


def _label_ok(
    root: Path, state: dict[str, Any], env: dict[str, Any], label: str | None
) -> list[str]:
    if not label or not re.fullmatch(env["artifacts"]["version_label_pattern"], label):
        return ["version label ausente o fuera de patron"]
    if _release_sha(root, state)[:7] not in label:
        return ["version label no contiene el release SHA corto"]
    return []


def _key_parts(env: dict[str, Any], key: str | None) -> re.Match[str] | None:
    prefix = re.escape(env["artifacts"]["bundle_key_prefix"])
    return re.fullmatch(prefix + r"/(?P<label>[^/]+)/(?P<sha>[0-9a-f]{64})\.zip", key or "")


def v_put_object(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    reasons = _only_options(
        cmd,
        {
            "--bucket",
            "--key",
            "--body",
            "--checksum-algorithm",
            "--checksum-sha256",
            "--if-none-match",
            "--content-type",
            "--metadata",
        },
    )
    if cmd.one("--bucket") != env["artifacts"]["bundle_bucket"]:
        reasons.append("bucket distinto del bucket de bundles DEV")
    parts = _key_parts(env, cmd.one("--key"))
    if parts is None:
        return reasons + ["key S3 no content-addressed <prefix>/<label>/<sha256>.zip"]
    reasons += _label_ok(root, state, env, parts["label"])
    if (cmd.one("--checksum-algorithm") or "").upper() != "SHA256":
        reasons.append("--checksum-algorithm SHA256 obligatorio")
    try:
        checksum = base64.b64decode(cmd.one("--checksum-sha256") or "", validate=True)
    except (binascii.Error, ValueError):
        checksum = b""
    if checksum != bytes.fromhex(parts["sha"]):
        reasons.append("--checksum-sha256 no corresponde al SHA256 de la key")
    if cmd.one("--if-none-match") != "*":
        reasons.append("--if-none-match '*' obligatorio (nunca sobrescribir)")
    body = cmd.one("--body")
    body_path = Path(body) if body else None
    if body_path is None:
        reasons.append("--body obligatorio")
    else:
        relative = common.to_repo_relative(root, body_path)
        if relative is None or not relative.startswith(".harness-release/"):
            reasons.append("--body debe estar dentro de .harness-release/")
        elif not common.resolve_repo_path(root, relative).is_file():
            reasons.append("--body no existe")
        elif common.sha256_file(common.resolve_repo_path(root, relative)) != parts["sha"]:
            reasons.append("SHA256 del archivo local distinto de la key")
    return reasons


def v_create_application_version(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    reasons = _only_options(
        cmd,
        {
            "--application-name",
            "--version-label",
            "--source-bundle",
            "--no-process",
            "--no-auto-create-application",
            "--description",
        },
    )
    if cmd.one("--application-name") != env["application"]:
        reasons.append("application distinta")
    label = cmd.one("--version-label")
    reasons += _label_ok(root, state, env, label)
    if "--no-process" not in cmd.options:
        reasons.append("--no-process obligatorio")
    if "--no-auto-create-application" not in cmd.options:
        reasons.append("--no-auto-create-application obligatorio")
    source = dict(
        item.split("=", 1) for item in (cmd.one("--source-bundle") or "").split(",") if "=" in item
    )
    parts = _key_parts(env, source.get("S3Key"))
    if source.get("S3Bucket") != env["artifacts"]["bundle_bucket"] or parts is None:
        reasons.append("--source-bundle debe apuntar al bundle content-addressed DEV")
    elif parts["label"] != label:
        reasons.append("la key del bundle no corresponde al version label")
    return reasons


def v_update_environment(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    reasons = _only_options(cmd, {"--environment-name", "--application-name", "--version-label"})
    if cmd.one("--environment-name") != env["deployment_target"]["environment_name"]:
        reasons.append("environment distinto del target DEV")
    application = cmd.one("--application-name")
    if application is not None and application != env["application"]:
        reasons.append("application distinta")
    label = cmd.one("--version-label")
    approval = common.load_ref(root, state, "approval")
    candidate = common.load_ref(root, state, "candidate_evidence")
    if (
        not approval
        or approval.get("decision") != "approved"
        or approval.get("created_by") != "scripts/harness/approve.py"
    ):
        return reasons + ["sin aprobacion humana valida (Human Gate)"]
    if not candidate or approval.get("approved_commit") != candidate.get("release_sha"):
        return reasons + ["la aprobacion no corresponde al candidate vigente"]
    audit = _audit_records(root, state.get("task_id"))
    if mode == "cutover":
        if label != approval.get("application_version"):
            reasons.append("version label distinta de la aprobada")
        if any(r.get("executed") and r.get("mutation") == "cutover" for r in audit):
            reasons.append("ya hubo un intento de cutover: un release, una promocion")
    elif mode == "rollback":
        authorization = approval.get("rollback_authorization") or {}
        if label != authorization.get("lkg_version_label") or label != approval.get(
            "lkg_version_label"
        ):
            reasons.append("rollback solo al LKG aprobado")
        if not state.get("rollback_attempted"):
            reasons.append("rollback sin transicion start_rollback")
        if any(r.get("executed") and r.get("mutation") == "rollback" for r in audit):
            reasons.append("ya se ejecuto un rollback")
    else:
        reasons.append(f"update-environment no permitido en modo {mode}")
    return reasons


def v_head_object(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    reasons = _only_options(cmd, {"--bucket", "--key", "--checksum-mode", "--version-id"})
    if cmd.one("--bucket") != env["artifacts"]["bundle_bucket"]:
        reasons.append("head-object solo sobre el bucket de bundles DEV")
    if not (cmd.one("--key") or "").startswith(env["artifacts"]["bundle_key_prefix"] + "/"):
        reasons.append("head-object solo sobre el prefijo de releases DEV")
    return reasons


def v_ecr(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    repositories = set(env["artifacts"]["ecr_repositories"].values())
    if cmd.operation == "describe-repositories":
        return _only_options(cmd, {"--repository-names"})
    reasons = _only_options(cmd, {"--repository-name", "--image-ids"})
    if cmd.one("--repository-name") not in repositories:
        reasons.append("repositorio ECR fuera del entorno DEV")
    return reasons


def v_logs_filter(
    root: Path, state: dict[str, Any], env: dict[str, Any], cmd: ParsedCommand, mode: str
) -> list[str]:
    reasons = _only_options(
        cmd, {"--log-group-name", "--filter-pattern", "--start-time", "--end-time"}
    )
    group_prefix = f"/aws/elasticbeanstalk/{env['deployment_target']['environment_name']}/"
    if not (cmd.one("--log-group-name") or "").startswith(group_prefix):
        reasons.append("log group fuera del environment DEV")
    if "length(" not in (cmd.one("--query") or ""):
        reasons.append("filter-log-events solo con --query 'length(events)' (sin volcar lineas)")
    return reasons


VALIDATORS: dict[
    str, Callable[[Path, dict[str, Any], dict[str, Any], ParsedCommand, str], list[str]]
] = {
    "s3api put-object": v_put_object,
    "elasticbeanstalk create-application-version": v_create_application_version,
    "elasticbeanstalk update-environment": v_update_environment,
    "s3api head-object": v_head_object,
    "ecr describe-images": v_ecr,
    "ecr describe-image-scan-findings": v_ecr,
    "ecr describe-repositories": v_ecr,
    "logs filter-log-events": v_logs_filter,
}
MUTATIONS = {
    "s3api put-object": "stage-bundle",
    "elasticbeanstalk create-application-version": "stage-application-version",
}


def _final_argv(cmd: ParsedCommand, profile: str, region: str) -> list[str]:
    cleaned: list[str] = []
    skip = False
    for token in cmd.tokens:
        if skip:
            skip = False
            continue
        if token in ("--profile", "--region"):
            skip = True
            continue
        if token.startswith(("--profile=", "--region=")):
            continue
        cleaned.append(token)
    argv = ["aws", *cleaned, "--profile", profile, "--region", region]
    if "--output" not in cmd.options:
        argv += ["--output", "json"]
    if "--no-cli-pager" not in cmd.options:
        argv.append("--no-cli-pager")
    return argv


def evaluate(
    root: Path, tokens: list[str], *, env_vars: Mapping[str, str] | None = None
) -> Decision:
    env_vars = os.environ if env_vars is None else env_vars
    state = common.load_state(root)
    workflow = common.load_workflow(root)
    policies = common.load_policies(root)
    environment = common.load_environment(root, state.get("environment", "dev"))
    aws = policies["aws"]
    current = state["state"]
    role = common.state_role(workflow, current)
    mode = aws["state_modes"].get(current, {}).get(role, "none")
    # D6: mantenimiento NO amplia el acceso AWS. El modo depende solo de rol + estado +
    # entorno (state_modes). Se registra maintenance en la auditoria (_audit) sin que
    # afecte la decision: si el estado/rol normalmente resuelve a "none", sigue en "none".
    maintenance = env_vars.get(policies["harness"]["maintenance_env_var"]) == "1"
    decision = Decision(False, current, role, mode, " ".join(tokens[:2]))
    try:
        cmd = parse(tokens)
    except common.HarnessError as error:
        decision.reasons.append(str(error))
        return decision
    decision.operation = cmd.key
    reasons = decision.reasons
    if mode == "none":
        reasons.append(f"sin acceso AWS para rol '{role}' en estado {current}")
    if env_vars.get("CLAUDECODE") != "1":
        reasons.append("runtime sin enforcement demostrado: AWS solo desde Claude Code")
    if cmd.service in aws["global_deny_services"]:
        reasons.append(f"servicio prohibido en el Harness: {cmd.service}")
    if cmd.key in aws["global_deny_operations"]:
        reasons.append(f"operacion prohibida: {cmd.key}")
    for flag in sorted(set(aws["global_deny_flags"]) | ALWAYS_DENIED_FLAGS):
        if flag in cmd.options:
            reasons.append(f"flag prohibido: {flag}")
    for name, expected in (("--profile", aws["profile"]), ("--region", aws["region"])):
        value = cmd.options.get(name)
        if value and value != [expected]:
            reasons.append(f"{name} debe ser {expected}")
    if mode != "none" and cmd.key not in _expand_mode(aws["modes"], mode):
        reasons.append(f"'{cmd.key}' no permitido en {current} para {role} (modo {mode})")
    if not reasons and cmd.key in VALIDATORS:
        try:
            reasons.extend(VALIDATORS[cmd.key](root, state, environment, cmd, mode))
        except (common.HarnessError, KeyError, ValueError) as error:
            reasons.append(f"validacion fallida: {error}")
    decision.allowed = not reasons
    decision.argv = _final_argv(cmd, aws["profile"], aws["region"])
    decision.maintenance = maintenance
    return decision


def _audit(root: Path, state: dict[str, Any], decision: Decision, **extra: Any) -> None:
    task_id = state.get("task_id") or "_no_task"
    directory = root / "evidence" / task_id
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "at": common.now_iso(),
        "state": decision.state,
        "role": decision.role,
        "mode": decision.mode,
        "operation": decision.operation,
        "argv": common.redact(" ".join(decision.argv[1:])),
        "allowed": decision.allowed,
        "reasons": decision.reasons,
        # D5/D6: mantenimiento auditado; nunca cambia mode/allowed (ver evaluate()).
        "maintenance_mode": getattr(decision, "maintenance", False),
        **extra,
    }
    with (directory / "aws-audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _subprocess_runner(argv: list[str]) -> RunResult:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    return RunResult(result.returncode, result.stdout, result.stderr)


def _verify_canonical_repo(root: Path) -> None:
    toplevel = Path(common.git(root, "rev-parse", "--show-toplevel")).resolve()
    if toplevel != root.resolve():
        raise common.HarnessError(
            "aws_guard debe ejecutarse desde el checkout canonico del repositorio"
        )
    remote = common.git(root, "remote", "get-url", "origin", check=False)
    if CANONICAL_REMOTE not in remote:
        raise common.HarnessError("remote origin no es el repositorio TPI")


def run(
    root: Path,
    tokens: list[str],
    *,
    dry_run: bool = False,
    runner: Callable[[list[str]], RunResult] | None = None,
    env_vars: Mapping[str, str] | None = None,
    verify_repo: bool = True,
) -> int:
    state = common.load_state(root)
    decision = evaluate(root, tokens, env_vars=env_vars)
    if not decision.allowed:
        _audit(root, state, decision, executed=False)
        print("AWS GUARD: DENIED", file=sys.stderr)
        for reason in decision.reasons:
            print(f"  - {reason}", file=sys.stderr)
        print(common.STOP_BANNER, file=sys.stderr)
        return 2
    if dry_run:
        _audit(root, state, decision, executed=False, dry_run=True)
        print("AWS GUARD: ALLOWED (dry-run) " + common.redact(" ".join(decision.argv)))
        return 0
    if verify_repo:
        _verify_canonical_repo(root)
    runner = runner or _subprocess_runner
    policies = common.load_policies(root)
    environment = common.load_environment(root, state.get("environment", "dev"))
    aws = policies["aws"]
    markers = aws["access_denied_markers"]
    if decision.operation != "sts get-caller-identity":
        identity = runner(
            [
                "aws",
                "sts",
                "get-caller-identity",
                "--profile",
                aws["profile"],
                "--region",
                aws["region"],
                "--output",
                "json",
            ]
        )
        account = None
        if identity.returncode == 0:
            try:
                account = json.loads(identity.stdout).get("Account")
            except json.JSONDecodeError:
                account = None
        if account != environment["account_id"]:
            _audit(root, state, decision, executed=False, identity_check="failed")
            print(
                "AWS GUARD: STOP - identidad AWS no verificada o cuenta distinta", file=sys.stderr
            )
            return 3
    mutation = MUTATIONS.get(decision.operation)
    if decision.operation == "elasticbeanstalk update-environment":
        mutation = decision.mode
    result = runner(decision.argv)
    access_denied = any(marker in result.stderr for marker in markers)
    _audit(
        root,
        state,
        decision,
        executed=True,
        mutation=mutation,
        exit_code=result.returncode,
        access_denied=access_denied,
    )
    sys.stdout.write(common.redact(result.stdout))
    sys.stderr.write(common.redact(result.stderr))
    if access_denied:
        _record_access_denied(root, state, decision, result)
        print(
            "\nAWS GUARD: ACCESS DENIED -> STOP. No agregar permisos, no reintentar, no cambiar principal.",
            file=sys.stderr,
        )
        print(common.STOP_BANNER, file=sys.stderr)
        return 3
    return result.returncode


def _record_access_denied(
    root: Path, state: dict[str, Any], decision: Decision, result: RunResult
) -> None:
    if not state.get("task_id") or decision.role not in common.AGENT_ROLES:
        return
    payload = {
        "action": decision.operation,
        "resource": common.redact(" ".join(decision.argv[3:])),
        "principal": "perfil tpi-dev (ver sts get-caller-identity; no se registra ARN completo)",
        "error": common.redact(result.stderr.strip())[:2000],
        "state": decision.state,
        "recommendation": "Revisar el contrato IAM completo de la operacion; decision humana requerida.",
        "residues": [],
        "access_denied": True,
    }
    try:
        evidence.write_evidence(
            root,
            "failure",
            payload,
            runtime="claude",
            session=os.environ.get("TPI_HARNESS_SESSION", "aws-guard"),
        )
    except common.HarnessError as error:
        print(f"no se pudo registrar evidencia de AccessDenied: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    dry_run = False
    if tokens and tokens[0] == "--dry-run":
        dry_run = True
        tokens = tokens[1:]
    if tokens and tokens[0] == "aws":
        tokens = tokens[1:]
    try:
        return run(common.ROOT, tokens, dry_run=dry_run)
    except common.HarnessError as error:
        print(f"AWS GUARD: STOP - {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
