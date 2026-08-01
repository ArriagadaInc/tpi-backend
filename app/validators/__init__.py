"""Módulo de validadores."""

from app.validators.email import (
    InvalidEmailError,
    mask_email,
    normalize_email,
    validate_email,
)
from app.validators.phone import (
    InvalidPhoneError,
    format_phone_for_display,
    mask_phone,
    normalize_phone,
    validate_phone,
)
from app.validators.rut import (
    InvalidRUTError,
    format_rut_for_display,
    mask_rut,
    normalize_rut,
    validate_rut,
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
