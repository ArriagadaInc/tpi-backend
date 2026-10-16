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
from math import isfinite
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.services.simulador_service import (
    CRM_TZ,
    Escenario,
    SimulacionInvalidaError,
    SimuladorService,
    clasificar_escenario,
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

# AC-13: tope razonable para el valor UF opcional (equivalente en pesos en el PDF). La UF ronda
# los 38.000 CLP; este tope descarta valores absurdos/infinitos sin restringir un uso legítimo.
VALOR_UF_MAX = 1_000_000.0


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
        if v is None:
            return v
        if not isfinite(v) or v <= 0:
            raise ValueError("El valor UF debe ser un número finito mayor que cero.")
        if v > VALOR_UF_MAX:
            raise ValueError(f"El valor UF no puede superar {VALOR_UF_MAX:,.0f}.".replace(",", "."))
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
        if v == 100 or v == 50:
            return v
        if 51 <= v <= 99 and v.is_integer():
            return v
        raise ValueError("La relación RVD/RT debe ser 100, 50 o un entero entre 51 y 99.")

    @model_validator(mode="after")
    def _rangos_por_escenario(self) -> SimuladorForm:
        """Rangos validados por escenario (matriz §4): saldo mínimo en renta temporal y tasa
        máxima en renta inmediata. No altera la lógica numérica del motor."""
        if self.anios_diferidos > 0:  # renta temporal
            if self.saldo_uf < 1_000:
                raise ValueError("En renta temporal el saldo en UF debe ser de al menos 1.000.")
        elif self.tasa_venta_pct > 7.5:  # renta inmediata
            raise ValueError(
                "En renta inmediata la tasa de venta debe ser de hasta 7,5% (8% solo en renta temporal)."
            )
        return self


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


def _form_context(
    request: Request,
    lead_id: str,
    lead: dict[str, Any] | None,
    *,
    form_values: Mapping[str, Any] | None = None,
    simulador_errores: list[str] | None = None,
) -> dict[str, Any]:
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
        "form_values": dict(form_values) if form_values else {},
        "simulador_errores": simulador_errores or [],
    }
    if lead is not None:
        context["sexo_precargado"] = _sexo_desde_genero(lead.get("genero"))
        context["fecha_nacimiento_precargada"] = _fecha_desde_valor(lead.get("fecha_nacimiento"))
    return context


def _validation_error_messages(exc: ValidationError) -> list[str]:
    """Mensajes claros en español de un ``ValidationError`` de Pydantic (sin el prefijo técnico).

    Pydantic v2 antepone ``"Value error, "`` al mensaje de los ``ValueError`` levantados en los
    validadores; se recupera el texto original para mostrarlo al usuario.
    """
    messages: list[str] = []
    for error in exc.errors():
        ctx = error.get("ctx") or {}
        original = ctx.get("error")
        if isinstance(original, Exception):
            messages.append(str(original))
            continue
        msg = str(error.get("msg", ""))
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        messages.append(msg)
    return messages or ["Los datos del formulario no son válidos. Revisa los campos ingresados."]


def _simulador_error_response(
    request: Request,
    lead_id: str,
    lead: dict[str, Any] | None,
    form: Mapping[str, Any],
    errores: list[str],
):
    """Re-renderiza el formulario en la misma pantalla (422) conservando lo ingresado (AC-1)."""
    context = _form_context(
        request, lead_id, lead, form_values=dict(form), simulador_errores=errores
    )
    return request.app.state.templates.TemplateResponse(
        request, "simulador.html", context, status_code=422
    )


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
    except ValidationError as exc:
        return _simulador_error_response(
            request, lead_id, lead, form, _validation_error_messages(exc)
        )

    fecha_simulacion = datetime.now(CRM_TZ).date()

    sim_service = SimuladorService()
    try:
        causante = _causante_desde_lead(lead)
    except SimulacionInvalidaError as exc:
        return _simulador_error_response(request, lead_id, lead, form, [str(exc)])

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
        return _simulador_error_response(request, lead_id, lead, form, [str(exc)])

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

    now = datetime.now(CRM_TZ)
    try:
        pdf = generar_pdf(
            fecha_hora=now,
            ejecutivo=user.display_name,
            lead_nombre=str(lead.get("nombre_completo") or ""),
            sexo_causante=causante.sexo,
            causante_nacimiento=causante.nacimiento,
            tiene_conyuge=conyuge is not None,
            escenario=escenario,
            resultado=resultado,
            tasa_venta_pct=simulador_form.tasa_venta_pct,
            valor_uf=simulador_form.valor_uf,
            saldo_uf=simulador_form.saldo_uf,
            meses_garantizados=simulador_form.meses_garantizados,
            meses_aumento_temporal=simulador_form.meses_aumento_temporal,
            porcentaje_aumento_temporal=simulador_form.porcentaje_aumento_temporal,
            anios_diferidos=simulador_form.anios_diferidos,
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
