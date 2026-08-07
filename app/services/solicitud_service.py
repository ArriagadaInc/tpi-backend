"""
Business service for lead registration and lookup.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.database import DatabaseAppError
from app.models.solicitud import (
    RegistrarSolicitudRequest,
    SolicitudResponse,
)
from app.repositories import SolicitudRepository
from app.security.masking import mask_row_for_display


class SolicitudService:
    """Business service for pension simulation requests."""

    def __init__(self) -> None:
        self.repository = SolicitudRepository()

    def registrar_solicitud(self, request: RegistrarSolicitudRequest) -> SolicitudResponse:
        """
        Register a validated request and persist it atomically.
        """
        try:
            self._validate_catalogo_ids(
                genero_id=request.solicitud.genero_id,
                estado_civil_id=request.solicitud.estado_civil_id,
                afp_id=request.solicitud.afp_id,
            )
            return self.repository.create_solicitud(
                persona_data=request.persona,
                solicitud_data=request.solicitud,
                consentimientos_data=request.consentimientos,
            )
        except DatabaseAppError:
            raise
        except ValueError as exc:
            raise ValueError(f"Validacion de negocio fallida: {exc}") from exc
        except Exception as exc:
            raise RuntimeError("No fue posible registrar la solicitud.") from exc

    def get_solicitud_detalle(self, id_lead: UUID) -> dict[str, Any] | None:
        return self.repository.get_solicitud_by_id(id_lead)

    def get_solicitud_detalle_masked(self, id_lead: UUID) -> dict[str, Any] | None:
        solicitud = self.repository.get_solicitud_by_id(id_lead)
        if not solicitud:
            return None

        return mask_row_for_display(
            solicitud,
            sensitive_fields=["rut", "email", "telefono"],
        )

    def get_solicitudes_lista(
        self,
        page: int = 1,
        page_size: int = 10,
        masked: bool = True,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        solicitudes, total = self.repository.get_all_solicitudes(limit=page_size, offset=offset)

        if masked:
            solicitudes = [
                mask_row_for_display(
                    solicitud,
                    sensitive_fields=["rut", "email", "telefono"],
                )
                for solicitud in solicitudes
            ]

        total_pages = (total + page_size - 1) // page_size

        return {
            "solicitudes": solicitudes,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def get_solicitudes_por_rut(self, rut: str, masked: bool = True) -> list[dict[str, Any]]:
        solicitudes = self.repository.get_solicitudes_by_rut(rut)

        if masked:
            solicitudes = [
                mask_row_for_display(
                    solicitud,
                    sensitive_fields=["rut", "email", "telefono"],
                )
                for solicitud in solicitudes
            ]

        return solicitudes

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        return self.repository.get_active_afp()

    def get_catalogo_genero(self) -> list[dict[str, Any]]:
        return self.repository.get_active_genero()

    def get_catalogo_estado_civil(self) -> list[dict[str, Any]]:
        return self.repository.get_active_estado_civil()

    def _validate_catalogo_ids(self, genero_id: UUID, estado_civil_id: UUID, afp_id: UUID) -> None:
        generos = self.repository.get_active_genero()
        estados_civiles = self.repository.get_active_estado_civil()
        afps = self.repository.get_active_afp()

        genero_ids = {UUID(str(genero["id"])) for genero in generos}
        if genero_id not in genero_ids:
            raise ValueError(f"ID de genero invalido: {genero_id}")

        estado_civil_ids = {UUID(str(estado["id"])) for estado in estados_civiles}
        if estado_civil_id not in estado_civil_ids:
            raise ValueError(f"ID de estado civil invalido: {estado_civil_id}")

        afp_ids = {UUID(str(afp["id"])) for afp in afps}
        if afp_id not in afp_ids:
            raise ValueError(f"ID de AFP invalido: {afp_id}")
