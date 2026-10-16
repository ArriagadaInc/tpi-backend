"""Servicio de aplicación del simulador de renta vitalicia (SIM-RV-V1).

Orquesta el motor puro (:mod:`app.simulador_pension`), la generación del PDF efímero y el
evento funcional de auditoría. No persiste entradas ni resultados de la simulación.
"""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.auth.models import AuthenticatedUser, is_superuser
from app.services.simulador_auditoria import record_simulacion_event
from app.simulador_pension import (
    Hijo,
    NoValidadoError,
    Persona,
    Resultado,
    simular,
)
from app.simulador_pension import __version__ as MODELO_VERSION  # noqa: N812
from app.simulador_pension.api import VENTANA_VALIDADA
from app.simulador_pension.mortalidad import edad_en_meses

CRM_TZ = ZoneInfo("America/Santiago")

# AC-6: ventana validada (constante única documentada). NO extender sin campaña canaria (AC-18).
VENTANA_ADVERTENCIA_DIAS = 90

# Rangos validados por edad (fuente de la ingeniería inversa; ver docs/SIM_RV_V1_PENDIENTES.md §1).
EDAD_CAUSANTE_INDIVIDUAL = (60, 100)
EDAD_CAUSANTE_CON_CONYUGE = (60, 92)
EDAD_CAUSANTE_CON_HIJOS = (62, 92)
EDAD_CAUSANTE_RENTA_TEMPORAL = (59, 88)
EDAD_CONYUGE = (46, 96)
EDAD_HIJO = (0, 41)

_LOGO_DARK_PATH = (
    Path(__file__).resolve().parent.parent / "web" / "static" / "img" / "official-logo-on-dark.png"
)

# Carta apaisada (792 × 612 pt) con márgenes de 20 pt (ver docs/specs/SIM_FICHA_PDF_SPEC.md §1).
_PAGE_W, _PAGE_H = landscape(letter)
_MARGEN = 20

# Paleta de la marca TPI (docs/specs/SIM_FICHA_PDF_SPEC.md §2).
_NAVY = colors.HexColor("#0f243e")
_NAVY_LIGHT = colors.HexColor("#b8cce4")
_HIGHLIGHT = colors.HexColor("#b7dee8")
_BODY = colors.HexColor("#1d1b10")

# Intercambio de separadores de miles/decimales al formato es-CL (punto de miles, coma decimal).
_SWAP_MILES = str.maketrans({",": ".", ".": ","})


class SimulacionInvalidaError(ValueError):
    """Validación de negocio de la simulación con mensaje claro en español (sin traceback)."""


@dataclass(frozen=True)
class Escenario:
    """Clasificación del escenario para el PDF y la auditoría."""

    tipo: str
    descripcion: str


def _edad_anios(nacimiento: date, referencia: date) -> int:
    return edad_en_meses(nacimiento, referencia) // 12


def clasificar_ventana(fecha: date) -> Literal["ok", "advertencia", "bloqueado"]:
    """Estado de la ventana validada respecto a una fecha de simulación.

    Dentro de la ventana se genera normal; hasta ``VENTANA_ADVERTENCIA_DIAS`` después del fin se
    genera con advertencia; más allá se bloquea (fail-closed, AC-6).
    """
    inicio, fin = VENTANA_VALIDADA
    if inicio <= fecha <= fin:
        return "ok"
    if fecha <= fin + timedelta(days=VENTANA_ADVERTENCIA_DIAS):
        return "advertencia"
    return "bloqueado"


def clasificar_escenario(
    *,
    anios_diferidos: int,
    tiene_conyuge: bool,
    n_hijos: int,
    con_garantia_aumento: bool,
) -> Escenario:
    """Devuelve el tipo (clave máquina) y la descripción en español del escenario."""
    if anios_diferidos > 0:
        return Escenario(
            tipo="renta_temporal_rvd",
            descripcion="Renta temporal + renta vitalicia diferida (causante individual)",
        )
    partes: list[str] = []
    if tiene_conyuge:
        partes.append("con cónyuge")
    if n_hijos:
        partes.append(f"con {n_hijos} hijo{'s' if n_hijos != 1 else ''}")
    if con_garantia_aumento:
        partes.append("con garantía/aumento temporal")
    if not partes:
        return Escenario(
            tipo="renta_inmediata_causante", descripcion="Renta vitalicia inmediata (causante)"
        )
    return Escenario(
        tipo="renta_inmediata_familia",
        descripcion=f"Renta vitalicia inmediata {'; '.join(partes)}",
    )


