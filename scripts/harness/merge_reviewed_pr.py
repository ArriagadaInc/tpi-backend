"""Merge the PR the Reviewer approved, and ONLY that one (Deployer, state MERGING).

Usage:
  python scripts/harness/merge_reviewed_pr.py

It takes NO arguments on purpose. The PR number and the SHA come from the harness evidence of the
active task (``review_evidence``, cross-checked with ``developer_evidence``), never from the
command line, so a permission rule for exactly this command lets the Deployer merge the reviewed
PR and nothing else. Before merging it re-reads GitHub and refuses unless:

  * the state is MERGING and the review evidence is APPROVED for this task;
  * the PR is open, targets the default branch and its head IS the reviewed SHA;
  * GitHub reports it MERGEABLE and CLEAN, with at least one check and every check passing.

Then it runs ``gh pr merge <n> --repo <repo> --squash --match-head-commit <sha>`` and confirms
the merge. It writes nothing in the repository: the Deployer still verifies the release tree,
records the merge evidence and applies the ``merged`` transition. Safe to repeat: a PR already
merged at the reviewed SHA is reported, never merged twice.

Exit codes: 0 merged (or already merged), 2 refused (nothing was merged), 3 merge failed.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

SHA_RE = re.compile(r"[0-9a-f]{40}")
PASSING_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
VIEW_FIELDS = (
    "number,state,headRefOid,baseRefName,mergeable,mergeStateStatus,statusCheckRollup,mergeCommit"
)
Runner = Callable[[list[str], float], tuple[int, str, str]]


class Refused(common.HarnessError):
    """A precondition failed: nothing was merged."""


class MergeFailed(common.HarnessError):
    """``gh pr merge`` did not complete: the PR may not be merged."""


@dataclasses.dataclass(frozen=True)
class Target:
    task_id: str
    pr_number: int
    reviewed_sha: str
    repository: str
    base: str


@dataclasses.dataclass(frozen=True)
class Result:
    pr_number: int
    reviewed_sha: str
    merge_commit: str
    already_merged: bool


def _subprocess_runner(command: list[str], timeout: float) -> tuple[int, str, str]:
    executable = shutil.which(command[0])
    if not executable:
        raise FileNotFoundError(command[0])
    result = subprocess.run(  # noqa: S603
        [executable, *command[1:]],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return common.redact(lines[0])[:200] if lines else ""


def _run(
    runner: Runner, command: list[str], timeout: float, error: type[common.HarnessError]
) -> tuple[int, str, str]:
    try:
        return runner(command, timeout)
    except FileNotFoundError as missing:
        raise error("el CLI de GitHub (gh) no esta en PATH") from missing
    except subprocess.TimeoutExpired as slow:
        raise error(f"gh {command[1]} {command[2]} excedio {timeout:.0f}s") from slow
    except OSError as broken:
        raise error(f"no se pudo ejecutar gh ({broken.__class__.__name__})") from broken


def target(root: Path) -> Target:
    """What may be merged: the PR and SHA of the approved review, from the harness evidence."""
    try:
        state = common.load_state(root)
        if state.get("state") != "MERGING" or not state.get("task_id"):
            raise Refused(
                f"solo se mergea en MERGING con una tarea activa (estado: {state.get('state')})"
            )
        review = common.load_ref(root, state, "review_evidence")
        developer = common.load_ref(root, state, "developer_evidence")
        if review is None or developer is None:
            raise Refused("faltan review_evidence o developer_evidence en el estado")
        if review.get("decision") != "APPROVED" or review.get("task_id") != state["task_id"]:
            raise Refused("la revision no esta aprobada para esta tarea")
        sha, number = review.get("reviewed_sha"), review.get("pr_number")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise Refused("reviewed_sha de la revision no es un SHA de 40 hex")
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise Refused("pr_number de la revision no es valido")
        if developer.get("head_sha") != sha or developer.get("pr_number") != number:
            raise Refused("el PR o el SHA revisados no coinciden con los que entrego el Developer")
        project = common.load_profile(root)["project"]
        return Target(
            task_id=str(state["task_id"]),
            pr_number=number,
            reviewed_sha=sha,
            repository=str(project["repository"]),
            base=str(project.get("default_branch", "main")),
        )
    except Refused:
        raise
    except (OSError, ValueError, KeyError, TypeError, common.HarnessError) as error:
        raise Refused(f"no se pudo leer la evidencia del arnes: {error}") from error


def view(repository: str, number: int, runner: Runner, timeout: float = 60.0) -> dict[str, Any]:
    command = ["gh", "pr", "view", str(number), "--repo", repository, "--json", VIEW_FIELDS]
    code, stdout, stderr = _run(runner, command, timeout, Refused)
    if code != 0:
        raise Refused(f"gh pr view fallo: {_first_line(stderr) or f'exit code {code}'}")
    try:
        data = json.loads(stdout)
    except ValueError as error:
        raise Refused("la respuesta de gh pr view no es JSON") from error
    if not isinstance(data, dict):
        raise Refused("la respuesta de gh pr view tiene un formato inesperado")
    return data


def _failing_checks(rollup: Any) -> list[str]:
    """Names of the checks that are not passing; a PR with no checks at all is refused."""
    if not isinstance(rollup, list) or not rollup:
        return ["no hay ningun check"]
    failing: list[str] = []
    for item in rollup:
        if not isinstance(item, dict):
            failing.append("?")
            continue
        name = str(item.get("name") or item.get("context") or "?")
        if item.get("__typename") == "StatusContext" or ("state" in item and "status" not in item):
            passing = item.get("state") == "SUCCESS"
        else:
            passing = (
                item.get("status") == "COMPLETED" and item.get("conclusion") in PASSING_CONCLUSIONS
            )
        if not passing:
            failing.append(name)
    return failing


def _merge_commit(data: dict[str, Any]) -> str:
    commit = data.get("mergeCommit")
    oid = commit.get("oid") if isinstance(commit, dict) else None
    if not isinstance(oid, str) or not SHA_RE.fullmatch(oid):
        raise MergeFailed("el PR figura mergeado pero sin merge commit legible")
    return oid


def _verify_open(wanted: Target, data: dict[str, Any]) -> None:
    if data.get("state") != "OPEN":
        raise Refused(f"el PR #{wanted.pr_number} no esta abierto (estado: {data.get('state')})")
    if data.get("baseRefName") != wanted.base:
        raise Refused(
            f"el PR #{wanted.pr_number} no apunta a {wanted.base} (apunta a {data.get('baseRefName')})"
        )
    if data.get("mergeable") != "MERGEABLE" or data.get("mergeStateStatus") != "CLEAN":
        raise Refused(
            f"el PR #{wanted.pr_number} no esta listo: mergeable={data.get('mergeable')}, "
            f"estado={data.get('mergeStateStatus')} (se exige MERGEABLE y CLEAN)"
        )
    failing = _failing_checks(data.get("statusCheckRollup"))
    if failing:
        raise Refused("checks que no pasan: " + ", ".join(failing))


def merge(root: Path, *, runner: Runner | None = None) -> Result:
    """Merge the reviewed PR if, and only if, every condition in the module docstring holds."""
    run = runner or _subprocess_runner
    wanted = target(root)
    data = view(wanted.repository, wanted.pr_number, run)
    if data.get("headRefOid") != wanted.reviewed_sha:
        raise Refused(
            f"la cabeza del PR #{wanted.pr_number} ({str(data.get('headRefOid'))[:7]}) no es el "
            f"SHA revisado ({wanted.reviewed_sha[:7]})"
        )
    if data.get("state") == "MERGED":
        return Result(wanted.pr_number, wanted.reviewed_sha, _merge_commit(data), True)
    _verify_open(wanted, data)
    command = [
        "gh", "pr", "merge", str(wanted.pr_number), "--repo", wanted.repository,
        "--squash", "--match-head-commit", wanted.reviewed_sha,
    ]  # fmt: skip
    code, _, stderr = _run(run, command, 120.0, MergeFailed)
    if code != 0:
        raise MergeFailed(f"gh pr merge fallo: {_first_line(stderr) or f'exit code {code}'}")
    after = view(wanted.repository, wanted.pr_number, run)
    if after.get("state") != "MERGED":
        raise MergeFailed("gh pr merge termino sin error pero el PR no figura MERGED")
    return Result(wanted.pr_number, wanted.reviewed_sha, _merge_commit(after), False)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write(
            "merge_reviewed_pr.py no admite argumentos: el PR y el SHA salen de la evidencia "
            "de la revision aprobada\n"
        )
        return 2
    try:
        result = merge(common.ROOT)
    except MergeFailed as error:
        sys.stderr.write(f"MERGE FALLIDO (revisa el estado del PR antes de reintentar): {error}\n")
        return 3
    except common.HarnessError as error:
        sys.stderr.write(f"MERGE RECHAZADO (no se mergeo nada): {error}\n")
        return 2
    print(json.dumps(dataclasses.asdict(result), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
