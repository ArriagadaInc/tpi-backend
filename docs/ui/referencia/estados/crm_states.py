"""Canonical CRM lead state contract used by the web CRM and repository layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class CrmStateOption:
    value: str
    label: str


CRM_STATE_CONTRACT: Final[tuple[str, ...]] = (
    "nuevo",
    "asignado",
    "sin_contacto",
    "en_seguimiento",
    "reunion_agendada",
    "reunion_realizada",
    "ficha_generada",
    "cerrado",
    "no_interesado",
    "datos_erroneos",
    "no_contactado",
    "perdido",
)

CRM_STATE_LABELS: Final[dict[str, str]] = {
    "nuevo": "Nuevo",
    "asignado": "Asignado",
    "sin_contacto": "Sin contacto",
    "en_seguimiento": "En seguimiento",
    "reunion_agendada": "Reunión agendada",
    "reunion_realizada": "Reunión realizada",
    "ficha_generada": "Ficha generada",
    "cerrado": "Cerrado",
    "no_interesado": "No interesado",
    "datos_erroneos": "Datos erróneos",
    "no_contactado": "No contactado",
    "perdido": "Perdido",
}

CRM_STATE_TONES: Final[dict[str, str]] = {
    "nuevo": "info",
    "asignado": "info",
    "sin_contacto": "warning",
    "en_seguimiento": "info",
    "reunion_agendada": "success",
    "reunion_realizada": "success",
    "ficha_generada": "success",
    "cerrado": "success",
    "no_interesado": "error",
    "datos_erroneos": "warning",
    "no_contactado": "warning",
    "perdido": "error",
}

_STATE_DISPLAY_ALIASES: Final[dict[str, str]] = {
    "pendiente": "nuevo",
}

_STATE_FILTER_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "nuevo": ("nuevo", "pendiente"),
    **{state: (state,) for state in CRM_STATE_CONTRACT if state != "nuevo"},
}

CRM_STATE_OPTIONS: Final[tuple[CrmStateOption, ...]] = tuple(
    CrmStateOption(value=value, label=CRM_STATE_LABELS[value]) for value in CRM_STATE_CONTRACT
)


def iter_crm_state_options() -> list[CrmStateOption]:
    return list(CRM_STATE_OPTIONS)


def normalize_crm_state_for_display(value: str | None) -> str | None:
    if value is None:
        return None

    raw = " ".join(str(value).strip().split())
    if not raw:
        return None

    canonical = raw.casefold()
    if canonical in CRM_STATE_CONTRACT:
        return canonical

    resolved = _STATE_DISPLAY_ALIASES.get(canonical)
    if resolved is not None:
        return resolved

    if raw in CRM_STATE_CONTRACT:
        return raw

    return None


def crm_state_label(value: str | None) -> str:
    """Return the display label for canonical or approved historical states."""
    if value is None:
        return ""

    raw = " ".join(str(value).strip().split())
    if not raw:
        return ""

    canonical = normalize_crm_state_for_display(raw)
    if canonical is not None:
        return CRM_STATE_LABELS[canonical]
    return raw


def crm_state_tone(value: str | None) -> str:
    canonical = normalize_crm_state_for_display(value)
    if canonical is None:
        return "warning"
    return CRM_STATE_TONES.get(canonical, "warning")


def normalize_crm_state_for_filter(value: str | None) -> str | None:
    if value is None:
        return None

    raw = " ".join(str(value).strip().split())
    if not raw:
        return None

    canonical = normalize_crm_state_for_display(raw)
    if canonical is not None:
        return canonical

    fallback = raw.casefold()
    return fallback if fallback else None


def normalize_crm_state_for_write(value: str | None) -> str:
    if value is None:
        raise ValueError("Estado de lead invalido")

    normalized = " ".join(str(value).strip().split())
    if normalized in CRM_STATE_CONTRACT:
        return normalized

    raise ValueError("Estado de lead invalido")


def crm_state_filter_terms(value: str | None) -> tuple[str, ...]:
    canonical = normalize_crm_state_for_filter(value)
    if canonical is None:
        return tuple()
    return _STATE_FILTER_ALIASES.get(canonical, (canonical,))


def crm_state_aggregate_key(value: str | None) -> str | None:
    """Return a stable presentation key for legacy metrics and charts."""

    canonical = normalize_crm_state_for_display(value)
    if canonical is not None:
        return canonical

    if value is None:
        return None

    raw = " ".join(str(value).strip().split())
    return raw or None
