"""Rutas web del simulador de renta vitalicia (SIM-RV-V1, una sola página).

GET muestra el formulario (Datos de la simulación y Grupo familiar) junto al panel de resultado,
precargado con el sexo y la fecha de nacimiento del lead. POST despacha por ``intent``:

- ``simular``: valida todo y calcula el resultado en el servidor, mostrándolo en el panel de
  resultado de la misma página (con lo ingresado conservado) sin persistir ni auditar nada (AC-4).
- ``descargar_pdf`` (también el valor por defecto, sin ``intent``): valida todo, genera el PDF
  efímero en memoria y registra el evento append-only de auditoría (AC-9, AC-11).

Cualquier otro valor de ``intent`` (un formulario viejo o manipulado) se trata como ``simular``:
nunca genera PDF ni auditoría.

La autorización es server-side y fail-closed: solo ``executive`` y los superusuarios ``ceo``/``cto``
pueden simular; el resto recibe 403 real (el anónimo conserva el flujo canónico de login). La
entrega es en memoria y no persiste entradas ni resultados; la única escritura es el evento
append-only de auditoría. El servidor es la fuente de verdad: toda validación (rangos, edades, CSRF,
autorización 403 y 404) y todo cálculo ocurren en el servidor; la interfaz solo guía.
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
    _edad_anios,
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

_TIPOS_PENSION = (("vejez_edad", "Vejez edad"),)

_SEXO_LABEL = {"H": "Masculino", "M": "Femenino"}
_INVALIDEZ_LABEL = {"no": "No inválido", "parcial": "Inválido parcial", "total": "Inválido total"}
_RELACION_LABEL = {True: "Común", False: "No común"}

# Intercambio de separadores de miles/decimales al formato es-CL (punto de miles, coma decimal).
_SWAP = str.maketrans({",": ".", ".": ","})


class ConyugeForm(BaseModel):
    sexo: Literal["H", "M"]
    nacimiento: date
    invalidez: Literal["no", "parcial", "total"] = "no"

    @model_validator(mode="after")
    def _rechazar_conyuge_invalido(self) -> ConyugeForm:
        """La V1 no valida un cónyuge inválido (pendiente #8): se rechaza con mensaje claro."""
        if self.invalidez != "no":
            raise ValueError("Un cónyuge inválido no es un escenario soportado por el simulador.")
        return self


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
    tipo_pension: Literal["vejez_edad"] = "vejez_edad"

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


def _fmt_uf(valor: float) -> str:
    """Formato es-CL de montos en UF: punto de miles y coma decimal, 2 decimales."""
    return f"{valor:,.2f}".translate(_SWAP)


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


def _sexo_label(sexo: Literal["H", "M"] | None) -> str:
    return _SEXO_LABEL.get(sexo, "") if sexo else ""


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
        "tipo_pension": raw.get("tipo_pension") or "vejez_edad",
    }

    conyuge_sexo = str(raw.get("conyuge_sexo") or "").strip()
    conyuge_nacimiento = str(raw.get("conyuge_nacimiento") or "").strip()
    if conyuge_sexo or conyuge_nacimiento:
        data["conyuge"] = {
            "sexo": conyuge_sexo,
            "nacimiento": conyuge_nacimiento,
            "invalidez": str(raw.get("conyuge_invalidez") or "no").strip() or "no",
        }

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


