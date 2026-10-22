"""Auditoría de armonía visual de la hoja de estilos del CRM (solo lectura).

Mide cuánto del CSS está sujeto a tokens y cuánto son valores sueltos: colores fuera de los bloques de
variables, tamaños de letra, radios, sombras, espaciados, cortes responsive y reglas de tema oscuro por
componente. Sirve para fijar la línea base de ``docs/UI_DESIGN_SYSTEM.md`` y para comprobar, tarea a
tarea, que el CRM converge a sus tokens.

Uso::

    python scripts/ui_css_audit.py            # tabla legible
    python scripts/ui_css_audit.py --json     # para comparar antes y después

No modifica ningún archivo ni se conecta a nada.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CSS_POR_DEFECTO = Path(__file__).resolve().parents[1] / "app" / "web" / "static" / "css" / "app.css"
PLANTILLAS = Path(__file__).resolve().parents[1] / "app" / "web" / "templates"

_COMENTARIOS = re.compile(r"/\*.*?\*/", re.S)
_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
_DECLARACION = re.compile(r"([a-z-]+)\s*:\s*([^;{}]+);")


def _hojas(css: str) -> list[tuple[str, str]]:
    """Reglas ``(selector, cuerpo)`` de las hojas hoja, aplanando ``@media`` y ``@keyframes``."""
    texto = _COMENTARIOS.sub("", css)
    reglas: list[tuple[str, str]] = []

    def recorrer(fragmento: str) -> None:
        indice = 0
        while True:
            abre = fragmento.find("{", indice)
            if abre == -1:
                return
            selector = fragmento[indice:abre].strip()
            nivel, cierre = 1, abre + 1
            while cierre < len(fragmento) and nivel:
                nivel += {"{": 1, "}": -1}.get(fragmento[cierre], 0)
                cierre += 1
            cuerpo = fragmento[abre + 1 : cierre - 1]
            if selector.startswith("@") and "{" in cuerpo:
                recorrer(cuerpo)
            else:
                reglas.append((selector.split("}")[-1].strip(), cuerpo))
            indice = cierre

    recorrer(texto)
    return reglas


def _es_bloque_de_tokens(selector: str, cuerpo: str) -> bool:
    """Un bloque de tokens es el de ``:root`` o el del tema y declara variables (``--nombre``)."""
    base = selector.replace("html", "").replace(" ", "")
    es_raiz = base in (":root", '[data-theme="dark"]', '[data-theme="light"]', "[data-theme=dark]")
    return es_raiz and any(n.startswith("--") for n, _ in _DECLARACION.findall(cuerpo))


def _distintos(reglas: list[tuple[str, str]], propiedad: str) -> Counter[str]:
    conteo: Counter[str] = Counter()
    for _selector, cuerpo in reglas:
        for nombre, valor in _DECLARACION.findall(cuerpo):
            if nombre == propiedad:
                conteo[" ".join(valor.split()).lower()] += 1
    return conteo


def auditar(css: str, plantillas: dict[str, str] | None = None) -> dict[str, Any]:
    """Métricas de armonía de ``css`` (y de los estilos en línea de las plantillas, si se dan)."""
    reglas = _hojas(css)
    tokens: dict[str, str] = {}
    sueltos: Counter[str] = Counter()
    for selector, cuerpo in reglas:
        if _es_bloque_de_tokens(selector, cuerpo):
            if selector.replace("html", "").replace(" ", "") == ":root":
                tokens.update(
                    {n: v.strip() for n, v in _DECLARACION.findall(cuerpo) if n.startswith("--")}
                )
            continue
        for _nombre, valor in _DECLARACION.findall(cuerpo):
            if not _nombre.startswith("--"):
                for color in _COLOR.findall(valor):
                    sueltos[color.replace(" ", "").lower()] += 1
    espaciado: Counter[str] = Counter()
    for propiedad in ("padding", "margin", "gap", "row-gap", "column-gap"):
        espaciado.update(_distintos(reglas, propiedad))
    en_linea = sum(t.count('style="') for t in (plantillas or {}).values())
    return {
        "reglas": len(reglas),
        "tokens_en_root": len(tokens),
        "colores_sueltos_distintos": len(sueltos),
        "colores_sueltos_usos": sum(sueltos.values()),
        "tamanos_de_letra_distintos": len(_distintos(reglas, "font-size")),
        "pesos_de_letra": dict(_distintos(reglas, "font-weight")),
        "radios_distintos": len(_distintos(reglas, "border-radius")),
        "sombras_distintas": len(_distintos(reglas, "box-shadow")),
        "espaciados_distintos": len(espaciado),
        "cortes_responsive": sorted(
            {int(ancho) for ancho in re.findall(r"@media[^{]*max-width:\s*(\d+)px", css)}
        ),
        "reglas_de_tema_oscuro_por_componente": sum(
            1
            for selector, cuerpo in reglas
            if "data-theme" in selector and not _es_bloque_de_tokens(selector, cuerpo)
        ),
        "important": css.count("!important"),
        "estilos_en_linea_en_plantillas": en_linea,
    }


def _leer_plantillas(carpeta: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(carpeta.glob("*.html"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audita la armonía visual del CSS del CRM.")
    parser.add_argument("--css", type=Path, default=CSS_POR_DEFECTO, help="Ruta de app.css.")
    parser.add_argument("--json", action="store_true", help="Imprime las métricas como JSON.")
    args = parser.parse_args(argv)
    if not args.css.is_file():
        print(f"No existe el archivo: {args.css}", file=sys.stderr)
        return 2
    plantillas = _leer_plantillas(PLANTILLAS) if PLANTILLAS.is_dir() else {}
    metricas = auditar(args.css.read_text(encoding="utf-8"), plantillas)
    if args.json:
        print(json.dumps(metricas, ensure_ascii=False, indent=2))
    else:
        for clave, valor in metricas.items():
            print(f"{clave.replace('_', ' '):<42} {valor}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
