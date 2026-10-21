"""Wait for one ECR image scan to finish and fail closed on HIGH/CRITICAL findings.

El workflow de publicación no debe fallar solo porque el escaneo de ECR tarde: este
script sondea ``describe-image-scan-findings`` hasta ``timeout_minutes`` (cada
``poll_seconds``) y mantiene el gate fail-closed:

* ``COMPLETE`` con ``CRITICAL=0`` y ``HIGH=0`` -> éxito;
* ``COMPLETE`` con hallazgos HIGH/CRITICAL -> falla con el detalle de los hallazgos;
* ``FAILED`` o ``UNSUPPORTED_IMAGE`` -> falla con el estado terminal;
* sigue ``IN_PROGRESS`` (o aún no visible) al vencer el plazo -> falla aclarando que NO
  hay hallazgos verificados y apuntando al procedimiento de recuperación.

La AWS CLI se invoca a través de un ``runner`` inyectable para que las pruebas ejerciten
todos los caminos sin AWS. Las constantes de plazo/intervalo viven en el workflow que lo
invoca (``SCAN_TIMEOUT_MINUTES`` y ``SCAN_POLL_SECONDS``) y aquí solo son los valores por
defecto.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

SCAN_TIMEOUT_MINUTES = 20
SCAN_POLL_SECONDS = 15

RECOVERY_PROCEDURE = (
    "Recuperacion: revisar el estado del escaneo de ambos digests "
    "(aws ecr describe-image-scan-findings), borrar las dos imagenes del release "
    "(los tags son inmutables, lo hace el humano) y relanzar el workflow con el mismo SHA."
)

_TERMINAL_BAD_STATUSES = frozenset({"FAILED", "UNSUPPORTED_IMAGE"})
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

_STATUS_QUERY = "imageScanStatus.status"
_CRITICAL_QUERY = "imageScanFindings.findingSeverityCounts.CRITICAL || `0`"
_HIGH_QUERY = "imageScanFindings.findingSeverityCounts.HIGH || `0`"
_FINDINGS_QUERY = (
    "imageScanFindings.findings[?severity==`CRITICAL` || severity==`HIGH`]."
    "{severity:severity,name:name,description:description,uri:uri,attributes:attributes}"
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CommandResult]
Sleeper = Callable[[float], None]


class EcrScanError(RuntimeError):
    """Raised when the scan cannot be verified with zero HIGH/CRITICAL findings."""


def timeout_message(repository: str, digest: str, timeout_minutes: int) -> str:
    """Mensaje (a): el escaneo no terminó en el plazo y NO hay hallazgos verificados."""
    return (
        f"El escaneo de ECR no termino en el plazo de {timeout_minutes} minutos para "
        f"{repository} (digest {digest}): NO hay hallazgos verificados; un escaneo "
        f"incompleto no demuestra que la imagen sea segura ni insegura. {RECOVERY_PROCEDURE}"
    )


def terminal_message(repository: str, digest: str, status: str) -> str:
    """Mensaje (b): el escaneo terminó en FAILED o UNSUPPORTED_IMAGE."""
    return (
        f"El escaneo de ECR termino en {status} para {repository} (digest {digest}): "
        f"la imagen no pudo ser verificada. {RECOVERY_PROCEDURE}"
    )


def findings_message(repository: str, digest: str, critical: str, high: str, detail: str) -> str:
    """Mensaje (c): hay hallazgos HIGH o CRITICAL, con el detalle."""
    return (
        f"Hallazgos HIGH o CRITICAL en {repository} (digest {digest}): "
        f"CRITICAL={critical} HIGH={high}. Detalle: {detail}"
    )


def _run(command: Sequence[str]) -> CommandResult:
    result = subprocess.run(command, capture_output=True, check=False, text=True)  # noqa: S603
    return CommandResult(result.returncode, result.stdout, result.stderr)


def _command(
    region: str, repository: str, image_tag: str, query: str, output_format: str = "text"
) -> list[str]:
    return [
        "aws",
        "ecr",
        "describe-image-scan-findings",
        "--region",
        region,
        "--repository-name",
        repository,
        "--image-id",
        f"imageTag={image_tag}",
        "--query",
        query,
        "--output",
        output_format,
    ]


def _describe_status(region: str, repository: str, image_tag: str, runner: Runner) -> str:
    result = runner(_command(region, repository, image_tag, _STATUS_QUERY))
    if result.returncode != 0:
        # El scan-on-push tiene consistencia eventual: un error transitorio (p. ej.
        # ScanNotFoundException) se trata como "todavía no listo" para seguir sondeando;
        # el plazo acotado mantiene el gate fail-closed.
        return ""
    return result.stdout.strip()


def _describe_required(
    region: str,
    repository: str,
    image_tag: str,
    query: str,
    runner: Runner,
    output_format: str = "text",
) -> str:
    result = runner(_command(region, repository, image_tag, query, output_format))
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or result.stdout.strip() or "unknown AWS CLI error"
        raise EcrScanError(f"No se pudo consultar el escaneo de {repository}: {diagnostic}")
    return result.stdout.strip()


def wait_for_scan(
    *,
    region: str,
    repository: str,
    image_tag: str,
    digest: str,
    timeout_minutes: int = SCAN_TIMEOUT_MINUTES,
    poll_seconds: int = SCAN_POLL_SECONDS,
    runner: Runner = _run,
    sleeper: Sleeper = time.sleep,
) -> None:
    """Wait until the scan is COMPLETE with zero HIGH/CRITICAL findings, else raise."""
    if timeout_minutes < 1 or poll_seconds < 1:
        raise ValueError("timeout_minutes y poll_seconds deben ser positivos")

    max_attempts = math.ceil(timeout_minutes * 60 / poll_seconds)
    for attempt in range(1, max_attempts + 1):
        status = _describe_status(region, repository, image_tag, runner)

        if status == "COMPLETE":
            critical = _describe_required(region, repository, image_tag, _CRITICAL_QUERY, runner)
            high = _describe_required(region, repository, image_tag, _HIGH_QUERY, runner)
            if critical != "0" or high != "0":
                detail = _describe_required(
                    region, repository, image_tag, _FINDINGS_QUERY, runner, output_format="json"
                )
                raise EcrScanError(findings_message(repository, digest, critical, high, detail))
            print(f"{repository}: CRITICAL={critical} HIGH={high}")
            return

        if status in _TERMINAL_BAD_STATUSES:
            raise EcrScanError(terminal_message(repository, digest, status))

        if status not in ("", "IN_PROGRESS"):
            raise EcrScanError(
                f"Estado de escaneo inesperado para {repository} (digest {digest}): {status!r}"
            )

        if attempt < max_attempts:
            sleeper(poll_seconds)

    raise EcrScanError(timeout_message(repository, digest, timeout_minutes))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--timeout-minutes", type=int, default=SCAN_TIMEOUT_MINUTES)
    parser.add_argument("--poll-seconds", type=int, default=SCAN_POLL_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not _DIGEST_PATTERN.fullmatch(args.digest):
        print(f"digest invalido: {args.digest!r}", file=sys.stderr)
        return 1
    try:
        wait_for_scan(
            region=args.region,
            repository=args.repository,
            image_tag=args.image_tag,
            digest=args.digest,
            timeout_minutes=args.timeout_minutes,
            poll_seconds=args.poll_seconds,
        )
    except (EcrScanError, ValueError) as error:
        print(f"Gate de escaneo ECR fallido: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
