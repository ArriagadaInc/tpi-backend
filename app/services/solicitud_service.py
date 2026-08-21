"""
Business service for lead registration and lookup.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from app.database import DatabaseAppError
from app.database.errors import DevLeadCleanupBlockedError
from app.models.idempotency import IdempotencyConflictError, IdempotentSolicitudResult
from app.models.solicitud import (
    RegistrarSolicitudRequest,
    SolicitudResponse,
)
from app.models.test_lead_cleanup import TestLeadCleanupResult
from app.notifications import LeadCreatedEvent, LeadEventPublisher, build_lead_event_publisher
from app.repositories import SolicitudRepository
from app.security.masking import mask_row_for_display

logger = logging.getLogger(__name__)


class SolicitudService:
    """Business service for pension simulation requests."""

    _CRM_TZ = ZoneInfo("America/Santiago")

    def __init__(
        self,
        repository: SolicitudRepository | None = None,
        settings: Settings | None = None,
        publisher: LeadEventPublisher | None = None,
    ) -> None:
        self.repository = repository or SolicitudRepository()
        self.settings = settings or get_settings()
        self.publisher = publisher or build_lead_event_publisher(self.settings)

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
            response = self.repository.create_solicitud(
                persona_data=request.persona,
                solicitud_data=request.solicitud,
                consentimientos_data=request.consentimientos,
            )
            self._publish_lead_created_event(response.id_lead)
            return response
        except DatabaseAppError:
            raise
        except ValueError as exc:
            raise ValueError(f"Validacion de negocio fallida: {exc}") from exc
        except Exception as exc:
            raise RuntimeError("No fue posible registrar la solicitud.") from exc

    def registrar_solicitud_idempotente(
        self,
        request: RegistrarSolicitudRequest,
        *,
        idempotency_key: UUID,
        payload_fingerprint: str,
        expires_in: timedelta = timedelta(hours=24),
    ) -> IdempotentSolicitudResult:
        """Register a public lead once and publish only after its first commit."""
        try:
            self._validate_catalogo_ids(
                genero_id=request.solicitud.genero_id,
                estado_civil_id=request.solicitud.estado_civil_id,
                afp_id=request.solicitud.afp_id,
            )
            result = self.repository.create_solicitud_idempotent(
                persona_data=request.persona,
                solicitud_data=request.solicitud,
                consentimientos_data=request.consentimientos,
                idempotency_key=idempotency_key,
                payload_fingerprint=payload_fingerprint,
                expires_at=datetime.now(UTC) + expires_in,
            )
            if result.created:
                self._publish_lead_created_event(result.lead_id)
            return result
        except (DatabaseAppError, IdempotencyConflictError):
            raise
        except ValueError as exc:
            raise ValueError(f"Validacion de negocio fallida: {exc}") from exc
        except Exception as exc:
            raise RuntimeError("No fue posible registrar la solicitud.") from exc

    def _publish_lead_created_event(self, lead_id: UUID) -> None:
        """Best-effort event publication after the repository has committed the lead."""
        event = LeadCreatedEvent.create(
            lead_id=lead_id,
            environment=self.settings.normalized_app_env,
        )
        try:
            result = self.publisher.publish(event)
        except Exception:
            logger.error(
                "event=lead_notification_failed event_id=%s lead_id=%s environment=%s "
                "provider=unknown result=failed",
                event.event_id,
                event.lead_id,
                event.environment,
            )
            return

        if result.status == "published":
            logger.info(
                "event=lead_notification_published event_id=%s lead_id=%s environment=%s "
                "provider=%s result=success message_id=%s",
                event.event_id,
                event.lead_id,
                event.environment,
                result.provider,
                result.message_id,
            )
        elif result.status == "failed":
            logger.error(
                "event=lead_notification_failed event_id=%s lead_id=%s environment=%s "
                "provider=%s result=failed",
                event.event_id,
                event.lead_id,
                event.environment,
                result.provider,
            )

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

    def get_crm_bandeja(
        self,
        page: int = 1,
        page_size: int = 20,
        masked: bool = True,
        *,
        search: str | None = None,
        estado_lead: str | None = None,
        afp_id: UUID | None = None,
        genero_id: UUID | None = None,
        estado_civil_id: UUID | None = None,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
    ) -> dict[str, Any]:
        """Return a CRM-oriented lead board without changing the schema."""
        if page < 1:
            raise ValueError("page must be greater than zero")
        if page_size < 1:
            raise ValueError("page_size must be greater than zero")

        normalized_date_from = self._normalize_crm_date(date_from, end_of_day=False)
        normalized_date_to = self._normalize_crm_date(date_to, end_of_day=True)
        if (
            normalized_date_from
            and normalized_date_to
            and normalized_date_from > normalized_date_to
        ):
            raise ValueError("date_from cannot be greater than date_to")

        offset = (page - 1) * page_size
        solicitudes, total = self.repository.get_crm_solicitudes(
            limit=page_size,
            offset=offset,
            search=search,
            estado_lead=estado_lead,
            afp_id=afp_id,
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )

        if masked:
            solicitudes = [
                mask_row_for_display(
                    solicitud,
                    sensitive_fields=["rut", "email", "telefono"],
                )
                for solicitud in solicitudes
            ]

        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return {
            "solicitudes": solicitudes,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    @classmethod
    def _normalize_crm_date(
        cls,
        value: datetime | date | None,
        *,
        end_of_day: bool,
    ) -> datetime | None:
        """Normalize date filters to timezone-aware datetimes for TIMESTAMPTZ comparisons."""
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=cls._CRM_TZ)
            return value.astimezone(cls._CRM_TZ)

        local_time = time.max if end_of_day else time.min
        return datetime.combine(value, local_time, tzinfo=cls._CRM_TZ)

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
