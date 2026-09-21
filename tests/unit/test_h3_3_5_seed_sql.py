"""Static verification of the H3.3.5 DEV seed SQL (not executed).

The seed must remain a DEV-only artifact with a strict idempotence contract, and it
must never write tpi.asignaciones, change grants, or reference secrets/passwords.
These checks verify the artifact text, not the database.
"""

from __future__ import annotations

from pathlib import Path

SEED_PATH = Path(__file__).parents[2] / "scripts" / "sql" / "dev" / "seed_asesores_desarrollo.sql"


def _text() -> str:
    return SEED_PATH.read_text(encoding="utf-8")


def test_seed_sql_exists_under_dev_only_path() -> None:
    assert SEED_PATH.exists()
    assert "scripts/sql/dev" in SEED_PATH.as_posix()


def test_seed_targets_only_the_two_development_advisors() -> None:
    text = _text()
    assert "Asesor Desarrollo 1" in text
    assert "Asesor Desarrollo 2" in text
    # No production/other names are seeded.
    assert "Asesor Produccion" not in text
    assert "Asesor Desarrollo 3" not in text


def test_seed_never_writes_assignments_or_grants() -> None:
    text = _text()
    # The seed must never issue a write statement against assignments or change grants.
    assert "INSERT INTO tpi.asignaciones" not in text
    assert "UPDATE tpi.asignaciones" not in text
    assert "DELETE FROM tpi.asignaciones" not in text
    assert "GRANT " not in text
    assert "REVOKE " not in text


def test_seed_has_no_secrets_passwords_or_hashes() -> None:
    text = _text()
    assert "password_hash" not in text
    assert "argon2" not in text
    assert "AUTH_USERS_JSON" not in text
    assert "CREATE ROLE" not in text
    assert "CREATE USER" not in text
    assert "ALTER ROLE" not in text


def test_seed_is_transactional_and_aborts() -> None:
    text = _text()
    assert "BEGIN;" in text
    assert "COMMIT;" in text
    assert "RAISE EXCEPTION" in text


def test_seed_validates_database_schema_and_user() -> None:
    text = _text()
    assert "current_database()" in text
    assert "to_regclass('tpi.asesores')" in text
    assert "has_table_privilege" in text
    assert "tpi_app" in text  # rejects the SELECT-only application role


def test_seed_implements_create_adopt_or_abort_idempotence() -> None:
    text = _text()
    assert "lower(nombre)" in text
    # insert path
    assert "INSERT INTO tpi.asesores" in text
    # adopt path (no-op for exactly one compatible row)
    assert "adopt" in text.lower()
    # ambiguous/incompatible -> abort
    assert "ambiguous" in text.lower()
    assert "incompatible" in text.lower()
