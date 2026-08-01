"""
Servicio de negocio para Solicitudes de Simulación.

Responsabilidades:
- Orquestar validaciones complejas
- Coordinar operaciones en repositorio
- Aplicar reglas de negocio
- Retornar DTOs para UI
"""

from typing import Any
from uuid import UUID

from app.models.solicitud import (
    RegistrarSolicitudRequest,
    SolicitudResponse,
)
from app.repositories import SolicitudRepository
from app.security.masking import mask_row_for_display


class SolicitudService:
    """Servicio de negocio para solicitudes de simulación."""

    def __init__(self) -> None:
        """Inicializa el servicio con su repositorio."""
        self.repository = SolicitudRepository()

    def registrar_solicitud(self, request: RegistrarSolicitudRequest) -> SolicitudResponse:
        """
        Registra una nueva solicitud de simulación.

        Valida los datos, crea la persona (si no existe), inserta la solicitud
        y consentimientos en transacción.

        Args:
            request: Request validado con Pydantic

        Returns:
            SolicitudResponse con id_lead y datos de confirmación

        Raises:
            ValueError: Si hay validaciones de negocio que fallan
            Exception: Si falla la operación en BD
        """
        try:
            # PASO 1: Validaciones adicionales de negocio
            # (Las validaciones básicas ya pasaron en Pydantic)
            self._validate_catalogo_ids(
                genero_id=request.solicitud.genero_id,
                estado_civil_id=request.solicitud.estado_civil_id,
                afp_id=request.solicitud.afp_id,
            )

            # PASO 2: Crear solicitud en BD (transacción)
            response = self.repository.create_solicitud(
                persona_data=request.persona,
                solicitud_data=request.solicitud,
                consentimientos_data=request.consentimientos,
            )

            return response

        except ValueError as e:
            raise ValueError(f"Validación de negocio fallida: {str(e)}") from e
        except Exception as e:
            raise Exception(f"Error al registrar solicitud: {str(e)}") from e

    def get_solicitud_detalle(self, id_lead: UUID) -> dict[str, Any] | None:
        """
        Obtiene los detalles de una solicitud (sin enmascaramiento).

        Para uso administrativo/interno.

        Args:
            id_lead: UUID del lead a consultar

        Returns:
            Dict con datos completos o None si no existe
        """
        return self.repository.get_solicitud_by_id(id_lead)

    def get_solicitud_detalle_masked(self, id_lead: UUID) -> dict[str, Any] | None:
        """
        Obtiene los detalles de una solicitud (con enmascaramiento de datos sensibles).

        Para uso en UI/display.

        Args:
            id_lead: UUID del lead a consultar

        Returns:
            Dict con datos enmascarados o None si no existe
        """
        solicitud = self.repository.get_solicitud_by_id(id_lead)
        if not solicitud:
            return None

        # Aplicar enmascaramiento visual (no modifica datos originales)
        return mask_row_for_display(
            solicitud,
            sensitive_fields=["rut", "email", "telefono"],
        )

    def get_solicitudes_lista(
        self, page: int = 1, page_size: int = 10, masked: bool = True
    ) -> dict[str, Any]:
        """
        Obtiene lista paginada de solicitudes.

        Args:
            page: Número de página (1-based)
            page_size: Registros por página
            masked: Si aplicar enmascaramiento (para UI)

        Returns:
            Dict con keys:
                - solicitudes: lista de solicitudes
                - total: total de registros
                - page: página actual
                - page_size: registros por página
                - total_pages: total de páginas
        """
        offset = (page - 1) * page_size

        solicitudes, total = self.repository.get_all_solicitudes(limit=page_size, offset=offset)

        # Aplicar enmascaramiento si se solicita
        if masked:
            solicitudes = [
                mask_row_for_display(
                    s,
                    sensitive_fields=["rut", "email", "telefono"],
                )
                for s in solicitudes
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
        """
        Obtiene todas las solicitudes de una persona por RUT.

        Args:
            rut: RUT normalizado
            masked: Si aplicar enmascaramiento

        Returns:
            Lista de solicitudes
        """
        solicitudes = self.repository.get_solicitudes_by_rut(rut)

        if masked:
            solicitudes = [
                mask_row_for_display(
                    s,
                    sensitive_fields=["rut", "email", "telefono"],
                )
                for s in solicitudes
            ]

        return solicitudes

    def get_catalogo_afp(self) -> list[dict[str, Any]]:
        """Obtiene listado de AFP activos para dropdown."""
        return self.repository.get_active_afp()

    def get_catalogo_genero(self) -> list[dict[str, Any]]:
        """Obtiene listado de géneros activos para dropdown."""
        return self.repository.get_active_genero()

    def get_catalogo_estado_civil(self) -> list[dict[str, Any]]:
        """Obtiene listado de estados civiles activos para dropdown."""
        return self.repository.get_active_estado_civil()

    # ========== Métodos privados de validación ==========

    def _validate_catalogo_ids(self, genero_id: UUID, estado_civil_id: UUID, afp_id: UUID) -> None:
        """
        Valida que los IDs de catálogos existan y sean válidos.

        Args:
            genero_id: UUID del género
            estado_civil_id: UUID del estado civil
            afp_id: UUID del AFP

        Raises:
            ValueError: Si algún ID no existe en catálogos
        """
        # Obtener catálogos
        generos = self.repository.get_active_genero()
        estados_civiles = self.repository.get_active_estado_civil()
        afps = self.repository.get_active_afp()

        # Validar géneros
        genero_ids = {UUID(str(g["id"])) for g in generos}
        if genero_id not in genero_ids:
            raise ValueError(f"ID de género inválido: {genero_id}")

        # Validar estado civil
        estado_civil_ids = {UUID(str(ec["id"])) for ec in estados_civiles}
        if estado_civil_id not in estado_civil_ids:
            raise ValueError(f"ID de estado civil inválido: {estado_civil_id}")

        # Validar AFP
        afp_ids = {UUID(str(a["id"])) for a in afps}
        if afp_id not in afp_ids:
            raise ValueError(f"ID de AFP inválido: {afp_id}")
