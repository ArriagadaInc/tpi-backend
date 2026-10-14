"""Servicio de aplicación del simulador de renta vitalicia (SIM-RV-V1).

Orquesta el motor puro (:mod:`app.simulador_pension`), la generación del PDF efímero y el
evento funcional de auditoría. No persiste entradas ni resultados de la simulación.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
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

_LOGO_PATH = (
    Path(__file__).resolve().parent.parent / "web" / "static" / "img" / "official-logo-on-light.png"
)

_A4_WIDTH, _A4_HEIGHT = A4


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


def _pie_pagina(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(_A4_WIDTH / 2, 12 * mm, f"Página {canvas.getPageNumber()}")
    canvas.drawCentredString(
        _A4_WIDTH / 2, 8 * mm, "Documento referencial no vinculante — Tu Pensión Inteligente"
    )
    canvas.restoreState()


def generar_pdf(
    *,
    fecha_hora: datetime,
    ejecutivo: str,
    lead_nombre: str,
    escenario: Escenario,
    parametros: list[tuple[str, str]],
    resultado: Resultado,
    tasa_venta_pct: float,
    valor_uf: float | None,
    advertencia_ventana: bool,
    codigo: str,
) -> bytes:
    """Genera el PDF efímero en memoria (sin escribir a disco)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="Simulación referencial de pensión",
        author="Tu Pensión Inteligente",
        subject="Estimación referencial no vinculante",
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "Titulo", parent=styles["Title"], fontSize=17, leading=21, spaceAfter=2 * mm
    )
    subtitulo = ParagraphStyle(
        "Subtitulo", parent=styles["Normal"], fontSize=9, textColor=colors.grey
    )
    seccion = ParagraphStyle(
        "Seccion", parent=styles["Heading2"], fontSize=11, spaceBefore=4 * mm, spaceAfter=1.5 * mm
    )
    normal = ParagraphStyle("NormalR", parent=styles["Normal"], fontSize=9.5, leading=13)
    pie_legal = ParagraphStyle(
        "PieLegal",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
        leading=11,
        alignment=TA_CENTER,
    )

    story: list[Any] = []
    if _LOGO_PATH.exists():
        logo = Image(str(_LOGO_PATH))
        ratio = logo.imageWidth / logo.imageHeight
        logo.drawWidth = 58 * mm
        logo.drawHeight = 58 * mm / ratio
        story.append(logo)
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Simulación referencial de pensión de renta vitalicia", titulo))
    story.append(
        Paragraph(
            f"Generado el {fecha_hora.strftime('%d/%m/%Y %H:%M')} (America/Santiago) — Ejecutivo: {_esc(ejecutivo)}",
            subtitulo,
        )
    )
    story.append(Spacer(1, 3 * mm))

    # Datos del lead (solo nombre; sin RUT, correo ni teléfono).
    story.append(Paragraph("Cliente", seccion))
    story.append(Paragraph(_esc(lead_nombre), normal))

    story.append(Paragraph("Escenario", seccion))
    story.append(Paragraph(_esc(escenario.descripcion), normal))
    story.append(Paragraph(f"Tasa de venta utilizada: {round(tasa_venta_pct, 2)}%", normal))

    story.append(Paragraph("Parámetros ingresados", seccion))
    tabla_parametros = Table(
        [[Paragraph(_esc(k), normal), Paragraph(_esc(v), normal)] for k, v in parametros],
        colWidths=[70 * mm, 102 * mm],
    )
    tabla_parametros.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tabla_parametros)

    story.append(Paragraph("Resultados", seccion))
    resultados: list[tuple[str, str]] = [
        ("Pensión mensual estimada (UF)", f"{resultado.pension_mensual:.2f}"),
    ]
    if resultado.meses_diferidos:
        resultados.append(("Meses de diferimiento", f"{resultado.meses_diferidos}"))
        if resultado.renta_temporal_mensual is not None:
            resultados.append(
                ("Renta temporal mensual (UF)", f"{resultado.renta_temporal_mensual:.2f}")
            )
    if valor_uf is not None:
        resultados.append(("Valor UF de referencia (CLP)", f"{valor_uf:.2f}"))
        resultados.append(
            ("Equivalente en pesos (CLP)", f"{resultado.pension_mensual * valor_uf:,.0f}")
        )
    tabla_resultados = Table(
        [[Paragraph(_esc(k), normal), Paragraph(_esc(v), normal)] for k, v in resultados],
        colWidths=[70 * mm, 102 * mm],
    )
    tabla_resultados.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tabla_resultados)

    story.append(Paragraph("Supuestos y advertencias", seccion))
    story.append(
        Paragraph(
            "Este documento es una estimación referencial calculada con un modelo empírico que reproduce "
            "el simulador de referencia dentro de ±1 UF, y no constituye una oferta ni un compromiso "
            "contractual. Los valores pueden variar según la normativa vigente, las tablas de mortalidad "
            "y las condiciones comerciales de la aseguradora.",
            normal,
        )
    )
    if advertencia_ventana:
        story.append(
            Paragraph(
                "Advertencia: la ventana de validación del modelo ha vencido recientemente; los resultados "
                "deben contrastarse con el simulador de referencia antes de entregarlos.",
                normal,
            )
        )
    story.append(
        Paragraph(
            "Modelo empírico, no normativo. No reemplaza la asesoría previsional regulada.",
            normal,
        )
    )

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Estimación referencial no vinculante", pie_legal))
    story.append(
        Paragraph(
            f"Versión del modelo: {MODELO_VERSION} — Código de verificación: {codigo}",
            pie_legal,
        )
    )

    doc.build(story, onFirstPage=_pie_pagina, onLaterPages=_pie_pagina)
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