def _familia_desde(
    lead: dict[str, Any] | None,
    form_values: Mapping[str, Any] | None,
    fecha_simulacion: date,
) -> list[dict[str, Any]]:
    """Grupo familiar para la tabla (causante primero, luego cónyuge e hijos), leniente.

    Se construye desde el lead (causante) y desde los valores crudos del formulario (cónyuge e
    hijos), sin validar: sirve para mostrar la tabla tal como el usuario la
    dejó. El servidor valida por separado con ``SimuladorForm`` y ``SimuladorService.simular``.
    """
    filas: list[dict[str, Any]] = []

    causante_sexo = _sexo_desde_genero(lead.get("genero")) if lead else None
    causante_nacimiento = _fecha_desde_valor(lead.get("fecha_nacimiento")) if lead else None
    filas.append(
        {
            "rol": "causante",
            "parentesco": "Causante",
            "sexo": causante_sexo,
            "sexo_label": _sexo_label(causante_sexo),
            "nacimiento": causante_nacimiento,
            "nacimiento_label": (
                causante_nacimiento.strftime("%d/%m/%Y") if causante_nacimiento else ""
            ),
            "edad": (
                _edad_anios(causante_nacimiento, fecha_simulacion) if causante_nacimiento else None
            ),
            "invalidez": None,
            "invalidez_label": "",
            "relacion_label": "",
        }
    )

    fv = form_values or {}
    conyuge_sexo = str(fv.get("conyuge_sexo") or "").strip()
    conyuge_nacimiento = _fecha_desde_valor(fv.get("conyuge_nacimiento"))
    if conyuge_sexo or conyuge_nacimiento:
        conyuge_sexo_t = _sexo_desde_genero(conyuge_sexo) if conyuge_sexo else None
        filas.append(
            {
                "rol": "conyuge",
                "parentesco": "Cónyuge",
                "sexo": conyuge_sexo_t,
                "sexo_label": _sexo_label(conyuge_sexo_t),
                "nacimiento": conyuge_nacimiento,
                "nacimiento_label": (
                    conyuge_nacimiento.strftime("%d/%m/%Y") if conyuge_nacimiento else ""
                ),
                "edad": (
                    _edad_anios(conyuge_nacimiento, fecha_simulacion)
                    if conyuge_nacimiento
                    else None
                ),
                "invalidez": str(fv.get("conyuge_invalidez") or "no").strip() or "no",
                "invalidez_label": _INVALIDEZ_LABEL.get(
                    str(fv.get("conyuge_invalidez") or "no").strip() or "no", ""
                ),
                "relacion_label": "",
            }
        )

    for i in range(1, 5):
        sexo = str(fv.get(f"hijo_sexo_{i}") or "").strip()
        nacimiento = _fecha_desde_valor(fv.get(f"hijo_nacimiento_{i}"))
        if not sexo and not nacimiento:
            continue
        sexo_t = _sexo_desde_genero(sexo) if sexo else None
        comun_raw = str(fv.get(f"hijo_comun_{i}") or "").strip().casefold()
        comun = comun_raw in {"1", "true", "on", "si", "sí", "yes"}
        invalidez = str(fv.get(f"hijo_invalidez_{i}") or "no").strip() or "no"
        filas.append(
            {
                "rol": "hijo",
                "index": i,
                "parentesco": "Hijo/a",
                "sexo": sexo_t,
                "sexo_label": _sexo_label(sexo_t),
                "nacimiento": nacimiento,
                "nacimiento_label": nacimiento.strftime("%d/%m/%Y") if nacimiento else "",
                "edad": _edad_anios(nacimiento, fecha_simulacion) if nacimiento else None,
                "invalidez": invalidez,
                "invalidez_label": _INVALIDEZ_LABEL.get(invalidez, ""),
                "relacion_label": _RELACION_LABEL.get(comun, "No común"),
            }
        )

    return filas


def _resumen_desde(simulador_form: SimuladorForm, fecha_simulacion: date) -> dict[str, Any]:
    return {
        "fecha_simulacion": fecha_simulacion.strftime("%d/%m/%Y"),
        "tipo_pension": dict(_TIPOS_PENSION).get(simulador_form.tipo_pension, "Vejez edad"),
        "saldo_uf": _fmt_uf(simulador_form.saldo_uf),
        "tasa_venta_pct": _fmt_uf(simulador_form.tasa_venta_pct),
        "meses_garantizados": simulador_form.meses_garantizados,
        "meses_aumento_temporal": simulador_form.meses_aumento_temporal,
        "porcentaje_aumento_temporal": _fmt_uf(simulador_form.porcentaje_aumento_temporal),
        "anios_diferidos": simulador_form.anios_diferidos,
    }


def _resultado_desde(resultado: Any, simulador_form: SimuladorForm) -> dict[str, Any]:
    return {
        "pension_mensual": _fmt_uf(resultado.pension_mensual),
        "saldo_total": _fmt_uf(simulador_form.saldo_uf),
        "tasa_venta": _fmt_uf(simulador_form.tasa_venta_pct),
        "renta_temporal": (
            _fmt_uf(resultado.renta_temporal_mensual)
            if resultado.renta_temporal_mensual is not None
            else None
        ),
        "meses_diferidos": resultado.meses_diferidos,
        "es_renta_temporal": simulador_form.anios_diferidos > 0,
    }


