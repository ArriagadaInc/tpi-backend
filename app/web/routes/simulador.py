"""Rutas web del simulador de renta vitalicia (SIM-RV-V1).

GET muestra el formulario (precargado con el sexo y la fecha de nacimiento del lead) y POST
genera el PDF efímero. La autorización es server-side y fail-closed: solo ``executive`` y los
superusuarios ``ceo``/``cto`` pueden simular; el resto recibe 403 real (el anónimo conserva el
flujo canónico de login). La entrega es en memoria y no persiste entradas ni resultados; la
única escritura es el evento append-only de auditoría (AC-11).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.simulador_service import (
    CRM_TZ,
    Escenario,
    SimulacionInvalidaError,
    SimuladorService,
    clasificar_escenario,
    clasificar_ventana,
    codigo_verificacion,
    generar_pdf,
)
from app.simulador_pension import Hijo, Persona
from app.web.routes.leads import (
    _get_csrf_token,
    _require_web_user,
    _resolve_service,
    _validate_csrf_token,
)

router = APIRouter()

_NO_AUTORIZADO = "No autorizado"


class ConyugeForm(BaseModel):
    sexo: Literal["H", "M"]
    nacimiento: date


class HijoForm(BaseModel):
    sexo: Literal["H", "M"]
    nacimiento: date
    comun: bool = False
    invalidez: Literal["no", "parcial", "total"] = "no"


class SimuladorForm(BaseModel):
    """Validación del borde web (AC-13): tipos y rangos con mensajes claros en español."""

    saldo_uf: float
    tasa_venta_pct: float
    valor_uf: float | None = None
    conyuge: ConyugeForm | None = None
    hijos: list[HijoForm] = Field(default_factory=list, max_length=4)
    meses_garantizados: int = 0
    meses_aumento_temporal: int = 0
    porcentaje_aumento_temporal: float = 0.0
    anios_diferidos: int = 0
    porcentaje_rvd: float = 100.0

    @field_validator("saldo_uf")
    @classmethod
    def _saldo_valido(cls, v: float) -> float:
        if not 500 <= v <= 100_000:
            raise ValueError("El saldo en UF debe estar entre 500 y 100.000.")
        return v

    @field_validator("tasa_venta_pct")
    @classmethod
    def _tasa_valida(cls, v: float) -> float:
        if not 0.5 <= v <= 8:
            raise ValueError("La tasa de venta debe estar entre 0,5% y 8%.")
        return v

    @field_validator("valor_uf")
    @classmethod
    def _valor_uf_valido(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("El valor UF debe ser mayor que cero.")
        return v

    @field_validator("meses_garantizados")
    @classmethod
    def _garantia_valida(cls, v: int) -> int:
        if not 0 <= v <= 480:
            raise ValueError("Los meses de garantía deben estar entre 0 y 480.")
        return v

    @field_validator("meses_aumento_temporal")
    @classmethod
    def _meses_aumento_validos(cls, v: int) -> int:
        if not 0 <= v <= 600:
            raise ValueError("Los meses de aumento temporal deben estar entre 0 y 600.")
        return v

    @field_validator("porcentaje_aumento_temporal")
    @classmethod
    def _aumento_valido(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError("El porcentaje de aumento temporal debe estar entre 0 y 100.")
        return v

    @field_validator("anios_diferidos")
    @classmethod
    def _diferimiento_valido(cls, v: int) -> int:
        if not 0 <= v <= 10:
            raise ValueError("Los años de diferimiento deben estar entre 0 y 10.")
        return v

    @field_validator("porcentaje_rvd")
    @classmethod
    def _rvd_valido(cls, v: float) -> float:
        if not (v == 100 or 50 <= v < 100):
            raise ValueError("La relación RVD/RT debe ser 100, 50 o un valor entre 51 y 99.")
        return v


def _sexo_desde_genero(genero: Any) -> Literal["H", "M"] | None:
    if genero in ("Masculino", "MASCULINO", "H"):
        return "H"
    if genero in ("Femenino", "FEMENINO", "M"):
        return "M"
    return None


def _fecha_desde_valor(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _causante_desde_lead(lead: dict[str, Any]) -> Persona:
    sexo = _sexo_desde_genero(lead.get("genero"))
    nacimiento = _fecha_desde_valor(lead.get("fecha_nacimiento"))
    if sexo is None or nacimiento is None:
        raise SimulacionInvalidaError(
            "El lead no tiene sexo o fecha de nacimiento disponibles para simular."
        )
    return Persona(sexo=sexo, nacimiento=nacimiento)


def _simulacion_filename(now: datetime) -> str:
    """Nombre de descarga predecible fecha/hora, sin PII (AC-9)."""
    return f"simulacion_rv_{now.strftime('%Y%m%d_%H%M%S')}.pdf"


def _parametros_pdf(
    *,
    form: SimuladorForm,
    causante: Persona,
    edad_causante: int,
) -> list[tuple[str, str]]:
    parametros: list[tuple[str, str]] = [
        ("Saldo en UF", f"{form.saldo_uf:,.2f}".replace(",", ".")),
        ("Tasa de venta", f"{form.tasa_venta_pct:.2f}%"),
    ]
    if form.valor_uf is not None:
        parametros.append(("Valor UF de referencia (CLP)", f"{form.valor_uf:.2f}"))
    parametros.append(("Causante", f"{causante.sexo}, {edad_causante} años"))
    if form.conyuge is not None:
        parametros.append(
            ("Cónyuge", f"{form.conyuge.sexo}, {form.conyuge.nacimiento.isoformat()}")
        )
    for i, hijo in enumerate(form.hijos, 1):
        invalidez = {
            "no": "sin invalidez",
            "parcial": "invalidez parcial",
            "total": "invalidez total",
        }[hijo.invalidez]
        comun = "común" if hijo.comun else "no común"
        parametros.append(
            (f"Hijo {i}", f"{hijo.sexo}, {hijo.nacimiento.isoformat()}, {comun}, {invalidez}")
        )
    if form.meses_garantizados:
        parametros.append(("Garantía (meses)", str(form.meses_garantizados)))
    if form.meses_aumento_temporal:
        parametros.append(("Aumento temporal", f"{form.meses_aumento_temporal} meses"))
        parametros.append(("Porcentaje de aumento", f"{form.porcentaje_aumento_temporal:.2f}%"))
    if form.anios_diferidos:
        parametros.append(("Años de diferimiento", str(form.anios_diferidos)))
        parametros.append(("Relación RVD/RT", f"{form.porcentaje_rvd:.0f}%"))
    return parametros


def _parse_simulador_form(raw: Mapping[str, Any]) -> SimuladorForm:
    data: dict[str, Any] = {
        "saldo_uf": raw.get("saldo_uf"),
        "tasa_venta_pct": raw.get("tasa_venta_pct"),
        "valor_uf": raw.get("valor_uf") or None,
        "meses_garantizados": raw.get("meses_garantizados") or 0,
        "meses_aumento_temporal": raw.get("meses_aumento_temporal") or 0,
        "porcentaje_aumento_temporal": raw.get("porcentaje_aumento_temporal") or 0,
        "anios_diferidos": raw.get("anios_diferidos") or 0,
        "porcentaje_rvd": raw.get("porcentaje_rvd") or 100.0,
    }

    conyuge_sexo = str(raw.get("conyuge_sexo") or "").strip()
    conyuge_nacimiento = str(raw.get("conyuge_nacimiento") or "").strip()
    if conyuge_sexo or conyuge_nacimiento:
        data["conyuge"] = {"sexo": conyuge_sexo, "nacimiento": conyuge_nacimiento}

    hijos: list[dict[str, Any]] = []
    for i in range(1, 5):
        sexo = str(raw.get(f"hijo_sexo_{i}") or "").strip()
        nacimiento = str(raw.get(f"hijo_nacimiento_{i}") or "").strip()
        if not sexo and not nacimiento:
            continue
        comun_raw = str(raw.get(f"hijo_comun_{i}") or "").strip().casefold()
        hijos.append(
            {
                "sexo": sexo,
                "nacimiento": nacimiento,
                "comun": comun_raw in {"1", "true", "on", "si", "sí", "yes"},
                "invalidez": str(raw.get(f"hijo_invalidez_{i}") or "no").strip() or "no",
            }
        )
    data["hijos"] = hijos
    return SimuladorForm(**data)


def _form_context(request: Request, lead_id: str, lead: dict[str, Any] | None) -> dict[str, Any]:
    user = _require_web_user(request)
    context: dict[str, Any] = {
        "request": request,
        "selected_user": user,
        "active_nav": "leads",
        "page_title": "Simulador de renta vitalicia",
        "lead_id": lead_id,
        "selected_lead": lead,
        "can_view_executive_dashboard": bool(user)
        and (user is not None and user.role in {"ceo", "cto"}),
        "web_env_label": getattr(request.app.state, "web_env_label", ""),
        "public_site_url": getattr(request.app.state, "web_public_site_url", None),
        "csrf_token": _get_csrf_token(request),
        "return_to_url": f"/leads/{lead_id}",
        "advertencia_ventana": clasificar_ventana(datetime.now(CRM_TZ).date()) == "advertencia",
    }
    if lead is not None:
        context["sexo_precargado"] = _sexo_desde_genero(lead.get("genero"))
        context["fecha_nacimiento_precargada"] = _fecha_desde_valor(lead.get("fecha_nacimiento"))
    return context


@router.get("/leads/{lead_id}/simulador", response_class=HTMLResponse)
def simulador_form(request: Request, lead_id: str):
    user = _require_web_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=307)
    if not SimuladorService.can_simulate(user):
        return PlainTextResponse(_NO_AUTORIZADO, status_code=403)

    service = _resolve_service(request)
    lead = service.get_solicitud_detalle_masked(lead_id, user=user)
    if lead is None:
        context = _form_context(request, lead_id, lead=None)
        context["lead_not_found"] = True
        return request.app.state.templates.TemplateResponse(
            request, "simulador.html", context, status_code=404
        )

    return request.app.state.templates.TemplateResponse(
        request, "simulador.html", _form_context(request, lead_id, lead)
    )


@router.post("/leads/{lead_id}/simulador")
async def simulador_generar(request: Request, lead_id: str):
    user = _require_web_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=307)
    if not SimuladorService.can_simulate(user):
        return PlainTextResponse(_NO_AUTORIZADO, status_code=403)

    service = _resolve_service(request)
    lead = service.get_solicitud_detalle_masked(lead_id, user=user)
    if lead is None:
        return PlainTextResponse("No encontramos el lead solicitado.", status_code=404)

    form = await request.form()
    if not _validate_csrf_token(request, str(form.get("csrf_token") or "")):
        return PlainTextResponse(
            "La sesion de seguridad ha expirado. Recarga la pagina e intenta nuevamente.",
            status_code=403,
        )

    try:
        simulador_form = _parse_simulador_form(form)
    except ValidationError:
        return PlainTextResponse(
            "Los datos del formulario no son validos. Revisa los campos ingresados.",
            status_code=422,
        )

    fecha_simulacion = datetime.now(CRM_TZ).date()
    estado_ventana = clasificar_ventana(fecha_simulacion)
    if estado_ventana == "bloqueado":
        return PlainTextResponse(
            "La ventana de validación del modelo ha vencido. No es posible generar la simulación.",
            status_code=422,
        )

    sim_service = SimuladorService()
    try:
        causante = _causante_desde_lead(lead)
    except SimulacionInvalidaError as exc:
        return PlainTextResponse(str(exc), status_code=422)

    conyuge = (
        Persona(sexo=simulador_form.conyuge.sexo, nacimiento=simulador_form.conyuge.nacimiento)
        if simulador_form.conyuge is not None
        else None
    )
    hijos = tuple(
        Hijo(
            sexo=h.sexo,
            nacimiento=h.nacimiento,
            comun=h.comun,
            invalidez=h.invalidez,
        )
        for h in simulador_form.hijos
    )

    escenario: Escenario = clasificar_escenario(
        anios_diferidos=simulador_form.anios_diferidos,
        tiene_conyuge=conyuge is not None,
        n_hijos=len(hijos),
        con_garantia_aumento=bool(
            simulador_form.meses_garantizados or simulador_form.meses_aumento_temporal
        ),
    )

    try:
        resultado = sim_service.simular(
            fecha_simulacion=fecha_simulacion,
            saldo_uf=simulador_form.saldo_uf,
            tasa_venta_pct=simulador_form.tasa_venta_pct,
            causante=causante,
            conyuge=conyuge,
            hijos=hijos,
            meses_garantizados=simulador_form.meses_garantizados,
            meses_aumento_temporal=simulador_form.meses_aumento_temporal,
            porcentaje_aumento_temporal=simulador_form.porcentaje_aumento_temporal,
            anios_diferidos=simulador_form.anios_diferidos,
            porcentaje_rvd=simulador_form.porcentaje_rvd,
        )
    except SimulacionInvalidaError as exc:
        return PlainTextResponse(str(exc), status_code=422)

    codigo = codigo_verificacion(
        fecha_simulacion=fecha_simulacion,
        saldo_uf=simulador_form.saldo_uf,
        tasa_venta_pct=simulador_form.tasa_venta_pct,
        causante=causante,
        conyuge=conyuge,
        hijos=hijos,
        meses_garantizados=simulador_form.meses_garantizados,
        meses_aumento_temporal=simulador_form.meses_aumento_temporal,
        porcentaje_aumento_temporal=simulador_form.porcentaje_aumento_temporal,
        anios_diferidos=simulador_form.anios_diferidos,
        porcentaje_rvd=simulador_form.porcentaje_rvd,
    )

    edad_causante = (fecha_simulacion.year - causante.nacimiento.year) - (
        (fecha_simulacion.month, fecha_simulacion.day)
        < (causante.nacimiento.month, causante.nacimiento.day)
    )
    now = datetime.now(CRM_TZ)
    try:
        pdf = generar_pdf(
            fecha_hora=now,
            ejecutivo=user.display_name,
            lead_nombre=str(lead.get("nombre_completo") or ""),
            escenario=escenario,
            parametros=_parametros_pdf(
                form=simulador_form, causante=causante, edad_causante=edad_causante
            ),
            resultado=resultado,
            tasa_venta_pct=simulador_form.tasa_venta_pct,
            valor_uf=simulador_form.valor_uf,
            advertencia_ventana=estado_ventana == "advertencia",
            codigo=codigo,
        )
    except Exception:
        return PlainTextResponse(
            "No fue posible generar el PDF. Intenta nuevamente.", status_code=500
        )

    # AC-11: evento append-only tras un PDF generado con éxito (fail-closed: sin auditoría
    # no se entrega el PDF).
    try:
        sim_service.record_event(
            id_lead=lead_id,
            actor=user,
            tipo_escenario=escenario.tipo,
            codigo=codigo,
        )
    except Exception:
        return PlainTextResponse(
            "No fue posible generar el PDF. Intenta nuevamente.", status_code=500
        )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_simulacion_filename(now)}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
