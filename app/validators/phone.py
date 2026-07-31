"""
Validador de teléfono chileno.

Normaliza a formato internacional +56 XXXXXXXXXX
"""

import re


class InvalidPhoneError(ValueError):
    """Excepción para teléfono inválido."""
    pass


def normalize_phone(phone: str) -> str:
    """
    Normalizar teléfono chileno a formato internacional +56.
    
    Acepta formatos:
    - +56 9 1234 5678
    - 56912345678
    - 09 1234 5678
    - 91234 5678
    - +56912345678
    
    Retorna: +56912345678
    
    Args:
        phone: Teléfono en cualquier formato
    
    Returns:
        Teléfono normalizado (+56XXXXXXXXXX)
    
    Raises:
        InvalidPhoneError: Si el teléfono no es válido
    """
    # Eliminar espacios, paréntesis, guiones
    phone = re.sub(r"[\s\(\)\-]", "", phone.strip())
    
    # Convertir a string
    phone = str(phone)
    
    # Validar que solo contenga dígitos (después de procesar)
    if not re.match(r"^\+?56\d{9,10}$|^\d{9,10}$", phone):
        raise InvalidPhoneError("Formato de teléfono inválido")
    
    # Si empieza con +56, ya está normalizado
    if phone.startswith("+56"):
        return phone
    
    # Si empieza con 56 (sin +)
    if phone.startswith("56"):
        return f"+{phone}"
    
    # Si empieza con 0, reemplazar por +56
    if phone.startswith("0"):
        return f"+56{phone[1:]}"
    
    # Si empieza con 9 (celular sin 0), agregar +56
    if len(phone) == 9 and phone.startswith("9"):
        return f"+56{phone}"
    
    # Si es un número de 9-10 dígitos sin prefijo
    if len(phone) in [9, 10]:
        return f"+56{phone}"
    
    raise InvalidPhoneError("No se pudo normalizar el teléfono")


def validate_phone(phone: str) -> bool:
    """
    Validar que el teléfono sea chileno válido.
    
    Args:
        phone: Teléfono en cualquier formato
    
    Returns:
        True si es válido, False en caso contrario
    
    Raises:
        InvalidPhoneError: Si el formato es claramente inválido
    """
    try:
        normalized = normalize_phone(phone)
        # Debe tener exactamente +56 + 9 dígitos (celular) o +56 + 10 dígitos (fijo)
        digits = re.sub(r"\D", "", normalized)
        return len(digits) >= 11  # +56 = 2 dígitos + 9-10 locales
    except InvalidPhoneError:
        return False


def format_phone_for_display(phone: str) -> str:
    """
    Formatear teléfono para visualización: +56 9 XXXX XXXX
    
    Args:
        phone: Teléfono en cualquier formato
    
    Returns:
        Teléfono formateado (+56 9 XXXX XXXX)
    """
    try:
        normalized = normalize_phone(phone)
        # +56912345678 → +56 9 1234 5678
        digits = re.sub(r"\D", "", normalized)
        if len(digits) == 11:  # +56 + 9 dígitos
            return f"+{digits[0:2]} {digits[2]} {digits[3:7]} {digits[7:]}"
        elif len(digits) == 12:  # +56 + 10 dígitos
            return f"+{digits[0:2]} {digits[2:4]} {digits[4:8]} {digits[8:]}"
        return normalized
    except Exception:
        return phone


def mask_phone(phone: str) -> str:
    """
    Enmascarar teléfono para visualización segura: +56 9 **** XXXX
    
    Ejemplo: +56 9 1234 5678 → +56 9 **** 5678
    
    Args:
        phone: Teléfono en cualquier formato
    
    Returns:
        Teléfono enmascarado
    """
    try:
        normalized = normalize_phone(phone)
        digits = re.sub(r"\D", "", normalized)
        
        if len(digits) == 11:  # Celular
            # +56 9 **** 5678
            return f"+{digits[0:2]} {digits[2]} **** {digits[-4:]}"
        elif len(digits) == 12:  # Fijo
            # +56 XX **** XXXX
            return f"+{digits[0:2]} {digits[2:4]} **** {digits[-4:]}"
        return "***-****"
    except Exception:
        return "***-****"
