"""Módulo de validadores."""

from app.validators.rut import (
    normalize_rut,
    validate_rut,
    format_rut_for_display,
    mask_rut,
    InvalidRUTError,
)
from app.validators.phone import (
    normalize_phone,
    validate_phone,
    format_phone_for_display,
    mask_phone,
    InvalidPhoneError,
)
from app.validators.email import (
    normalize_email,
    validate_email,
    mask_email,
    InvalidEmailError,
)

__all__ = [
    # RUT
    "normalize_rut",
    "validate_rut",
    "format_rut_for_display",
    "mask_rut",
    "InvalidRUTError",
    # Phone
    "normalize_phone",
    "validate_phone",
    "format_phone_for_display",
    "mask_phone",
    "InvalidPhoneError",
    # Email
    "normalize_email",
    "validate_email",
    "mask_email",
    "InvalidEmailError",
]