def codigo_verificacion(
    *,
    fecha_simulacion: date,
    saldo_uf: float,
    tasa_venta_pct: float,
    causante: Persona,
    conyuge: Persona | None,
    hijos: tuple[Hijo, ...],
    meses_garantizados: int,
    meses_aumento_temporal: int,
    porcentaje_aumento_temporal: float,
    anios_diferidos: int,
    porcentaje_rvd: float,
) -> str:
    """Código de verificación determinístico (sha256, 12 hex) de las entradas canónicas (AC-12)."""
    hijos_canon = ";".join(
        f"{h.sexo},{h.nacimiento.isoformat()},{int(h.comun)},{h.invalidez}"
        for h in sorted(hijos, key=lambda h: (h.nacimiento.isoformat(), h.sexo))
    )
    canonico = "|".join(
        [
            MODELO_VERSION,
            fecha_simulacion.isoformat(),
            repr(round(float(saldo_uf), 6)),
            repr(round(float(tasa_venta_pct), 6)),
            causante.sexo,
            causante.nacimiento.isoformat(),
            f"{conyuge.sexo},{conyuge.nacimiento.isoformat()}" if conyuge else "-",
            hijos_canon or "-",
            str(int(meses_garantizados)),
            str(int(meses_aumento_temporal)),
            repr(round(float(porcentaje_aumento_temporal), 6)),
            str(int(anios_diferidos)),
            repr(round(float(porcentaje_rvd), 6)),
        ]
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:12]


def validar_edades(
    *,
    fecha_simulacion: date,
    causante: Persona,
    conyuge: Persona | None,
    hijos: tuple[Hijo, ...],
    anios_diferidos: int,
) -> None:
    """Rechaza (422) edades fuera de los rangos validados por escenario (AC-4)."""
    edad = _edad_anios(causante.nacimiento, fecha_simulacion)
    if anios_diferidos > 0:
        minimo, maximo = EDAD_CAUSANTE_RENTA_TEMPORAL
    elif conyuge is not None:
        minimo, maximo = EDAD_CAUSANTE_CON_CONYUGE
    elif hijos:
        minimo, maximo = EDAD_CAUSANTE_CON_HIJOS
    else:
        minimo, maximo = EDAD_CAUSANTE_INDIVIDUAL
    if not minimo <= edad <= maximo:
        raise SimulacionInvalidaError(
            f"La edad del causante ({edad} años) está fuera del rango validado ({minimo}–{maximo})."
        )
    if conyuge is not None:
        edad_conyuge = _edad_anios(conyuge.nacimiento, fecha_simulacion)
        if not EDAD_CONYUGE[0] <= edad_conyuge <= EDAD_CONYUGE[1]:
            raise SimulacionInvalidaError(
                f"La edad del cónyuge ({edad_conyuge} años) está fuera del rango validado "
                f"({EDAD_CONYUGE[0]}–{EDAD_CONYUGE[1]})."
            )
    for i, h in enumerate(hijos, 1):
        edad_hijo = _edad_anios(h.nacimiento, fecha_simulacion)
        if not EDAD_HIJO[0] <= edad_hijo <= EDAD_HIJO[1]:
            raise SimulacionInvalidaError(
                f"La edad del hijo {i} ({edad_hijo} años) está fuera del rango validado "
                f"({EDAD_HIJO[0]}–{EDAD_HIJO[1]})."
            )


def _esc(texto: Any) -> str:
    """Escapa texto para Paragraph de reportlab (interpreta marcado XML-like)."""
    return escape(str(texto))


def _uf(valor: float) -> str:
    """Formato es-CL de montos en UF: punto de miles y coma decimal, 2 decimales."""
    return f"{valor:,.2f}".translate(_SWAP_MILES)


def _clp(valor: float) -> str:
    """Formato es-CL de montos en pesos: punto de miles, sin decimales."""
    return f"{valor:,.0f}".translate(_SWAP_MILES)


def _tratamiento(sexo: Literal["H", "M"]) -> str:
    """Tratamiento para la banda superior de la ficha (Sr./Sra.)."""
    return "Sr." if sexo == "H" else "Sra."


def _anios(meses: int) -> str:
    """Años como entero si es exacto, o con 1 decimal es-CL en otro caso."""
    anios = meses / 12.0
    if anios.is_integer():
        return str(int(anios))
    return f"{anios:.1f}".replace(".", ",")


