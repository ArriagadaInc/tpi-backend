"""Pruebas de la auditoría de armonía visual del CSS (solo lectura)."""

from __future__ import annotations

from pathlib import Path

from scripts.ui_css_audit import CSS_POR_DEFECTO, auditar, main

CSS_EJEMPLO = """
:root { color-scheme: light; --bg: #f8fafc; --accent: #0d9488; font-family: Inter, sans-serif; }
[data-theme="dark"] { --bg: #0b1220; --accent: #2dd4bf; }
.card { background: var(--bg); border-radius: 16px; padding: 12px 16px; box-shadow: 0 1px 2px rgba(0,0,0,.1); }
.card h2 { font-size: 0.82rem; font-weight: 800; color: #334155; }
.pill { border-radius: 999px; font-size: 0.84rem; color: #334155; }
[data-theme="dark"] .card { background: #111827; }
/* un comentario con #ffffff que no cuenta */
@media (max-width: 900px) { .card { padding: 8px; } }
@media (max-width: 640px) { .pill { font-size: 0.82rem; } }
"""


def test_tokens_blocks_are_not_counted_as_loose_values() -> None:
    metricas = auditar(CSS_EJEMPLO)
    assert metricas["tokens_en_root"] == 2
    # Fuera de los bloques de tokens: rgba, #334155 (x2) y #111827.
    assert metricas["colores_sueltos_distintos"] == 3
    assert metricas["colores_sueltos_usos"] == 4


def test_it_counts_scales_breakpoints_and_dark_component_rules() -> None:
    metricas = auditar(CSS_EJEMPLO)
    assert metricas["tamanos_de_letra_distintos"] == 2
    assert metricas["radios_distintos"] == 2
    assert metricas["sombras_distintas"] == 1
    assert metricas["pesos_de_letra"] == {"800": 1}
    assert metricas["cortes_responsive"] == [640, 900]
    assert metricas["reglas_de_tema_oscuro_por_componente"] == 1
    assert metricas["espaciados_distintos"] == 2


def test_inline_styles_in_templates_are_counted() -> None:
    plantillas = {"a.html": '<div style="color:red"></div><p style="x"></p>', "b.html": "<p></p>"}
    assert auditar(CSS_EJEMPLO, plantillas)["estilos_en_linea_en_plantillas"] == 2


def test_the_real_stylesheet_can_be_audited_and_the_cli_prints_a_table(
    capsys: object, tmp_path: Path
) -> None:
    assert CSS_POR_DEFECTO.is_file()
    assert main([]) == 0
    assert main(["--css", str(tmp_path / "no_existe.css")]) == 2
