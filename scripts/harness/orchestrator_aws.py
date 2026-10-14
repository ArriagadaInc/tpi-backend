"""Read-only AWS session preflight for the Orchestrator v2: ONE fixed operation.

The only command this module can ever run:

  aws sts get-caller-identity --profile <aws.profile> --region <aws.region> --output json
      --no-cli-pager

Profile, region and the expected account come from harness/policies.yaml and
environments/<env>.yaml (single source). It answers a single question before an LLM turn is spent:
"is the local tpi-dev session valid?" (the real cause of the H3.3.2 and H3.3.7 BLOCKED_HUMAN).

Documented exception to "every AWS operation goes through aws_guard.py": aws_guard resolves
permissions from the agent role + workflow state and requires CLAUDECODE=1, which a
human-launched orchestrator does not have; it also writes audit records into evidence/. This
module is NOT a path for agents. It writes nothing in the repository, never returns the ARN or
user id and redacts stderr. Do not extend it with other operations.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from . import common
except ImportError:  # executed as a script
    import common  # type: ignore[no-redef]

# stderr fragments meaning "the local session is not valid": the human must re-authenticate.
SESSION_MARKERS = (
    "expired",
    "aws login",
    "aws sso login",
    "expiredtoken",
    "invalidclienttokenid",
    "unrecognizedclient",
    "unable to locate credentials",
)
Runner = Callable[[list[str], float], tuple[int, str, str]]


@dataclasses.dataclass(frozen=True)
class AwsPreflight:
    status: str  # ok | expired | wrong_account | unavailable
    detail: str = ""


def required(policies: dict[str, Any], state_name: str, role: str) -> bool:
    """True when the next worker (role in state) is granted AWS access by the Harness policies."""
    modes = (policies["aws"].get("state_modes") or {}).get(state_name) or {}
    return modes.get(role, "none") != "none"


def argv(policies: dict[str, Any]) -> list[str]:
    aws = policies["aws"]
    return [
        "aws",
        "sts",
        "get-caller-identity",
        "--profile",
        aws["profile"],
        "--region",
        aws["region"],
        "--output",
        "json",
        "--no-cli-pager",
    ]


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
    return common.redact(lines[0])[:160] if lines else ""


def check(root: Path, *, runner: Runner | None = None, timeout: float = 60.0) -> AwsPreflight:
    """Run the fixed operation and classify the outcome. Never raises for AWS/CLI problems."""
    state = common.load_state(root)
    policies = common.load_policies(root)
    expected = common.load_environment(root, state.get("environment", "dev"))["account_id"]
    try:
        code, stdout, stderr = (runner or _subprocess_runner)(argv(policies), timeout)
    except FileNotFoundError:
        return AwsPreflight("unavailable", "CLI de AWS no encontrado en PATH")
    except subprocess.TimeoutExpired:
        return AwsPreflight("unavailable", f"sts get-caller-identity excedio {timeout:.0f}s")
    except OSError as error:
        return AwsPreflight(
            "unavailable", f"no se pudo ejecutar el CLI de AWS ({error.__class__.__name__})"
        )
    if code != 0:
        lowered = stderr.lower()
        status = (
            "expired" if any(marker in lowered for marker in SESSION_MARKERS) else "unavailable"
        )
        return AwsPreflight(status, _first_line(stderr) or f"exit code {code}")
    try:
        account = json.loads(stdout).get("Account")
    except (ValueError, AttributeError):
        return AwsPreflight("unavailable", "respuesta de sts ilegible")
    if account != expected:
        return AwsPreflight("wrong_account", "la cuenta de la sesion no es la del entorno")
    return AwsPreflight("ok")
