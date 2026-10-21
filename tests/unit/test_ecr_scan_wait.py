"""Tests for the ECR scan wait gate (``scripts/release/wait_for_ecr_scan.py``).

The script invokes the AWS CLI through an injectable ``runner``; these tests exercise
every path with a simulated AWS CLI (no AWS, no network): COMPLETE sin hallazgos,
IN_PROGRESS que termina, IN_PROGRESS que no termina (timeout), FAILED/UNSUPPORTED_IMAGE
y hallazgos HIGH/CRITICAL.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from scripts.release.wait_for_ecr_scan import (
    CommandResult,
    EcrScanError,
    findings_message,
    main,
    terminal_message,
    timeout_message,
    wait_for_scan,
)

DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
REGION = "us-east-2"
REPOSITORY = "tpi-dev-app"
TAG = "0123456789abcdef0123456789abcdef01234567"


def _ok(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(0, stdout, stderr)


def _error(stderr: str) -> CommandResult:
    return CommandResult(254, "", stderr)


def _runner(*results: CommandResult):
    calls: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> CommandResult:
        calls.append(command)
        if len(calls) > len(results):
            raise AssertionError("runner invocado mas veces que resultados provistos")
        return results[len(calls) - 1]

    return run, calls


def _args(**overrides) -> dict:
    args = {
        "region": REGION,
        "repository": REPOSITORY,
        "image_tag": TAG,
        "digest": DIGEST,
        "timeout_minutes": 20,
        "poll_seconds": 15,
    }
    args.update(overrides)
    return args


def test_complete_sin_hallazgos_aprueba() -> None:
    run, calls = _runner(_ok("COMPLETE"), _ok("0"), _ok("0"))
    sleeps: list[float] = []

    wait_for_scan(**_args(), runner=run, sleeper=sleeps.append)

    assert len(calls) == 3
    assert sleeps == []


def test_in_progress_que_termina_aprueba() -> None:
    run, calls = _runner(_ok("IN_PROGRESS"), _ok("COMPLETE"), _ok("0"), _ok("0"))
    sleeps: list[float] = []

    wait_for_scan(**_args(), runner=run, sleeper=sleeps.append)

    assert len(calls) == 4
    assert sleeps == [15]


def test_in_progress_que_no_termina_falla_con_mensaje_a() -> None:
    run, calls = _runner(_ok("IN_PROGRESS"), _ok("IN_PROGRESS"), _ok("IN_PROGRESS"))
    sleeps: list[float] = []

    with pytest.raises(EcrScanError) as exc:
        wait_for_scan(
            **_args(timeout_minutes=1, poll_seconds=20), runner=run, sleeper=sleeps.append
        )

    assert len(calls) == 3
    assert sleeps == [20, 20]
    message = str(exc.value)
    assert "no termino en el plazo de 1 minutos" in message
    assert "NO hay hallazgos verificados" in message
    assert DIGEST in message
    assert "Recuperacion" in message


def test_scan_terminado_en_failed_falla_con_mensaje_b() -> None:
    run, calls = _runner(_ok("FAILED"))

    with pytest.raises(EcrScanError) as exc:
        wait_for_scan(**_args(), runner=run)

    assert len(calls) == 1
    message = str(exc.value)
    assert "termino en FAILED" in message
    assert "la imagen no pudo ser verificada" in message
    assert DIGEST in message


def test_scan_terminado_en_unsupported_image_falla_con_mensaje_b() -> None:
    run, calls = _runner(_ok("UNSUPPORTED_IMAGE"))

    with pytest.raises(EcrScanError) as exc:
        wait_for_scan(**_args(), runner=run)

    assert len(calls) == 1
    assert "termino en UNSUPPORTED_IMAGE" in str(exc.value)


def test_hallazgos_high_o_critical_fallan_con_mensaje_c() -> None:
    detail = '[{"severity": "CRITICAL", "name": "CVE-0000-0000"}]'
    run, calls = _runner(_ok("COMPLETE"), _ok("1"), _ok("2"), _ok(detail))

    with pytest.raises(EcrScanError) as exc:
        wait_for_scan(**_args(), runner=run)

    assert len(calls) == 4
    message = str(exc.value)
    assert "Hallazgos HIGH o CRITICAL" in message
    assert "CRITICAL=1 HIGH=2" in message
    assert detail in message
    assert DIGEST in message


def test_estado_desconocido_falla_cerrado() -> None:
    run, calls = _runner(_ok("PENDING"))

    with pytest.raises(EcrScanError, match="inesperado"):
        wait_for_scan(**_args(), runner=run)

    assert len(calls) == 1


def test_error_transitorio_del_status_se_sigue_sondeando() -> None:
    run, calls = _runner(
        _error("ScanNotFoundException: not visible yet"),
        _ok("COMPLETE"),
        _ok("0"),
        _ok("0"),
    )
    sleeps: list[float] = []

    wait_for_scan(**_args(), runner=run, sleeper=sleeps.append)

    assert len(calls) == 4
    assert sleeps == [15]


def test_parametros_no_positivos_se_rechazan() -> None:
    with pytest.raises(ValueError):
        wait_for_scan(**_args(timeout_minutes=0), runner=_runner()[0])


def test_los_tres_mensajes_son_distintos_y_con_sus_marcas() -> None:
    a = timeout_message(REPOSITORY, DIGEST, 20)
    b = terminal_message(REPOSITORY, DIGEST, "FAILED")
    c = findings_message(REPOSITORY, DIGEST, "3", "4", "[]")

    assert "NO hay hallazgos verificados" in a
    assert "termino en FAILED" in b
    assert "Hallazgos HIGH o CRITICAL" in c
    assert "CRITICAL=3 HIGH=4" in c
    assert len({a, b, c}) == 3


def test_main_rechaza_digest_invalido() -> None:
    code = main(
        [
            "--region",
            REGION,
            "--repository",
            REPOSITORY,
            "--image-tag",
            TAG,
            "--digest",
            "not-a-digest",
        ]
    )

    assert code == 1
