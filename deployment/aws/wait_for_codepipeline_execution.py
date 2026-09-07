"""Wait for one CodePipeline execution with bounded eventual-consistency retries."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CommandResult]
Sleeper = Callable[[float], None]


class PipelineObservationError(RuntimeError):
    """Raised when a pipeline execution cannot be observed safely."""


def _run(command: Sequence[str]) -> CommandResult:
    result = subprocess.run(command, capture_output=True, check=False, text=True)  # noqa: S603
    return CommandResult(result.returncode, result.stdout, result.stderr)


def wait_for_execution(
    *,
    pipeline_name: str,
    execution_id: str,
    region: str,
    max_attempts: int = 90,
    poll_seconds: float = 20,
    visibility_attempts: int = 6,
    visibility_backoff_seconds: float = 5,
    runner: Runner = _run,
    sleeper: Sleeper = time.sleep,
) -> str:
    """Return ``Succeeded`` or fail closed for terminal/error/timeout states."""
    if max_attempts < 1 or visibility_attempts < 0:
        raise ValueError("Polling limits must be positive")

    not_found_count = 0
    command = [
        "aws",
        "codepipeline",
        "get-pipeline-execution",
        "--region",
        region,
        "--pipeline-name",
        pipeline_name,
        "--pipeline-execution-id",
        execution_id,
        "--query",
        "pipelineExecution.status",
        "--output",
        "text",
    ]

    for attempt in range(1, max_attempts + 1):
        result = runner(command)
        if result.returncode != 0:
            diagnostic = result.stderr.strip() or result.stdout.strip() or "unknown AWS CLI error"
            if "PipelineExecutionNotFoundException" not in diagnostic:
                raise PipelineObservationError(
                    f"Unable to observe CodePipeline execution {execution_id}: {diagnostic}"
                )
            not_found_count += 1
            if not_found_count > visibility_attempts:
                raise PipelineObservationError(
                    "CodePipeline execution did not become visible within the bounded "
                    f"retry window: {execution_id}; last error: {diagnostic}"
                )
            delay = visibility_backoff_seconds * not_found_count
            print(
                f"CodePipeline execution is not visible yet "
                f"({not_found_count}/{visibility_attempts}); retrying in {delay:g}s."
            )
            sleeper(delay)
            continue

        status = result.stdout.strip()
        print(f"CodePipeline execution status: {status}")
        if status == "Succeeded":
            return status
        if status in {"Failed", "Stopped", "Superseded"}:
            raise PipelineObservationError(
                f"CodePipeline execution {execution_id} ended with status {status}"
            )
        if status not in {"InProgress", "Stopping"}:
            raise PipelineObservationError(f"Unexpected CodePipeline status: {status!r}")
        if attempt < max_attempts:
            sleeper(poll_seconds)

    raise PipelineObservationError(
        f"Timed out after {max_attempts} observations waiting for CodePipeline "
        f"execution {execution_id}; last status was non-terminal"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-name", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--max-attempts", type=int, default=90)
    parser.add_argument("--poll-seconds", type=float, default=20)
    parser.add_argument("--visibility-attempts", type=int, default=6)
    parser.add_argument("--visibility-backoff-seconds", type=float, default=5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        wait_for_execution(
            pipeline_name=args.pipeline_name,
            execution_id=args.execution_id,
            region=args.region,
            max_attempts=args.max_attempts,
            poll_seconds=args.poll_seconds,
            visibility_attempts=args.visibility_attempts,
            visibility_backoff_seconds=args.visibility_backoff_seconds,
        )
    except (PipelineObservationError, ValueError) as error:
        print(f"Pipeline observation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
