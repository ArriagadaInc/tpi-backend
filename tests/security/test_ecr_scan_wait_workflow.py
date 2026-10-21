"""Guard the ECR scan wait gate declared in ``publish-dev-ecr-images.yml``.

El workflow de publicacion debe esperar lo suficiente (>= 20 minutos) sondeando lo bastante
rapido (<= 30 s) a que el escaneo de ECR termine, y debe mantener el gate fail-closed con
tres mensajes de fallo distinguibles. Estas pruebas leen el workflow YAML (sin AWS) y la
documentacion de recuperacion, de modo que una regresion rompa el CI en lugar de pasar
silenciosamente.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-dev-ecr-images.yml"
SCRIPT = ROOT / "scripts" / "release" / "wait_for_ecr_scan.py"
RUNBOOK = ROOT / "docs" / "DEV_EB_DEPLOYMENT_RUNBOOK.md"
CHANGELOG = ROOT / "CHANGELOG.md"
BITACORA = ROOT / "docs" / "BITACORA.md"


def _scan_steps() -> list[dict]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: list[dict] = []
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if "wait_for_ecr_scan.py" in str(step.get("run", "")):
                steps.append(step)
    return steps


def _scan_step() -> dict:
    steps = _scan_steps()
    assert (
        len(steps) == 1
    ), f"se esperaba exactamente un paso que invoque wait_for_ecr_scan.py, hay {len(steps)}"
    return steps[0]


def test_plazo_e_intervalo_son_constantes_legibles_del_workflow() -> None:
    env = _scan_step().get("env", {})
    timeout_minutes = int(env["SCAN_TIMEOUT_MINUTES"])
    poll_seconds = int(env["SCAN_POLL_SECONDS"])

    assert timeout_minutes >= 20
    assert poll_seconds <= 30


def test_el_paso_espera_el_escaneo_de_ambas_imagenes_con_sus_digests() -> None:
    run = str(_scan_step()["run"])

    assert run.count("scripts/release/wait_for_ecr_scan.py") == 2
    assert "$ECR_APP_REPOSITORY" in run
    assert "$ECR_CADDY_REPOSITORY" in run
    assert "$APP_DIGEST" in run
    assert "$CADDY_DIGEST" in run


def test_los_tres_mensajes_de_fallo_estan_en_el_script_referido() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "NO hay hallazgos verificados" in source
    assert "termino en" in source
    assert "Hallazgos HIGH o CRITICAL" in source
    assert "Recuperacion" in source


def test_la_recuperacion_esta_documentada() -> None:
    for doc in (RUNBOOK, CHANGELOG, BITACORA):
        text = doc.read_text(encoding="utf-8").lower()
        assert "relanzar el workflow con el mismo sha" in text, doc.name
        assert "borrar las dos imagenes" in text, doc.name
