"""
Validador de RUT chileno.

Implementa validación del dígito verificador usando módulo 11.
"""

import re
from typing import Tuple


class InvalidRUTError(ValueError):
    """Excepción para RUT inválido."""
    pass


def normalize_rut(rut: str) -> str:
    """
    Normalizar RUT a formato canónico.
    
    Acepta formatos:
    - 12345678-K
    - 12.345.678-K
    - 12345678k
    
    Retorna formato: 12345678-K
    
    Args:
        rut: RUT en cualquier formato
    
    Returns:
        RUT normalizado (sin puntos, con guion antes del dígito verificador)
    
    Raises:
        InvalidRUTError: Si el RUT no es válido
    """
    # Eliminar espacios
    rut = rut.strip()
    
    # Eliminar puntos
    rut = rut.replace(".", "")
    
    # Separar número y dígito verificador
    if "-" in rut:
        partes = rut.split("-")
        if len(partes) != 2:
            raise InvalidRUTError("Formato de RUT inválido")
        numero_str, dv_input = partes[0], partes[1].upper()
    else:
        # Sin guion: asumir últimos 1-2 caracteres son el dígito verificador
        if len(rut) < 2:
            raise InvalidRUTError("RUT demasiado corto")
        numero_str = rut[:-1]
        dv_input = rut[-1].upper()
    
    # Validar que la parte numérica sea solo dígitos
    if not numero_str.isdigit():
        raise InvalidRUTError("La parte numérica del RUT debe contener solo dígitos")
    
    # Validar que el dígito verificador sea válido (K o 0-9)
    if not (dv_input.isdigit() or dv_input == "K"):
        raise InvalidRUTError("Dígito verificador inválido")
    
    return f"{numero_str}-{dv_input}"


def validate_rut(rut: str) -> bool:
    """
    Validar RUT chileno verificando el dígito verificador.
    
    Args:
        rut: RUT en cualquier formato
    
    Returns:
        True si el RUT es válido, False en caso contrario
    
    Raises:
        InvalidRUTError: Si el formato es inválido
    """
    # Normalizar
    rut_normalizado = normalize_rut(rut)
    numero_str, dv_input = rut_normalizado.split("-")
    
    # Calcular dígito verificador correcto
    numero = int(numero_str)
    dv_calculado = _calculate_dv(numero)
    
    # Comparar
    return dv_input == dv_calculado


def _calculate_dv(numero: int) -> str:
    """
    Calcular dígito verificador usando módulo 11.
    
    Args:
        numero: Número RUT sin dígito verificador
    
    Returns:
        Dígito verificador (0-9 o K)
    """
    multiplicadores = [2, 3, 4, 5, 6, 7]
    suma = 0
    indice = 0
    
    # Procesar número de derecha a izquierda
    for digito in str(numero)[::-1]:
        suma += int(digito) * multiplicadores[indice % 6]
        indice += 1
    
    resto = suma % 11
    dv = 11 - resto
    
    if dv == 11:
        return "0"
    elif dv == 10:
        return "K"
    else:
        return str(dv)


def format_rut_for_display(rut: str) -> str:
    """
    Formatear RUT para visualización: XX.XXX.XXX-X
    
    Args:
        rut: RUT normalizado (12345678-K)
    
    Returns:
        RUT formateado (12.345.678-K)
    """
    try:
        rut_normalizado = normalize_rut(rut)
        numero, dv = rut_normalizado.split("-")
        
        # Agregar puntos al número
        numero_rev = numero[::-1]
        partes = [
            numero_rev[0:3][::-1],
            numero_rev[3:6][::-1],
            numero_rev[6:][::-1],
        ]
        numero_formateado = ".".join(p for p in partes if p)
        
        return f"{numero_formateado}-{dv}"
    except Exception:
        # Si hay error, retornar como está
        return rut


def mask_rut(rut: str) -> str:
    """
    Enmascarar RUT para visualización segura: XX.***. ***-X
    
    Ejemplo: 12.345.678-5 → 12.***.***-5
    
    Args:
        rut: RUT normalizado o formateado
    
    Returns:
        RUT enmascarado
    """
    try:
        rut_normalizado = normalize_rut(rut)
        numero, dv = rut_normalizado.split("-")
        
        if len(numero) <= 4:
            # RUT muy corto, no enmascarar
            return rut_normalizado
        
        # Mostrar primeros 2 dígitos y el dígito verificador
        primeros = numero[:2]
        return f"{primeros}.***.***-{dv}"
    except Exception:
        return "***.***-*"
