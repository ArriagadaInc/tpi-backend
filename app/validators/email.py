"""
Validador de correo electrónico.

Validación básica de estructura (sin verificación de entrega).
"""

import re


class InvalidEmailError(ValueError):
    """Excepción para email inválido."""
    pass


def normalize_email(email: str) -> str:
    """
    Normalizar correo electrónico.
    
    - Eliminar espacios
    - Convertir a minúsculas
    - Validar estructura básica
    
    Args:
        email: Correo electrónico
    
    Returns:
        Correo normalizado (minúsculas, sin espacios)
    
    Raises:
        InvalidEmailError: Si el formato es inválido
    """
    email = email.strip().lower()
    
    # Validar estructura básica
    if not re.match(r"^[a-z0-9][a-z0-9._%-]*@[a-z0-9.-]+\.[a-z]{2,}$", email):
        raise InvalidEmailError("Formato de correo electrónico inválido")
    
    # Validar longitud
    if len(email) > 254:
        raise InvalidEmailError("Correo electrónico demasiado largo (máx 254 caracteres)")
    
    # Validar que no contenga espacios
    if " " in email:
        raise InvalidEmailError("El correo electrónico no puede contener espacios")
    
    return email


def validate_email(email: str) -> bool:
    """
    Validar que el correo sea válido.
    
    Args:
        email: Correo electrónico
    
    Returns:
        True si es válido, False en caso contrario
    """
    try:
        normalize_email(email)
        return True
    except InvalidEmailError:
        return False


def mask_email(email: str) -> str:
    """
    Enmascarar correo para visualización segura.
    
    Ejemplo: usuario@dominio.cl → us***@dominio.cl
    
    Args:
        email: Correo electrónico
    
    Returns:
        Correo enmascarado
    """
    try:
        email = email.lower()
        if "@" not in email:
            return "***@***"
        
        usuario, dominio = email.split("@")
        
        # Mostrar primeros 2 caracteres del usuario
        if len(usuario) <= 2:
            usuario_enmascarado = usuario
        else:
            usuario_enmascarado = usuario[:2] + "***"
        
        return f"{usuario_enmascarado}@{dominio}"
    except Exception:
        return "***@***"
