"""Versioned public request and response contracts for lead registration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import ConsentimientosData, PersonaData, RegistrarSolicitudRequest, SolicitudData


class PublicLeadConsents(BaseModel):
    """The three explicit consents required to create a public lead."""

    acepta_terminos: bool
    acepta_politica_privacidad: bool
    finalidad_contacto: bool

    model_config = ConfigDict(extra="forbid")


class PublicLeadCreateRequest(BaseModel):
    """External v1 contract, deliberately independent from application models."""

    schema_version: Literal["1.0"] = "1.0"
    rut: str = Field(min_length=5, max_length=20)
    nombre_completo: str = Field(min_length=3, max_length=200)
    email: str = Field(max_length=254)
    telefono: str = Field(min_length=8, max_length=20)
    fecha_nacimiento: date
    genero_id: UUID
    estado_civil_id: UUID
    afp_id: UUID
    saldo_afp: Decimal = Field(ge=0, decimal_places=0)
    comentarios: str | None = Field(default=None, max_length=1000)
    consentimientos: PublicLeadConsents
    honeypot: str = Field(default="", max_length=200)

    model_config = ConfigDict(extra="forbid")

    def to_application_request(self) -> RegistrarSolicitudRequest:
        """Map this public contract explicitly to the shared application contract."""
        return RegistrarSolicitudRequest(
            persona=PersonaData(
                rut=self.rut,
                nombre_completo=self.nombre_completo,
                email=self.email,
                telefono=self.telefono,
                fecha_nacimiento=self.fecha_nacimiento,
            ),
            solicitud=SolicitudData(
                genero_id=self.genero_id,
                estado_civil_id=self.estado_civil_id,
                afp_id=self.afp_id,
                saldo_afp=self.saldo_afp,
                comentarios=self.comentarios,
            ),
            consentimientos=ConsentimientosData(
                acepta_terminos=self.consentimientos.acepta_terminos,
                acepta_politica_privacidad=self.consentimientos.acepta_politica_privacidad,
                finalidad_contacto=self.consentimientos.finalidad_contacto,
            ),
        )


class CatalogItem(BaseModel):
    id: UUID
    nombre: str


class PublicCatalogsResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generos: list[CatalogItem]
    estados_civiles: list[CatalogItem]
    afps: list[CatalogItem]


class PublicLeadCreateResponse(BaseModel):
    lead_id: UUID
    request_id: UUID
