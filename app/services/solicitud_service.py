"""
Business service for lead registration and lookup.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings
from app.database import DatabaseAppError
from app.database.errors import DevLeadCleanupBlockedError
from app.models.solicitud import (
    RegistrarSolicitudRequest,
    SolicitudResponse,
)
from app.models.test_lead_cleanup import TestLeadCleanupResult
from app.repositories import SolicitudRepository
from app.security.masking import mask_row_for_display

logger = logging.getLogger(__name__)


class SolicitudService:
    """Business service for pension simulation requests."""

    def __init__(
        self,
        repository: SolicitudRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository or SolicitudRepository()
        self.settings = settings or get_settings()

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

    def is_test_lead_cleanup_enabled(self) -> bool:
        """Return the effective cleanup capability, never enabled outside AWS DEV."""
        return self.settings.is_test_lead_cleanup_enabled

    def delete_test_lead(self, id_lead: UUID | str) -> TestLeadCleanupResult:
        """Safely clean a fictitious lead when AWS DEV explicitly permits it."""
        if not self.is_test_lead_cleanup_enabled():
            return TestLeadCleanupResult(
                status="denied",
                message="Esta operacion solo esta disponible en el ambiente de desarrollo.",
            )

        try:
            lead_id = UUID(str(id_lead))
        except (TypeError, ValueError, AttributeError):
            return TestLeadCleanupResult(
                status="invalid",
                message="El identificador de la solicitud no es valido.",
            )

        if not self.repository.test_lead_exists(lead_id):
            return TestLeadCleanupResult(
                status="not_found",
                message="El lead de prueba ya no existe.",
                lead_id=lead_id,
            )

        try:
            deleted = self.repository.delete_test_lead(lead_id)
        except DevLeadCleanupBlockedError:
            logger.warning(
                "event=test_lead_delete_failed environment=%s lead_id=%s result=blocked",
                self.settings.normalized_app_env,
                lead_id,
            )
            return TestLeadCleanupResult(
                status="blocked",
                message="No fue posible eliminar el lead porque tiene referencias operacionales.",
                lead_id=lead_id,
            )
        except (DatabaseAppError, RuntimeError):
            logger.error(
                "event=test_lead_delete_failed environment=%s lead_id=%s result=failed",
                self.settings.normalized_app_env,
                lead_id,
            )
            return TestLeadCleanupResult(
                status="failed",
                message="No fue posible eliminar el lead de prueba. Intenta nuevamente.",
                lead_id=lead_id,
            )

        if not deleted:
            return TestLeadCleanupResult(
                status="not_found",
                message="El lead de prueba ya no existe.",
                lead_id=lead_id,
            )

        logger.info(
            "event=test_lead_deleted environment=%s lead_id=%s result=success",
            self.settings.normalized_app_env,
            lead_id,
        )
        return TestLeadCleanupResult(
            status="deleted",
            message="Lead de prueba eliminado correctamente.",
            lead_id=lead_id,
        )

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
