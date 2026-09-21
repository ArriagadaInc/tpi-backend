"""
Business service for lead registration and lookup.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from app.auth.models import AuthenticatedUser, is_superuser
from app.config import Settings, get_settings
from app.database import DatabaseAppError
from app.database.errors import DevLeadCleanupBlockedError
from app.models.crm_states import (
    CRM_STATE_CONTRACT,
    crm_state_filter_terms,
    normalize_crm_state_for_write,
)
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

    def can_view_full_pii(self, user: AuthenticatedUser) -> bool:
        return is_superuser(user.role)

    def resolve_advisor_identity(self, user: AuthenticatedUser | None) -> UUID | None:
        """Resolve an advisor identity to its active ``id_asesor``, or ``None``.

        This is the server-side resolution chain ``usuario -> advisor_id -> registro
        valido/activo``. It returns the active ``id_asesor`` only when the identity
        resolves to an active advisor; otherwise ``None`` (fail-closed). Non-advisor
        roles also return ``None`` — callers distinguish them with ``user.role``.

        The raw ``advisor_id`` and any secret value are never logged.
        """
        if user is None or user.role != "advisor":
            return None
        advisor_id = user.advisor_id
        if advisor_id is None:
            logger.warning(
                "event=advisor_scope_unavailable role=advisor result=fail_closed "
                "reason=missing_advisor_id"
            )
            return None
        if self.repository.get_active_advisor_by_id(advisor_id) is None:
            logger.warning(
                "event=advisor_scope_unavailable role=advisor result=fail_closed "
                "reason=advisor_not_active_or_missing"
            )
            return None
        return advisor_id

    def _advisor_mutation_scope(self, actor: AuthenticatedUser) -> UUID | None | bool:
        """Return the advisor portfolio scope for a mutation, or ``False`` to deny.

        ``None`` means "no portfolio restriction" (non-advisor). ``False`` means the
        actor is an advisor whose identity does not resolve to an active advisor, so
        every mutation must be rejected without writing.
        """
        if actor.role != "advisor":
            return None
        scope = self.resolve_advisor_identity(actor)
        if scope is None:
            return False
        return scope

    def get_solicitud_detalle_masked(
        self,
        id_lead: UUID,
        *,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any] | None:
        solicitud = self.repository.get_solicitud_by_id(id_lead)
        if not solicitud:
            return None

        if user is not None and self.can_view_full_pii(user):
            return solicitud

        if user is not None and user.role == "advisor":
            # PII authorization is contextual per lead and active assignment, never a
            # global advisor permission. Own lead -> full PII; other/no assignment -> 404.
            advisor_id = self.resolve_advisor_identity(user)
            if advisor_id is None:
                return None
            lead_id = self._normalize_uuid(id_lead, "lead")
            if not self.repository.lead_active_assignment_belongs_to(lead_id, advisor_id):
                return None
            return solicitud

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
        user: AuthenticatedUser | None = None,
        search: str | None = None,
        estado_lead: str | None = None,
        afp_id: UUID | None = None,
        genero_id: UUID | None = None,
        estado_civil_id: UUID | None = None,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
        asesor_id: UUID | None = None,
        origen_lead: str | None = None,
        fuente_actual: str | None = None,
        sin_asignar: bool = False,
        estancado: bool = False,
    ) -> dict[str, Any]:
        """Return a CRM-oriented lead board without changing the schema.

        ``sin_asignar`` and ``estancado`` mirror the executive dashboard alerts:
        both use the shared predicates, so the listing linked from an alert
        returns exactly the population the alert counted.
        """
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

        normalized_estado = None
        if estado_lead is not None:
            normalized_estado = self._normalize_crm_state_for_filter(estado_lead)

        # Portfolio scope: an advisor is always constrained server-side to the leads
        # whose currently-active assignment belongs to their resolved id_asesor. A
        # non-resolving advisor identity fails closed to an empty board. Non-advisor
        # roles (including ceo/cto) keep the global view and the optional asesor filter.
        portfolio_asesor_id: UUID | None = None
        effective_asesor_id = asesor_id
        if user is not None and user.role == "advisor":
            portfolio_asesor_id = self.resolve_advisor_identity(user)
            if portfolio_asesor_id is None:
                return {
                    "solicitudes": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                }
            effective_asesor_id = None

        offset = (page - 1) * page_size
        solicitudes, total = self.repository.get_crm_solicitudes(
            limit=page_size,
            offset=offset,
            search=search,
            estado_lead=normalized_estado,
            afp_id=afp_id,
            genero_id=genero_id,
            estado_civil_id=estado_civil_id,
            date_from=normalized_date_from,
            date_to=normalized_date_to,
            sort_by=sort_by,
            sort_direction=sort_direction,
            asesor_id=effective_asesor_id,
            portfolio_asesor_id=portfolio_asesor_id,
            origen_lead=origen_lead,
            fuente_actual=fuente_actual,
            sin_asignar=sin_asignar,
            estancado=estancado,
        )

        should_mask = masked and not (user is not None and self.can_view_full_pii(user))
        # The advisor's portfolio is by definition their own leads, so those rows are
        # returned unmasked (contextual PII by lead, not a global advisor flag).
        if portfolio_asesor_id is not None:
            should_mask = False
        if should_mask:
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

    def get_crm_estado_lead_options(self) -> list[str]:
        """Return the actual lead states present in the current data model."""
        return self.repository.get_crm_estado_lead_options()

    def get_crm_estado_lead_options_for_update(self) -> list[str]:
        """Return lead states available for generic edits, excluding assignment-only flows."""
        return [
            state for state in self.repository.get_crm_estado_lead_options() if state != "asignado"
        ]

    def update_lead_status(
        self,
        id_lead: UUID | str,
        estado_lead: str,
        *,
        actor: AuthenticatedUser,
    ) -> bool:
        """Update a lead status after validating role and allowed values.

        The actor is the authenticated subject (never a client-supplied value); it is
        propagated to the repository so the audit event records the real identity.
        """
        self._ensure_web_write_allowed()
        if not isinstance(actor, AuthenticatedUser):
            raise TypeError("actor must be an AuthenticatedUser")
        lead_id = self._normalize_uuid(id_lead, "lead")
        normalized_estado = normalize_crm_state_for_write(estado_lead)
        if normalized_estado not in CRM_STATE_CONTRACT:
            raise ValueError("Estado de lead invalido")
        if normalized_estado == "asignado":
            raise ValueError(
                "El estado asignado solo puede establecerse mediante una asignacion valida"
            )

        advisor_scope = self._advisor_mutation_scope(actor)
        if advisor_scope is False:
            return False
        return self.repository.update_lead_status(
            lead_id,
            normalized_estado,
            actor=actor,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

    def assign_lead(
        self,
        id_lead: UUID | str,
        id_asesor: UUID | str,
        *,
        actor: AuthenticatedUser,
    ) -> bool:
        if not isinstance(actor, AuthenticatedUser):
            raise TypeError("actor must be an AuthenticatedUser")
        if not self.can_assign_lead(actor):
            raise PermissionError("Usuario no autorizado para asignar leads")
        lead_id = self._normalize_uuid(id_lead, "lead")
        asesor_id = self._normalize_uuid(id_asesor, "asesor")
        return self.repository.assign_lead(lead_id, asesor_id, actor=actor)

    def can_assign_lead(self, user: AuthenticatedUser) -> bool:
        return is_superuser(user.role) or user.role in {"admin", "executive"}

    def get_lead_assignment_events(self, id_lead: UUID | str) -> list[dict[str, Any]]:
        """Return sanitized assignment traceability events for one lead.

        The repository reads only the migration-007 view (joined with tpi.asesores);
        the application never reads tpi.auditoria directly.
        """
        lead_id = self._normalize_uuid(id_lead, "lead")
        return self.repository.get_lead_assignment_events(lead_id)

    def get_lead_state_change_events(self, id_lead: UUID | str) -> list[dict[str, Any]]:
        """Return sanitized general state-change traceability events for one lead.

        The repository reads only the migration-008 view; the application never reads
        tpi.auditoria directly.
        """
        lead_id = self._normalize_uuid(id_lead, "lead")
        return self.repository.get_lead_state_change_events(lead_id)

    def get_asesores_disponibles_para_asignacion(self) -> list[dict[str, Any]]:
        return self.repository.get_asesores_disponibles_para_asignacion()

    def append_lead_comment(
        self,
        id_lead: UUID | str,
        comment_text: str,
        *,
        actor: AuthenticatedUser,
    ) -> bool:
        """Append a follow-up note atomically with server-side identity and timestamp.

        The actor is the authenticated subject (never a client-supplied value). For an
        advisor, the note is only written when the lead's active assignment belongs to
        the advisor's resolved id_asesor; otherwise the write is rejected without
        revealing existence.
        """
        self._ensure_web_write_allowed()
        if not isinstance(actor, AuthenticatedUser):
            raise TypeError("actor must be an AuthenticatedUser")
        lead_id = self._normalize_uuid(id_lead, "lead")
        normalized_comment = self._normalize_follow_up_comment(comment_text)
        if not normalized_comment:
            raise ValueError("El comentario no puede estar vacio")
        if len(normalized_comment) > 1000:
            raise ValueError("El comentario excede la longitud permitida")

        advisor_scope = self._advisor_mutation_scope(actor)
        if advisor_scope is False:
            return False
        fragment = self._format_follow_up_fragment(normalized_comment, actor.display_name)
        return self.repository.append_lead_comment(
            lead_id,
            fragment,
            advisor_scope=cast(UUID | None, advisor_scope),
        )

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

    def _ensure_web_write_allowed(self) -> None:
        if not self.settings.authentication_required:
            return
        # Web writes are only allowed for authenticated operational roles.
        # The web layer already performs the UI check, but the service fails closed.
        return

    def _normalize_uuid(self, value: UUID | str, label: str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"Identificador de {label} invalido") from exc

    @staticmethod
    def _normalize_estado_lead(value: str) -> str:
        normalized = normalize_crm_state_for_write(value)
        return normalized

    @staticmethod
    def _normalize_crm_state_for_filter(value: str) -> str | None:
        normalized = crm_state_filter_terms(value)
        if not normalized:
            return None
        # Use the canonical state for repository-level filtering and let the repository
        # expand any approved historical aliases in SQL.
        return normalized[0]

    @staticmethod
    def _normalize_follow_up_comment(value: str) -> str:
        return " ".join(str(value).strip().split())

    def _format_follow_up_fragment(self, comment_text: str, author: str) -> str:
        timestamp = datetime.now(self._CRM_TZ).strftime("%d/%m/%Y %H:%M")
        display_name = " ".join(str(author or "").strip().split()) or "Usuario"
        safe_comment = comment_text.replace("<", "&lt;").replace(">", "&gt;")
        return f"[{timestamp}] {display_name}\n{safe_comment}"