def _form_context(
    request: Request,
    lead_id: str,
    lead: dict[str, Any] | None,
    *,
    form_values: Mapping[str, Any] | None = None,
    simulador_errores: list[str] | None = None,
    fecha_simulacion: date | None = None,
    resumen: dict[str, Any] | None = None,
    resultado: dict[str, Any] | None = None,
    escenario: Escenario | None = None,
) -> dict[str, Any]:
    user = _require_web_user(request)
    fecha = fecha_simulacion or datetime.now(CRM_TZ).date()
    context: dict[str, Any] = {
        "request": request,
        "selected_user": user,
        "active_nav": "leads",
        "page_title": "Simulador de pensión mensual",
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
        "fecha_simulacion": fecha,
        "fecha_simulacion_label": fecha.strftime("%d/%m/%Y"),
        "tipo_pension_options": _TIPOS_PENSION,
        "familia": _familia_desde(lead, form_values, fecha),
        "resumen": resumen,
        "resultado": resultado,
        "escenario_descripcion": escenario.descripcion if escenario else "",
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


def _render_simulador(
    request: Request,
    lead_id: str,
    lead: dict[str, Any] | None,
    form: Mapping[str, Any],
    *,
    fecha_simulacion: date,
    errores: list[str] | None = None,
    resumen: dict[str, Any] | None = None,
    resultado: dict[str, Any] | None = None,
    escenario: Escenario | None = None,
    status_code: int = 200,
):
    context = _form_context(
        request,
        lead_id,
        lead,
        form_values=dict(form),
        simulador_errores=errores,
        fecha_simulacion=fecha_simulacion,
        resumen=resumen,
        resultado=resultado,
        escenario=escenario,
    )
    return request.app.state.templates.TemplateResponse(
        request, "simulador.html", context, status_code=status_code
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

    return _render_simulador(
        request, lead_id, lead, {}, fecha_simulacion=datetime.now(CRM_TZ).date()
    )


@router.post("/leads/{lead_id}/simulador")
async def simulador_accion(request: Request, lead_id: str):
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

    intent = str(form.get("intent") or "descargar_pdf").strip()
    if intent not in {"simular", "descargar_pdf"}:
        # Un formulario viejo (p. ej. con «continuar») o manipulado nunca genera PDF ni auditoría.
        intent = "simular"
    fecha_simulacion = datetime.now(CRM_TZ).date()

    # «Simular» y «Descargar PDF» validan todo el formulario y calculan en el servidor.
    try:
        simulador_form = _parse_simulador_form(form)
    except ValidationError as exc:
        return _render_simulador(
            request,
            lead_id,
            lead,
            form,
            fecha_simulacion=fecha_simulacion,
            errores=_validation_error_messages(exc),
            status_code=422,
        )

    sim_service = SimuladorService()
    try:
        causante = _causante_desde_lead(lead)
    except SimulacionInvalidaError as exc:
        return _render_simulador(
            request,
            lead_id,
            lead,
            form,
            fecha_simulacion=fecha_simulacion,
            errores=[str(exc)],
            status_code=422,
        )

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
        return _render_simulador(
            request,
            lead_id,
            lead,
            form,
            fecha_simulacion=fecha_simulacion,
            errores=[str(exc)],
            status_code=422,
        )

    # «Simular»: muestra el resultado en la misma pagina, sin persistir ni auditar (AC-4).
    if intent == "simular":
        return _render_simulador(
            request,
            lead_id,
            lead,
            form,
            fecha_simulacion=fecha_simulacion,
            resumen=_resumen_desde(simulador_form, fecha_simulacion),
            resultado=_resultado_desde(resultado, simulador_form),
            escenario=escenario,
        )

    # «Descargar PDF»: genera el PDF en memoria y registra el evento append-only de auditoría.
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
    # no se entrega el PDF). El detalle guarda las entradas y el resultado como evidencia
    # de solo escritura (SIM-EVIDENCIA-ENTRADAS).
    try:
        sim_service.record_event(
            id_lead=lead_id,
            actor=user,
            tipo_escenario=escenario.tipo,
            codigo=codigo,
            fecha_simulacion=fecha_simulacion,
            saldo_uf=simulador_form.saldo_uf,
            tasa_venta_pct=simulador_form.tasa_venta_pct,
            valor_uf=simulador_form.valor_uf,
            meses_garantizados=simulador_form.meses_garantizados,
            meses_aumento_temporal=simulador_form.meses_aumento_temporal,
            porcentaje_aumento_temporal=simulador_form.porcentaje_aumento_temporal,
            anios_diferidos=simulador_form.anios_diferidos,
            porcentaje_rvd=simulador_form.porcentaje_rvd,
            causante=causante,
            conyuge=conyuge,
            hijos=hijos,
            resultado=resultado,
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
