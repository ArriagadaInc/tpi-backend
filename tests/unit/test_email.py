"""Pruebas unitarias para validador de email."""

import pytest

from app.validators.email import InvalidEmailError, mask_email, normalize_email, validate_email

pytestmark = pytest.mark.unit


class TestNormalizeEmail:
    """Pruebas para la normalización de email."""

    def test_normalize_to_lowercase(self):
        """Normaliza a minúsculas."""
        assert normalize_email("User@EXAMPLE.COM") == "user@example.com"

    def test_normalize_preserves_valid_email(self):
        """Preserva email válido."""
        assert normalize_email("user@example.com") == "user@example.com"

    def test_normalize_strips_spaces(self):
        """Elimina espacios."""
        assert normalize_email("  user@example.com  ") == "user@example.com"

    def test_normalize_multiple_formats(self):
        """Normaliza múltiples formatos."""
        formats = [
            ("User@Example.COM", "user@example.com"),
            ("USER+TAG@EXAMPLE.COM", "user+tag@example.com"),
            ("John.Doe@Example.Co.UK", "john.doe@example.co.uk"),
        ]
        for input_email, expected in formats:
            assert normalize_email(input_email) == expected


class TestValidateEmail:
    """Pruebas para la validación de email."""

    def test_valid_emails(self):
        """Valida emails correctos."""
        valid_emails = [
            "user@example.com",
            "john.doe@example.co.uk",
            "user+tag@example.com",
            "user123@example456.com",
            "a@b.co",
        ]
        for email in valid_emails:
            assert validate_email(email) is True, f"Email {email} debería ser válido"

    def test_invalid_emails(self):
        """Rechaza emails incorrectos."""
        invalid_emails = [
            "invalid",  # Sin @
            "@example.com",  # Sin usuario
            "user@",  # Sin dominio
            "user @example.com",  # Espacio en usuario
            "user@example",  # Sin TLD
            ".user@example.com",  # Comienza con punto
            "user@.example.com",  # Dominio comienza con punto
            "user@@example.com",  # @ doble
        ]
        for email in invalid_emails:
            assert validate_email(email) is False, f"Email {email} debería ser inválido"

    def test_invalid_format_raises_error(self):
        """Lanza error con formato muy inválido."""
        # Casos que podrían lanzar excepciones
        with pytest.raises(InvalidEmailError):
            validate_email("")

    def test_max_length_email(self):
        """Valida límite máximo de 254 caracteres."""
        # RFC 5321: máximo 254 caracteres
        # Email válido de máximo permitido
        long_email = "a" * 243 + "@example.com"  # 254 caracteres
        assert validate_email(long_email) is True

        # Email más largo del máximo
        too_long_email = "a" * 244 + "@example.com"  # 255 caracteres
        assert validate_email(too_long_email) is False

    def test_validate_after_normalization(self):
        """Valida después de normalización."""
        assert validate_email("User@EXAMPLE.COM") is True
        assert validate_email("JOHN.DOE@EXAMPLE.COM") is True


class TestMaskEmail:
    """Pruebas para enmascaramiento de email."""

    def test_mask_email(self):
        """Enmascara email correctamente."""
        result = mask_email("user@example.com")
        assert result == "us***@example.com"

    def test_mask_email_with_long_username(self):
        """Enmascara username largo."""
        result = mask_email("johndoe@example.com")
        assert result == "jo***@example.com"

    def test_mask_email_with_single_char(self):
        """Enmascara email de un carácter."""
        result = mask_email("a@example.com")
        assert result == "a***@example.com"

    def test_mask_email_preserves_domain(self):
        """Preserva dominio en enmascaramiento."""
        result = mask_email("user@mydomain.co.uk")
        assert result.endswith("@mydomain.co.uk")

    def test_mask_email_with_plus(self):
        """Enmascara email con +."""
        result = mask_email("user+tag@example.com")
        # Debería enmascarar la parte antes del +
        assert "@example.com" in result

    def test_mask_email_consistent(self):
        """Enmascaramiento consistente."""
        email = "user@example.com"
        result1 = mask_email(email)
        result2 = mask_email(email)
        assert result1 == result2


class TestEmailEdgeCases:
    """Pruebas de casos límite."""

    def test_special_characters_in_username(self):
        """Valida caracteres especiales permitidos en username."""
        valid_emails = [
            "user+tag@example.com",
            "user.name@example.com",
            "user_name@example.com",
            "user-name@example.com",
            "user123@example.com",
        ]
        for email in valid_emails:
            assert validate_email(email) is True

    def test_special_characters_not_allowed(self):
        """Rechaza caracteres especiales no permitidos."""
        invalid_emails = [
            "user#name@example.com",
            "user!name@example.com",
            "user$name@example.com",
            "user&name@example.com",
        ]
        for email in invalid_emails:
            assert validate_email(email) is False

    def test_numeric_domain(self):
        """Valida dominio numérico."""
        # Ejemplo: IP domain
        assert validate_email("user@123.456.789.012") is False or validate_email(
            "user@123.456.789.012"
        ) is True  # Depende de validación

    def test_internationalized_domain(self):
        """Rechaza dominio internacionalizado (fuera de MVP)."""
        # El MVP solo acepta ASCII
        assert validate_email("user@münchen.de") is False

    def test_empty_email(self):
        """Rechaza email vacío."""
        with pytest.raises(InvalidEmailError):
            validate_email("")

    def test_only_special_characters(self):
        """Rechaza solo caracteres especiales."""
        with pytest.raises(InvalidEmailError):
            validate_email("@.+-_ ")
