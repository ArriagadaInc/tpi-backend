"""
Enmascaramiento de datos personales sensibles.

Funciones para ocultar datos sensibles en vistas públicas de Streamlit.
El enmascaramiento es únicamente visual; los datos originales no se modifican.
"""

from app.validators import mask_email, mask_phone, mask_rut


def mask_sensitive_data(data: dict, fields_to_mask: list[str]) -> dict:
    """
    Enmascarar campos sensibles en un diccionario.

    Args:
        data: Diccionario con datos
        fields_to_mask: Lista de nombres de campos a enmascarar

    Returns:
        Diccionario con los campos enmascarados (copia)

    Ejemplo:
        data = {"rut": "12345678-5", "nombre": "Juan", "telefono": "+56912345678"}
        masked = mask_sensitive_data(data, ["rut", "telefono"])
        # masked = {"rut": "12.***.***-5", "nombre": "Juan", "telefono": "+56 9 **** 5678"}
    """
    masked = data.copy()

    for field in fields_to_mask:
        if field not in masked:
            continue

        value = masked[field]
        if value is None:
            continue

        # Aplicar enmascaramiento según el tipo de campo
        if "rut" in field.lower():
            masked[field] = mask_rut(str(value))
        elif "telefono" in field.lower() or "phone" in field.lower():
            masked[field] = mask_phone(str(value))
        elif "email" in field.lower() or "correo" in field.lower():
            masked[field] = mask_email(str(value))

    return masked


def mask_row_for_display(row: dict, sensitive_fields: list[str] | None = None) -> dict:
    """
    Preparar un registro (fila) para mostrar en tabla de Streamlit.

    Enmascarar campos sensibles automáticamente según el nombre del campo.

    Args:
        row: Registro de la BD
        sensitive_fields: Lista de campos a ocultar (si None, detectar automáticamente)

    Returns:
        Registro con campos sensibles enmascarados

    Ejemplo:
        row = {
            "id_lead": "uuid-xxx",
            "nombre_completo": "Juan Pérez",
            "rut": "12345678-5",
            "email": "juan@example.com",
            "telefono": "+56912345678",
            "saldo_afp": 5000000,
            "estado_lead": "recibida"
        }
        display_row = mask_row_for_display(row)
        # Automáticamente enmascarará rut, email, telefono
    """
    if sensitive_fields is None:
        # Detectar automáticamente campos sensibles
        sensitive_fields = [
            k
            for k in row.keys()
            if any(s in k.lower() for s in ["rut", "telefono", "phone", "email", "correo"])
        ]

    return mask_sensitive_data(row, sensitive_fields)


def unmask_for_detail(row: dict) -> dict:
    """
    Retornar registro sin enmascaramiento para vista de detalle.

    Solo se debe usar en vistas de detalle de solo lectura, con adver advencia
    de que esta información requiere autenticación en producción.

    Args:
        row: Registro enmascarado o no

    Returns:
        Registro original (sin enmascaramiento)
    """
    # En esta versión, simplemente retorna el registro
    # Los datos nunca se enmascararon de manera destructiva
    return row.copy()
