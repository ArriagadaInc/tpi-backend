"""Tests for bounded CodePipeline execution observation."""

from collections.abc import Iterator, Sequence

import pytest

from deployment.aws.wait_for_codepipeline_execution import (
    CommandResult,
    PipelineObservationError,
    wait_for_execution,
)


def _runner(results: list[CommandResult]):
    responses: Iterator[CommandResult] = iter(results)

    def run(_command: Sequence[str]) -> CommandResult:
        return next(responses)

    return run


def test_retries_initial_not_found_then_observes_success() -> None:
    sleeps: list[float] = []
    result = wait_for_execution(
        pipeline_name="pipeline",
        execution_id="execution",
        region="us-east-2",
        runner=_runner(
            [
                CommandResult(254, "", "PipelineExecutionNotFoundException: not visible"),
                CommandResult(254, "", "PipelineExecutionNotFoundException: not visible"),
                CommandResult(0, "InProgress\n", ""),
                CommandResult(0, "Succeeded\n", ""),
            ]
        ),
        sleeper=sleeps.append,
        poll_seconds=20,
        visibility_backoff_seconds=5,
    )

    assert result == "Succeeded"
    assert sleeps == [5, 10, 20]


def test_times_out_with_execution_diagnostic() -> None:
    with pytest.raises(PipelineObservationError, match="execution-id.*last status"):
        wait_for_execution(
            pipeline_name="pipeline",
            execution_id="execution-id",
            region="us-east-2",
            max_attempts=2,
            runner=_runner([CommandResult(0, "InProgress", "")] * 2),
            sleeper=lambda _seconds: None,
        )


def test_fails_closed_on_non_transient_aws_error() -> None:
    with pytest.raises(PipelineObservationError, match="AccessDeniedException"):
        wait_for_execution(
            pipeline_name="pipeline",
            execution_id="execution",
            region="us-east-2",
            runner=_runner([CommandResult(254, "", "AccessDeniedException: denied")]),
            sleeper=lambda _seconds: None,
        )


def test_fails_when_visibility_retry_window_is_exhausted() -> None:
    with pytest.raises(PipelineObservationError, match="bounded retry window"):
        wait_for_execution(
            pipeline_name="pipeline",
            execution_id="execution",
            region="us-east-2",
            visibility_attempts=1,
            runner=_runner(
                [
                    CommandResult(254, "", "PipelineExecutionNotFoundException: pending"),
                    CommandResult(254, "", "PipelineExecutionNotFoundException: pending"),
                ]
            ),
            sleeper=lambda _seconds: None,
        )


def test_fails_immediately_when_visible_execution_disappears() -> None:
    sleeps: list[float] = []
    with pytest.raises(PipelineObservationError, match="disappeared after.*observed"):
        wait_for_execution(
            pipeline_name="pipeline",
            execution_id="execution",
            region="us-east-2",
            runner=_runner(
                [
                    CommandResult(254, "", "PipelineExecutionNotFoundException: pending"),
                    CommandResult(0, "InProgress", ""),
                    CommandResult(254, "", "PipelineExecutionNotFoundException: missing"),
                ]
            ),
            sleeper=sleeps.append,
            poll_seconds=20,
        )

    assert sleeps == [5, 20]


@pytest.mark.parametrize("status", ["Cancelled", "Failed", "Stopped", "Superseded"])
def test_fails_closed_on_every_negative_terminal_status(status: str) -> None:
    with pytest.raises(PipelineObservationError, match=rf"ended with status {status}"):
        wait_for_execution(
            pipeline_name="pipeline",
            execution_id="execution",
            region="us-east-2",
            runner=_runner([CommandResult(0, status, "")]),
            sleeper=lambda _seconds: None,
        )