def _pension_aumentada(pension: float, porcentaje_aumento_temporal: float) -> float:
    """Pensión mensual durante el aumento temporal: base × (1 + %/100)."""
    return pension * (1 + porcentaje_aumento_temporal / 100.0)


def _rescate_opcion_i(pension: float, meses_garantizados: int) -> float:
    """Rescate Total de la Opción I = pensión mensual × meses garantizados."""
    return pension * meses_garantizados


def _valor_actual(pension: float, valor_uf: float | None) -> float | None:
    """$ Valor Actual = pensión × valor UF (solo si hay valor UF informado)."""
    return pension * valor_uf if valor_uf is not None else None


def _valor_futuro(valor_actual: float, meses_aumento_temporal: int) -> float:
    """Valor Futuro = Valor Actual × 1,04 elevado a los años de aumento temporal."""
    return valor_actual * math.pow(1.04, meses_aumento_temporal / 12.0)


def _rescate_opcion_ii(
    pension: float,
    porcentaje_aumento_temporal: float,
    meses_aumento_temporal: int,
    meses_garantizados: int,
) -> float:
    """Rescate Total de la Opción II = aumentada × meses aumento + base × (garantía − aumento)."""
    aumentada = _pension_aumentada(pension, porcentaje_aumento_temporal)
    return aumentada * meses_aumento_temporal + pension * (
        meses_garantizados - meses_aumento_temporal
    )


