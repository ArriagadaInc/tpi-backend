"""Pruebas unitarias para validador de teléfono chileno."""

import pytest

from app.validators.phone import (
    InvalidPhoneError,
    format_phone_for_display,
    mask_phone,
    normalize_phone,
    validate_phone,
)

pytestmark = pytest.mark.unit


class TestNormalizePhone:
    """Pruebas para la normalización de teléfono."""

    def test_normalize_with_plus_56(self):
        """Normaliza formato con +56."""
        assert normalize_phone("+56912345678") == "+56912345678"

    def test_normalize_09_format(self):
        """Normaliza formato con 09."""
        assert normalize_phone("0912345678") == "+56912345678"

    def test_normalize_spaces(self):
        """Normaliza formato con espacios."""
        assert normalize_phone("+56 9 1234 5678") == "+56912345678"

    def test_normalize_country_code_without_plus(self):
        """Normaliza código de país sin +."""
        assert normalize_phone("56912345678") == "+56912345678"

    def test_normalize_without_leading_zero(self):
        """Normaliza sin cero al principio."""
        assert normalize_phone("912345678") == "+56912345678"

    def test_normalize_strips_spaces(self):
        """Elimina espacios."""
        assert normalize_phone("  +56 9 1234 5678  ") == "+56912345678"

    def test_normalize_multiple_formats(self):
        """Normaliza múltiples formatos."""
        formats = [
            ("+56912345678", "+56912345678"),
            ("0912345678", "+56912345678"),
            ("912345678", "+56912345678"),
            ("56912345678", "+56912345678"),
            ("+56 9 1234 5678", "+56912345678"),
        ]
        for input_phone, expected in formats:
            assert normalize_phone(input_phone) == expected


class TestValidatePhone:
    """Pruebas para la validación de teléfono."""

    def test_valid_phones(self):
        """Valida teléfonos correctos."""
        valid_phones = [
            "+56912345678",
            "0912345678",
            "912345678",
            "56912345678",
            "+56912349999",
        ]
        for phone in valid_phones:
            assert validate_phone(phone) is True, f"Teléfono {phone} debería ser válido"

    def test_invalid_phones(self):
        """Rechaza teléfonos incorrectos."""
        invalid_phones = [
            "1234567",  # Muy corto
            "+569123456789",  # Muy largo
            "+56512345678",  # No es celular (5 en lugar de 9)
            "ABC1234567",  # Contiene letras
            "",  # Vacío
        ]
        for phone in invalid_phones:
            assert validate_phone(phone) is False, f"Teléfono {phone} debería ser inválido"

    def test_invalid_format_raises_error(self):
        """validate_phone retorna False; normalize_phone lanza la excepción."""
        assert validate_phone("ABCDEFGHIJ") is False
        with pytest.raises(InvalidPhoneError):
            normalize_phone("ABCDEFGHIJ")

    def test_validate_after_normalization(self):
        """Valida después de normalización."""
        assert validate_phone("+56 9 1234 5678") is True
        assert validate_phone("09 1234 5678") is True


class TestFormatPhoneForDisplay:
    """Pruebas para formateo de teléfono."""

    def test_format_phone_display(self):
        """Formatea teléfono para display."""
        assert format_phone_for_display("+56912345678") == "+56 9 1234 5678"

    def test_format_phone_standardized(self):
        """Formatea teléfono estandarizado."""
        result = format_phone_for_display("+56912349999")
        assert result == "+56 9 1234 9999"


class TestMaskPhone:
    """Pruebas para enmascaramiento de teléfono."""

    def test_mask_phone(self):
        """Enmascara teléfono correctamente."""
        result = mask_phone("+56912345678")
        assert result == "+56 9 **** 5678"

    def test_mask_phone_shows_edges(self):
        """Enmascara pero preserva principio y fin."""
        result = mask_phone("+56912349999")
        assert result.startswith("+56 9")
        assert result.endswith("9999")

    def test_mask_phone_consistent(self):
        """Enmascaramiento consistente."""
        phone = "+56912345678"
        result1 = mask_phone(phone)
        result2 = mask_phone(phone)
        assert result1 == result2


class TestPhoneEdgeCases:
    """Pruebas de casos límite."""

    def test_different_area_codes(self):
        """Valida diferentes formatos de código de área."""
        # En Chile el formato es +56 9 XXXX XXXX para celulares
        # No 56 2 XXXX XXXX para teléfonos fijos
        assert validate_phone("+56912345678") is True

    def test_very_long_phone(self):
        """validate_phone retorna False; normalize_phone lanza la excepción."""
        assert validate_phone("+569123456789123") is False
        with pytest.raises(InvalidPhoneError):
            normalize_phone("+569123456789123")

    def test_empty_phone(self):
        """validate_phone retorna False; normalize_phone lanza la excepción."""
        assert validate_phone("") is False
        with pytest.raises(InvalidPhoneError):
            normalize_phone("")

    def test_only_special_characters(self):
        """validate_phone retorna False; normalize_phone lanza la excepción."""
        assert validate_phone("+-() ") is False
        with pytest.raises(InvalidPhoneError):
            normalize_phone("+-() ")

    def test_phone_with_mixed_separators(self):
        """Normaliza múltiples separadores."""
        # Asumiendo que el normalizador es flexible
        phone = "+56-9-1234-5678"
        result = normalize_phone(phone)
        assert result == "+56912345678"
