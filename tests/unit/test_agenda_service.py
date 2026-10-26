"""Pruebas unitarias del servicio de agenda (permisos, responsable, alcance y recorte).

Usa repositorios falsos para ejercitar la logica de negocio sin base de datos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

import pytest

from app.auth.models import AuthenticatedUser, UserRole
from app.models.agenda import (
    AGENDA_TZ,
    AgendaNotFoundError,
    AgendaPermissionError,
    AgendaValidationError,
)
from app.services.agenda_service import AgendaService
from app.services.solicitud_service import SolicitudService

SOCIO_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIO_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
COORD = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
RUNNER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
LEAD = UUID("11111111-1111-1111-1111-111111111111")
FOREIGN_LEAD = UUID("99999999-9999-9999-9999-999999999999")
CITA = UUID("22222222-2222-2222-2222-222222222222")


def _user(role: str, advisor_id: UUID | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject=f"subject-{role}",
        username=f"{role}@example.com",
        display_name=f"User {role}",
        role=cast(UserRole, role),
        advisor_id=advisor_id,
    )


class FakeSolicitudRepo:
    def __init__(self, active: set[UUID] | None = None, ownership: dict[UUID, UUID] | None = None):
        self.active = active if active is not None else {SOCIO_A, SOCIO_B, COORD, RUNNER}
        self.ownership = ownership if ownership is not None else {LEAD: RUNNER}

    def get_active_advisor_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        if id_asesor in self.active:
            return {"id_asesor": str(id_asesor), "rol": "asesor", "estado_disponibilidad": "activo"}
        return None

    def lead_active_assignment_belongs_to(self, id_lead: UUID, id_asesor: UUID) -> bool:
        return self.ownership.get(id_lead) == id_asesor


class FakeAgendaRepo:
    def __init__(
        self,
        responsables: list[dict[str, Any]] | None = None,
        citas: dict[UUID, dict[str, Any]] | None = None,
        ownership: dict[UUID, UUID] | None = None,
    ) -> None:
        self.responsables = (
            responsables
            if responsables is not None
            else [
                {"id_asesor": str(SOCIO_A), "nombre": "Socio A", "rol": "socio"},
                {"id_asesor": str(SOCIO_B), "nombre": "Socio B", "rol": "socio"},
                {"id_asesor": str(COORD), "nombre": "Coordinador", "rol": "asesor"},
            ]
        )
        self.citas = citas if citas is not None else {}
        self.ownership = ownership if ownership is not None else {LEAD: RUNNER}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_responsables(self) -> list[dict[str, Any]]:
        return list(self.responsables)

    def get_responsable_by_id(self, id_asesor: UUID) -> dict[str, Any] | None:
        return next((r for r in self.responsables if UUID(r["id_asesor"]) == id_asesor), None)

    def get_cita_by_id(self, id_cita: UUID) -> dict[str, Any] | None:
        return self.citas.get(id_cita)

    def get_cita_for_lead(self, id_lead: UUID) -> dict[str, Any] | None:
        for cita in self.citas.values():
            if UUID(str(cita["id_lead"])) == id_lead:
                return cita
        return None

    def list_citas(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def lead_active_assignment_owner(self, id_lead: UUID) -> UUID | None:
        return self.ownership.get(id_lead)

    def create_cita(self, **kwargs: Any) -> None:
        self.calls.append(("create_cita", kwargs))

    def update_cita(self, **kwargs: Any) -> None:
        self.calls.append(("update_cita", kwargs))

    def cancel_cita(self, **kwargs: Any) -> None:
        self.calls.append(("cancel_cita", kwargs))

    def complete_cita(self, **kwargs: Any) -> None:
        self.calls.append(("complete_cita", kwargs))

    def no_show_cita(self, **kwargs: Any) -> None:
        self.calls.append(("no_show_cita", kwargs))


def _service(
    repo: FakeAgendaRepo | None = None,
    solicitud_repo: FakeSolicitudRepo | None = None,
) -> tuple[AgendaService, FakeAgendaRepo]:
    agenda_repo = repo or FakeAgendaRepo()
    solicitudes = SolicitudService(repository=cast(Any, solicitud_repo or FakeSolicitudRepo()))
    return AgendaService(repository=cast(Any, agenda_repo), solicitudes=solicitudes), agenda_repo


# ------------------------------------------------------------------ permisos


def test_permisos_matriz():
    service, _ = _service()
    for role in ("tester", "advisor", "coordinator", "operations", "admin", "ceo", "cto"):
        assert service.can_agendar(_user(role)) is True, role
    for role in ("executive", "readonly"):
        assert service.can_agendar(_user(role)) is False, role

    for role in ("coordinator", "ceo", "cto"):
        assert service.can_mark_attendance(_user(role)) is True, role
    for role in ("tester", "advisor", "operations", "admin", "executive", "readonly"):
        assert service.can_mark_attendance(_user(role)) is False, role


# ------------------------------------------------------------------ responsables


def test_runner_solo_elige_socio():
    service, _ = _service()
    runner = _user("advisor", advisor_id=RUNNER)
    assert service.can_agendar(runner)
    # Runner elige Socio: ok
    responsable = service._resolve_responsable(SOCIO_A, runner, LEAD)
    assert responsable["rol"] == "socio"
    # Runner elige Coordinador: rechazo
    with pytest.raises(AgendaPermissionError):
        service._resolve_responsable(COORD, runner, LEAD)


def test_coordinador_elige_self_o_socio():
    service, repo = _service()
    repo.ownership = {LEAD: COORD}
    coordinador = _user("coordinator", advisor_id=COORD)
    # self (coordinador dueño del lead): ok
    assert service._resolve_responsable(COORD, coordinador, LEAD)["rol"] == "asesor"
    # socio: ok
    assert service._resolve_responsable(SOCIO_A, coordinador, LEAD)["rol"] == "socio"


def test_coordinador_responsable_solo_de_su_cartera():
    service, repo = _service()
    repo.ownership = {LEAD: RUNNER}  # el lead es de otro runner
    socio = _user("ceo")
    with pytest.raises(AgendaValidationError):
        service._resolve_responsable(COORD, socio, LEAD)


def test_socio_elige_socio_o_coordinador_dueno():
    service, repo = _service()
    repo.ownership = {LEAD: COORD}
    socio = _user("cto")
    assert service._resolve_responsable(SOCIO_A, socio, LEAD)["rol"] == "socio"
    assert service._resolve_responsable(COORD, socio, LEAD)["rol"] == "asesor"


def test_responsable_inexistente_rechazado():
    service, _ = _service()
    socio = _user("ceo")
    with pytest.raises(AgendaValidationError):
        service._resolve_responsable(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"), socio, LEAD)


def test_responsables_para_agendar_filtrados_por_actor():
    service, repo = _service()
    repo.ownership = {LEAD: RUNNER}
    runner_opts = service.get_responsables_para_agendar(LEAD, _user("advisor", advisor_id=RUNNER))
    assert {r["rol"] for r in runner_opts} == {"socio"}

    repo.ownership = {LEAD: COORD}
    coord_opts = service.get_responsables_para_agendar(LEAD, _user("coordinator", advisor_id=COORD))
    assert {UUID(r["id_asesor"]) for r in coord_opts} == {SOCIO_A, SOCIO_B, COORD}

    socio_opts = service.get_responsables_para_agendar(LEAD, _user("cto"))
    assert {UUID(r["id_asesor"]) for r in socio_opts} == {SOCIO_A, SOCIO_B, COORD}


# ------------------------------------------------------------------ alcance y recorte


def _cita_row(lead_id: UUID, owner: UUID, cita_id: UUID = CITA) -> dict[str, Any]:
    return {
        "id_cita": str(cita_id),
        "id_lead": str(lead_id),
        "id_asesor": str(SOCIO_A),
        "fecha_hora": datetime(2026, 1, 15, 10, 0, tzinfo=AGENDA_TZ),
        "fecha_hora_fin": datetime(2026, 1, 15, 10, 30, tzinfo=AGENDA_TZ),
        "agendada_por_nombre": "Quien agendo",
        "canal": "Google Meet",
        "estado_cita": "agendada",
        "nota": None,
        "motivo_cancelacion": None,
        "asesor_nombre": "Socio A",
        "link_reunion": "https://meet.example/abc",
        "lead_nombre": "Juan Perez",
        "lead_asesor_id": str(owner),
    }


def test_socio_ve_todos_los_leads():
    service, repo = _service()
    repo.citas_rows = [
        _cita_row(LEAD, RUNNER),
        _cita_row(FOREIGN_LEAD, COORD),
    ]
    repo.list_citas = lambda *a, **k: list(repo.citas_rows)  # type: ignore[method-assign]
    views = service.get_agenda(
        desde=datetime(2026, 1, 1, tzinfo=AGENDA_TZ),
        hasta=datetime(2026, 2, 1, tzinfo=AGENDA_TZ),
        user=_user("ceo"),
    )
    assert all(v["lead_fuera_de_alcance"] is False for v in views)
    assert {v["lead_nombre"] for v in views} == {"Juan Perez"}


def test_runner_solo_ve_su_cartera():
    service, repo = _service()
    repo.citas_rows = [
        _cita_row(LEAD, RUNNER, cita_id=UUID("22222222-2222-2222-2222-222222222222")),
        _cita_row(FOREIGN_LEAD, COORD, cita_id=UUID("33333333-3333-3333-3333-333333333333")),
    ]
    repo.list_citas = lambda *a, **k: list(repo.citas_rows)  # type: ignore[method-assign]
    views = service.get_agenda(
        desde=datetime(2026, 1, 1, tzinfo=AGENDA_TZ),
        hasta=datetime(2026, 2, 1, tzinfo=AGENDA_TZ),
        user=_user("advisor", advisor_id=RUNNER),
    )
    propia = next(v for v in views if v["lead_fuera_de_alcance"] is False)
    ajena = next(v for v in views if v["lead_fuera_de_alcance"] is True)
    assert propia["lead_nombre"] == "Juan Perez"
    assert propia["id_lead"] == str(LEAD)
    assert ajena["lead_nombre"] is None
    assert ajena["id_lead"] is None
    assert ajena["link_reunion"] is None


def test_cita_ajena_recorta_nota_y_motivo():
    service, repo = _service()
    ajena = _cita_row(FOREIGN_LEAD, COORD, cita_id=UUID("33333333-3333-3333-3333-333333333333"))
    ajena["nota"] = "Nota con el nombre del lead ajeno"
    ajena["motivo_cancelacion"] = "Lead no pudo asistir"
    repo.citas_rows = [ajena]
    repo.list_citas = lambda *a, **k: list(repo.citas_rows)  # type: ignore[method-assign]
    views = service.get_agenda(
        desde=datetime(2026, 1, 1, tzinfo=AGENDA_TZ),
        hasta=datetime(2026, 2, 1, tzinfo=AGENDA_TZ),
        user=_user("advisor", advisor_id=RUNNER),
    )
    vista = views[0]
    assert vista["lead_fuera_de_alcance"] is True
    assert vista["nota"] is None
    assert vista["motivo_cancelacion"] is None


def test_rol_sin_cartera_ve_todos():
    service, repo = _service()
    repo.citas_rows = [_cita_row(LEAD, RUNNER), _cita_row(FOREIGN_LEAD, COORD)]
    repo.list_citas = lambda *a, **k: list(repo.citas_rows)  # type: ignore[method-assign]
    views = service.get_agenda(
        desde=datetime(2026, 1, 1, tzinfo=AGENDA_TZ),
        hasta=datetime(2026, 2, 1, tzinfo=AGENDA_TZ),
        user=_user("tester"),
    )
    assert all(v["lead_fuera_de_alcance"] is False for v in views)


def test_get_proximas_citas_y_list_responsables():
    service, repo = _service()
    repo.citas_rows = [_cita_row(LEAD, RUNNER)]
    repo.list_citas = lambda *a, **k: list(repo.citas_rows)  # type: ignore[method-assign]
    proximas = service.get_proximas_citas(
        desde=datetime(2026, 1, 1, tzinfo=AGENDA_TZ), user=_user("ceo")
    )
    assert len(proximas) == 1
    assert proximas[0]["lead_nombre"] == "Juan Perez"
    assert len(service.list_responsables()) == 3


# ------------------------------------------------------------------ escritura


def test_agendar_valida_y_delega():
    service, repo = _service()
    service.agendar(
        lead_id=LEAD,
        responsable_id=SOCIO_A,
        fecha="2099-01-15",
        hora="10:00",
        duracion=30,
        modalidad="Google Meet",
        link=None,
        nota=None,
        actor=_user("advisor", advisor_id=RUNNER),
    )
    assert repo.calls[0][0] == "create_cita"
    kwargs = repo.calls[0][1]
    assert kwargs["responsable_id"] == SOCIO_A
    assert kwargs["modalidad"] == "Google Meet"


def test_agendar_rechaza_pasado():
    service, _ = _service()
    with pytest.raises(AgendaValidationError):
        service.agendar(
            lead_id=LEAD,
            responsable_id=SOCIO_A,
            fecha="2000-01-15",
            hora="10:00",
            duracion=30,
            modalidad="Google Meet",
            link=None,
            nota=None,
            actor=_user("advisor", advisor_id=RUNNER),
        )


def test_cancelar_exige_motivo():
    service, _ = _service()
    with pytest.raises(AgendaValidationError):
        service.cancelar(cita_id=CITA, motivo="   ", actor=_user("ceo"))


def test_runner_no_puede_marcar_asistencia():
    service, _ = _service()
    with pytest.raises(AgendaPermissionError):
        service.marcar_realizada(cita_id=CITA, actor=_user("advisor", advisor_id=RUNNER))
    with pytest.raises(AgendaPermissionError):
        service.marcar_no_asistio(cita_id=CITA, actor=_user("advisor", advisor_id=RUNNER))


def test_reagendar_cita_ajena_es_404():
    service, repo = _service()
    repo.citas = {
        CITA: {
            "id_cita": str(CITA),
            "id_lead": str(FOREIGN_LEAD),
            "id_asesor": str(SOCIO_A),
            "estado_cita": "agendada",
            "fecha_hora": datetime(2099, 1, 15, 10, 0, tzinfo=AGENDA_TZ),
        }
    }
    runner = _user("advisor", advisor_id=RUNNER)
    with pytest.raises(AgendaNotFoundError):
        service.reagendar(
            cita_id=CITA,
            responsable_id=SOCIO_A,
            fecha="2099-02-16",
            hora="10:00",
            duracion=30,
            modalidad="Google Meet",
            link=None,
            nota=None,
            actor=runner,
        )


def test_identity_sin_asesor_activo_falla_cerrado():
    service, _ = _service(solicitud_repo=FakeSolicitudRepo(active=set(), ownership={LEAD: RUNNER}))
    runner = _user("advisor", advisor_id=RUNNER)
    with pytest.raises(AgendaNotFoundError):
        service.agendar(
            lead_id=LEAD,
            responsable_id=SOCIO_A,
            fecha="2099-01-15",
            hora="10:00",
            duracion=30,
            modalidad="Google Meet",
            link=None,
            nota=None,
            actor=runner,
        )