def generar_pdf(
    *,
    fecha_hora: datetime,
    ejecutivo: str,
    lead_nombre: str,
    sexo_causante: Literal["H", "M"],
    causante_nacimiento: date,
    tiene_conyuge: bool,
    escenario: Escenario,
    resultado: Resultado,
    tasa_venta_pct: float,
    valor_uf: float | None,
    saldo_uf: float,
    meses_garantizados: int,
    meses_aumento_temporal: int,
    porcentaje_aumento_temporal: float,
    anios_diferidos: int,
    advertencia_ventana: bool,
    codigo: str,
) -> bytes:
    """Genera en memoria la ficha PDF «Estudio de pensión» (carta apaisada) sin escribir a disco."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=_MARGEN,
        rightMargin=_MARGEN,
        topMargin=_MARGEN,
        bottomMargin=_MARGEN,
        title="Estudio de pensión",
        author="Tu Pensión Inteligente",
        subject="Estimación referencial no vinculante",
    )

    styles = getSampleStyleSheet()

    def _ps(
        name: str,
        *,
        font: str,
        size: float,
        leading: float,
        color: Any = _BODY,
        align: int = TA_LEFT,
    ) -> ParagraphStyle:
        return ParagraphStyle(
            name,
            parent=styles["Normal"],
            fontName=font,
            fontSize=size,
            leading=leading,
            textColor=color,
            alignment=align,
        )

    banda_nombre = _ps(
        "BandaNombre", font="Helvetica-Bold", size=14, leading=16, color=colors.white
    )
    banda_titulo = _ps(
        "BandaTitulo",
        font="Helvetica-Bold",
        size=14,
        leading=16,
        color=colors.white,
        align=TA_CENTER,
    )
    banda_fecha = _ps(
        "BandaFecha", font="Helvetica-Bold", size=12, leading=14, color=colors.white, align=TA_RIGHT
    )
    dato = _ps("Dato", font="Helvetica-Bold", size=9, leading=11)
    opcion_titulo = _ps("OpcionTitulo", font="Helvetica-Bold", size=12, leading=14)
    cabecera = _ps("Cabecera", font="Helvetica-Bold", size=9, leading=11, color=colors.white)
    rotulo = _ps("Rotulo", font="Helvetica-Bold", size=8, leading=10)
    celda_dato = _ps("CeldaDato", font="Helvetica-BoldOblique", size=9, leading=11)
    nota = _ps("Nota", font="Helvetica-Bold", size=8, leading=10)
    pie_ejecutivo = _ps("PieEjecutivo", font="Helvetica-Bold", size=10, leading=12, color=_NAVY)
    pie_texto = _ps("PieTexto", font="Helvetica", size=8, leading=10)
    leyenda = _ps(
        "Leyenda", font="Helvetica", size=8, leading=10, color=colors.grey, align=TA_CENTER
    )

    ancho = _PAGE_W - 2 * _MARGEN

    story: list[Any] = []

    # a) Banda superior: tratamiento + nombre, título y fecha de generación.
    banda = Table(
        [
            [
                Paragraph(f"{_tratamiento(sexo_causante)} {_esc(lead_nombre)}", banda_nombre),
                Paragraph("ESTUDIO DE PENSIÓN", banda_titulo),
                Paragraph(_esc(fecha_hora.strftime("%d-%m-%Y")), banda_fecha),
            ]
        ],
        colWidths=[ancho // 3] * 3,
        hAlign="LEFT",
    )
    banda.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(banda)
    story.append(Spacer(1, 8))

    # b) Fila de datos bajo la banda (celdas con borde; la celda del valor UF va destacada).
    celdas = [Paragraph(f"FECHA DE NAC: {causante_nacimiento.strftime('%Y/%m/%d')}", dato)]
    if tiene_conyuge:
        celdas.append(Paragraph("CÓNYUGE: Sí", dato))
    celdas.append(Paragraph(f"T: {_uf(tasa_venta_pct)}%", dato))
    if valor_uf is not None:
        celdas.append(Paragraph(f"VALOR UF: ${_clp(valor_uf)}", dato))

    fila_datos = Table([celdas], colWidths=[ancho // len(celdas)] * len(celdas), hAlign="LEFT")
    estilo_datos: list[Any] = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if valor_uf is not None:
        estilo_datos.append(("BACKGROUND", (len(celdas) - 1, 0), (len(celdas) - 1, 0), _HIGHLIGHT))
    fila_datos.setStyle(TableStyle(estilo_datos))
    story.append(fila_datos)
    story.append(Spacer(1, 10))

    pension = resultado.pension_mensual
    valor_actual_base = _valor_actual(pension, valor_uf)

    if anios_diferidos > 0:
        # Renta temporal + RVD: se conserva su sección, con la nueva apariencia (AC-4).
        story.append(Paragraph("RENTA TEMPORAL + RENTA VITALICIA DIFERIDA", opcion_titulo))
        story.append(Paragraph(_esc(escenario.descripcion), pie_texto))
        story.append(Spacer(1, 4))
        filas_rvd: list[list[Any]] = [
            [
                Paragraph("Pensión mensual estimada (UF)", rotulo),
                Paragraph(_uf(pension), celda_dato),
            ],
        ]
        if resultado.meses_diferidos:
            filas_rvd.append(
                [
                    Paragraph("Meses de diferimiento", rotulo),
                    Paragraph(str(resultado.meses_diferidos), celda_dato),
                ]
            )
        if resultado.renta_temporal_mensual is not None:
            filas_rvd.append(
                [
                    Paragraph("Renta temporal mensual (UF)", rotulo),
                    Paragraph(_uf(resultado.renta_temporal_mensual), celda_dato),
                ]
            )
        if valor_uf is not None:
            filas_rvd.append(
                [
                    Paragraph("Valor UF de referencia (CLP)", rotulo),
                    Paragraph(_clp(valor_uf), celda_dato),
                ]
            )
            filas_rvd.append(
                [
                    Paragraph("Equivalente en pesos (CLP)", rotulo),
                    Paragraph(_clp(pension * valor_uf), celda_dato),
                ]
            )
        tabla_rvd = Table(filas_rvd, colWidths=[260, 160], hAlign="LEFT")
        tabla_rvd.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, 0), (0, -1), _NAVY_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(tabla_rvd)
    else:
        # c) OPCIÓN I (renta vitalicia inmediata + rescate total).
        story.append(Paragraph("OPCIÓN I", opcion_titulo))
        rescate_i = _rescate_opcion_i(pension, meses_garantizados)
        if meses_garantizados:
            etiqueta_i = f"Periodo Garantizado<br/>{_anios(meses_garantizados)} años"
        else:
            etiqueta_i = "Simple"
        tabla_i = Table(
            [
                [
                    Paragraph("Renta Vitalicia Inmediata", cabecera),
                    "",
                    "",
                    "",
                    Paragraph("Rescate Total", cabecera),
                ],
                [
                    Paragraph(f"Capital: {_uf(saldo_uf)} UF", dato),
                    "",
                    Paragraph(f"T: {_uf(tasa_venta_pct)}%", dato),
                    "",
                    "",
                ],
                [
                    Paragraph("Años", rotulo),
                    Paragraph("[UF]", rotulo),
                    Paragraph("[$]Valor Actual", rotulo),
                    "",
                    Paragraph("[UF]", rotulo),
                ],
                [
                    Paragraph(etiqueta_i, celda_dato),
                    Paragraph(_uf(pension), celda_dato),
                    Paragraph(
                        _clp(valor_actual_base) if valor_actual_base is not None else "", celda_dato
                    ),
                    Paragraph(">>>>", celda_dato),
                    Paragraph(_uf(rescate_i), celda_dato),
                ],
            ],
            colWidths=[140, 90, 120, 70, 120],
            hAlign="LEFT",
        )
        tabla_i.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (2, 0)),
                    ("SPAN", (0, 1), (1, 1)),
                    ("BACKGROUND", (0, 0), (2, 0), _NAVY),
                    ("BACKGROUND", (4, 0), (4, 0), _NAVY),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (3, 3), (3, 3), "CENTER"),
                ]
            )
        )
        story.append(tabla_i)
        story.append(Paragraph("Esta Opción es vitalicia sin recálculo", nota))

        # d) OPCIÓN II (solo si la simulación incluye aumento temporal).
        if meses_aumento_temporal > 0:
            story.append(Spacer(1, 8))
            story.append(Paragraph("OPCIÓN II", opcion_titulo))
            pension_aumentada = _pension_aumentada(pension, porcentaje_aumento_temporal)
            valor_actual_aumentada = _valor_actual(pension_aumentada, valor_uf)
            valor_futuro = (
                _valor_futuro(valor_actual_aumentada, meses_aumento_temporal)
                if valor_actual_aumentada is not None
                else None
            )
            rescate_ii = _rescate_opcion_ii(
                pension, porcentaje_aumento_temporal, meses_aumento_temporal, meses_garantizados
            )

            izquierda = Table(
                [
                    [Paragraph("Aumento Temporal de Pensión", cabecera), "", "", ""],
                    [
                        Paragraph(f"Capital: {_uf(saldo_uf)} UF", dato),
                        "",
                        Paragraph(f"T: {_uf(tasa_venta_pct)}%", dato),
                        "",
                    ],
                    [
                        Paragraph("Años", rotulo),
                        Paragraph("Meses", rotulo),
                        Paragraph("[UF]", rotulo),
                        Paragraph("[$]", rotulo),
                    ],
                    [
                        Paragraph(_anios(meses_aumento_temporal), celda_dato),
                        Paragraph(str(meses_aumento_temporal), celda_dato),
                        Paragraph(_uf(pension_aumentada), celda_dato),
                        Paragraph(
                            (
                                _clp(valor_actual_aumentada)
                                if valor_actual_aumentada is not None
                                else ""
                            ),
                            celda_dato,
                        ),
                    ],
                ],
                colWidths=[90, 60, 80, 90],
                hAlign="LEFT",
            )
            izquierda.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 0), (3, 0)),
                        ("SPAN", (0, 1), (1, 1)),
                        ("BACKGROUND", (0, 0), (3, 0), _NAVY),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )

            derecha = Table(
                [
                    [Paragraph("Renta Vitalicia Inmediata", cabecera), "", ""],
                    [
                        Paragraph(f"Capital: {_uf(saldo_uf)} UF", dato),
                        "",
                        Paragraph(f"T: {_uf(tasa_venta_pct)}%", dato),
                    ],
                    [Paragraph("Sin Excedente", rotulo), "", ""],
                    [
                        Paragraph("Años", rotulo),
                        Paragraph("[UF]", rotulo),
                        Paragraph("[$]Valor Actual", rotulo),
                    ],
                    [
                        Paragraph(_anios(meses_garantizados), celda_dato),
                        Paragraph(_uf(pension), celda_dato),
                        Paragraph(
                            _clp(valor_actual_base) if valor_actual_base is not None else "",
                            celda_dato,
                        ),
                    ],
                    [
                        Paragraph("Inflación Futura 4%", rotulo),
                        "",
                        Paragraph(
                            _clp(valor_futuro) if valor_futuro is not None else "", celda_dato
                        ),
                    ],
                    [
                        Paragraph("Rescate Total", rotulo),
                        "",
                        Paragraph(_uf(rescate_ii), celda_dato),
                    ],
                ],
                colWidths=[130, 80, 110],
                hAlign="LEFT",
            )
            derecha.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 0), (2, 0)),
                        ("SPAN", (0, 1), (1, 1)),
                        ("SPAN", (0, 2), (2, 2)),
                        ("BACKGROUND", (0, 0), (2, 0), _NAVY),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )

            tabla_ii = Table(
                [[izquierda, Paragraph(">>>>", celda_dato), derecha]],
                colWidths=[320, 60, 320],
                hAlign="LEFT",
            )
            tabla_ii.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
            story.append(tabla_ii)
            story.append(Paragraph("Esta Opción es vitalicia sin recálculo", nota))

    story.append(Spacer(1, 10))

    # e) Pie: nombre del ejecutivo y contacto corporativo como texto plano (sin enlaces activos).
    contacto_izq = [
        Paragraph(_esc(ejecutivo), pie_ejecutivo),
        Paragraph("Tu Pensión Inteligente", pie_texto),
    ]
    contacto_der = [
        Paragraph("Email: contacto@tupensioninteligente.cl", pie_texto),
        Paragraph("Web: www.tupensioninteligente.cl", pie_texto),
        Paragraph("Dirección: Dr. Sotero del Río 508, Of. 612, Santiago", pie_texto),
    ]
    pie = Table([[contacto_izq, contacto_der]], colWidths=[ancho // 2, ancho // 2], hAlign="LEFT")
    pie.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(pie)

    # g) Leyenda, versión y código de verificación conservados de SIM-RV-V1.
    story.append(Spacer(1, 6))
    story.append(Paragraph("Estimación referencial no vinculante", leyenda))
    story.append(
        Paragraph(
            f"Versión del modelo: {MODELO_VERSION} — Código de verificación: {codigo}",
            leyenda,
        )
    )
    if advertencia_ventana:
        story.append(
            Paragraph(
                "Advertencia: la ventana de validación del modelo ha vencido recientemente; los resultados "
                "deben contrastarse con el simulador de referencia antes de entregarlos.",
                leyenda,
            )
        )
    story.append(Paragraph("Documento referencial no vinculante — Tu Pensión Inteligente", leyenda))

    # f) Banda inferior con el logo oficial.
    story.append(Spacer(1, 6))
    if _LOGO_DARK_PATH.exists():
        logo = Image(str(_LOGO_DARK_PATH))
        ratio = logo.imageWidth / logo.imageHeight
        logo.drawWidth = 270
        logo.drawHeight = 270 / ratio
        banda_inferior = Table([[logo]], colWidths=[ancho], hAlign="LEFT")
        banda_inferior.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(banda_inferior)

    doc.build(story)
    return buf.getvalue()


class SimuladorService:
    """Servicio de orquestación del simulador (motor + auditoría)."""

    @staticmethod
    def can_simulate(user: AuthenticatedUser | None) -> bool:
        if user is None:
            return False
        return is_superuser(user.role) or user.role == "executive"

    def simular(
        self,
        *,
        fecha_simulacion: date,
        saldo_uf: float,
        tasa_venta_pct: float,
        causante: Persona,
        conyuge: Persona | None,
        hijos: tuple[Hijo, ...],
        meses_garantizados: int,
        meses_aumento_temporal: int,
        porcentaje_aumento_temporal: float,
        anios_diferidos: int,
        porcentaje_rvd: float,
    ) -> Resultado:
        validar_edades(
            fecha_simulacion=fecha_simulacion,
            causante=causante,
            conyuge=conyuge,
            hijos=hijos,
            anios_diferidos=anios_diferidos,
        )
        try:
            return simular(
                fecha_simulacion=fecha_simulacion,
                saldo_uf=saldo_uf,
                tasa_venta_pct=tasa_venta_pct,
                causante=causante,
                conyuge=conyuge,
                hijos=hijos,
                meses_garantizados=meses_garantizados,
                meses_aumento_temporal=meses_aumento_temporal,
                porcentaje_aumento_temporal=porcentaje_aumento_temporal,
                anios_diferidos=anios_diferidos,
                porcentaje_rvd=porcentaje_rvd,
            )
        except NoValidadoError as exc:
            raise SimulacionInvalidaError(str(exc)) from exc
        except ValueError as exc:
            raise SimulacionInvalidaError(str(exc)) from exc

    def record_event(
        self,
        *,
        id_lead: Any,
        actor: AuthenticatedUser,
        tipo_escenario: str,
        codigo: str,
    ) -> None:
        record_simulacion_event(
            id_lead=id_lead,
            actor_subject=actor.subject,
            role=actor.role,
            tipo_escenario=tipo_escenario,
            version_modelo=MODELO_VERSION,
            codigo_verificacion=codigo,
        )
