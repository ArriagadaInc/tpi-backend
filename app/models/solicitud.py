"""
Modelos Pydantic para la solicitud de simulación.

Define la estructura de datos esperada y validación a nivel de modelo.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.validators import normalize_email, normalize_phone, normalize_rut


class PersonaData(BaseModel):
    """Datos de la persona para crear o actualizar."""

    rut: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="RUT sin normalizar (se normalizará al insertar)",
    )
    nombre_completo: str = Field(
        ..., min_length=3, max_length=200, description="Nombre completo de la persona"
    )
    email: str = Field(..., max_length=254, description="Correo electrónico")
    telefono: str = Field(
        ...,
        min_length=8,
        max_length=20,
        description="Teléfono (se normalizará al formato +56)",
    )
    fecha_nacimiento: date = Field(..., description="Fecha de nacimiento")

    @field_validator("rut", mode="before")
    @classmethod
    def normalize_rut_field(cls, v: str) -> str:
        """Normalizar RUT al recibir."""
        if isinstance(v, str):
            return normalize_rut(v)
        return v

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: str) -> str:
        """Normalizar email al recibir."""
        if isinstance(v, str):
            return normalize_email(v)
        return v

    @field_validator("telefono", mode="before")
    @classmethod
    def normalize_phone_field(cls, v: str) -> str:
        """Normalizar teléfono al recibir."""
        if isinstance(v, str):
            return normalize_phone(v)
        return v

    @field_validator("nombre_completo", mode="before")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        """Normalizar nombre: eliminar espacios extra y rechazar bytes nulos."""
        if isinstance(v, str):
            if "\x00" in v:
                raise ValueError("El nombre no puede contener bytes nulos")
            # Eliminar espacios iniciales/finales y espacios múltiples
            return " ".join(v.strip().split())
        return v

    @field_validator("fecha_nacimiento")
    @classmethod
    def validate_birth_date(cls, v: date) -> date:
        """Validar que la fecha no sea futura."""
        from datetime import date as date_class

        today = date_class.today()
        if v > today:
            raise ValueError("La fecha de nacimiento no puede ser futura")

        # Validar edad razonable (1920-2015)
        if v.year < 1920:
            raise ValueError("Fecha de nacimiento demasiado antigua")
        if v.year > 2015:
            raise ValueError("Debes tener al menos 18 años para solicitar simulación")

        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rut": "12345678-5",
                "nombre_completo": "Juan Pérez García",
                "email": "juan@example.com",
                "telefono": "+56912345678",
                "fecha_nacimiento": "1985-06-15",
            }
        }
    )


class SolicitudData(BaseModel):
    """Datos de la solicitud de simulación."""

    # Referencia a catálogos (UUID)
    genero_id: UUID = Field(..., description="ID de genero desde catalogo_genero")
    estado_civil_id: UUID = Field(..., description="ID de estado civil desde catalogo_estado_civil")
    afp_id: UUID = Field(..., description="ID de AFP desde catalogo_afp")

    # Datos previsionales
    saldo_afp: Decimal = Field(
        ...,
        ge=0,
        decimal_places=0,
        description="Saldo acumulado en AFP (pesos chilenos, sin decimales)",
    )
    comentarios: str | None = Field(
        default=None, max_length=1000, description="Comentarios adicionales (opcional)"
    )

    @field_validator("comentarios", mode="before")
    @classmethod
    def normalize_comments(cls, v: str | None) -> str | None:
        """Normalizar comentarios: eliminar espacios extra."""
        if v is None:
            return None
        if isinstance(v, str):
            text = " ".join(v.strip().split())
            return text if text else None
        return v

    @field_validator("saldo_afp", mode="before")
    @classmethod
    def parse_saldo(cls, v) -> Decimal:
        """Convertir saldo a Decimal."""
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        elif isinstance(v, str):
            return Decimal(v.replace("$", "").replace(",", "").strip())
        elif isinstance(v, Decimal):
            return v
        raise ValueError("Saldo debe ser numérico")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "genero_id": "cbfc6550-0873-4f1b-b992-682650aa50b1",
                "estado_civil_id": "c1b6a6cf-2a60-4781-a0de-f92844ce4608",
                "afp_id": "b8ba2d12-2de0-41a5-8349-77cda60a14b6",
                "saldo_afp": 5000000,
                "comentarios": "Interesado en simular retiro programado",
            }
        }
    )


class ConsentimientosData(BaseModel):
    """Datos de consentimientos."""

    acepta_terminos: bool = Field(..., description="Acepta términos y condiciones")
    acepta_politica_privacidad: bool = Field(..., description="Acepta política de privacidad")
    finalidad_contacto: bool = Field(..., description="Autoriza contacto para fines comerciales")

    @model_validator(mode="before")
    @classmethod
    def validate_all_accepted(cls, data: Any) -> Any:
        """Validar que todos los consentimientos sean aceptados."""
        if not isinstance(data, dict):
            return data
        if not data.get("acepta_terminos"):
            raise ValueError("Debes aceptar los términos y condiciones")
        if not data.get("acepta_politica_privacidad"):
            raise ValueError("Debes aceptar la política de privacidad")
        if not data.get("finalidad_contacto"):
            raise ValueError("Debes autorizar el contacto para fines comerciales")
        return data

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "acepta_terminos": True,
                "acepta_politica_privacidad": True,
                "finalidad_contacto": True,
            }
        }
    )


class RegistrarSolicitudRequest(BaseModel):
    """Request completo para registrar una solicitud."""

    persona: PersonaData
    solicitud: SolicitudData
    consentimientos: ConsentimientosData

    model_config = ConfigDict(
        json_schema_extra={
            "description": "Solicitud completa de simulación con persona, datos previsionales y consentimientos"
        }
    )


class SolicitudResponse(BaseModel):
    """Response después de registrar una solicitud."""

    id_lead: UUID = Field(description="ID de la solicitud generado por PostgreSQL")
    id_persona: UUID = Field(description="ID de la persona generado por PostgreSQL")
    rut: str = Field(description="RUT de la persona (formato canónico)")
    nombre_completo: str = Field(description="Nombre de la persona")
    fecha_creacion: datetime = Field(description="Fecha y hora de creación (UTC)")
    estado_lead: str = Field(description="Estado inicial de la solicitud: 'recibida'")
    mensaje: str = Field(description="Mensaje de confirmación para el usuario")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id_lead": "550e8400-e29b-41d4-a716-446655440000",
                "id_persona": "550e8400-e29b-41d4-a716-446655440001",
                "rut": "12345678-5",
                "nombre_completo": "Juan Pérez García",
                "fecha_creacion": "2026-07-31T10:30:00Z",
                "estado_lead": "recibida",
                "mensaje": "Solicitud registrada correctamente",
            }
        }
    )
