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
    "prospecto",
    "asignado",
    "contactado",
    "citado",
    "en_tramite",
    "expediente",
    "ficha_generada",
    "cerrado",
    "perdido",
    "no_califica",
    "duplicado",
    "dormido",
)

CRM_STATE_LABELS: Final[dict[str, str]] = {
    "nuevo": "Nuevo",
    "prospecto": "Prospecto",
    "asignado": "Asignado",
    "contactado": "Contactado",
    "citado": "Citado",
    "en_tramite": "En trámite",
    "expediente": "Expediente",
    "ficha_generada": "Ficha generada",
    "cerrado": "Cerrado",
    "perdido": "Perdido",
    "no_califica": "No califica",
    "duplicado": "Duplicado",
    "dormido": "Dormido",
}

CRM_STATE_TONES: Final[dict[str, str]] = {
    "nuevo": "info",
    "prospecto": "info",
    "asignado": "info",
    "contactado": "info",
    "citado": "warning",
    "en_tramite": "warning",
    "expediente": "warning",
    "ficha_generada": "success",
    "cerrado": "success",
    "perdido": "error",
    "no_califica": "error",
    "duplicado": "warning",
    "dormido": "warning",
}

_STATE_DISPLAY_ALIASES: Final[dict[str, str]] = {
    "pendiente": "nuevo",
    "citado": "citado",
    "en trámite": "en_tramite",
    "en_tramite": "en_tramite",
    "cerrado": "cerrado",
}

_STATE_FILTER_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "nuevo": ("nuevo", "pendiente"),
    "prospecto": ("prospecto",),
    "asignado": ("asignado",),
    "contactado": ("contactado",),
    "citado": ("citado",),
    "en_tramite": ("en_tramite", "en trámite"),
    "expediente": ("expediente",),
    "ficha_generada": ("ficha_generada",),
    "cerrado": ("cerrado",),
    "perdido": ("perdido",),
    "no_califica": ("no_califica",),
    "duplicado": ("duplicado",),
    "dormido": ("dormido",),
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
