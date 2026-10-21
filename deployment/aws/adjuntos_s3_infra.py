"""Infraestructura S3 de los adjuntos de las notas del lead (CRM-ADJUNTOS-1-INFRA-S3).

Crea, comprueba y revierte el bucket privado de adjuntos, el permiso minimo del rol de la
instancia de Elastic Beanstalk y GuardDuty Malware Protection for S3. Los documentos de politica
estan en ``deployment/iam/`` y este script es la unica forma prevista de aplicarlos.

Subcomandos:

* ``plan``     solo lectura: compara el estado real con el esperado (no cambia nada).
* ``apply``    crea o corrige lo que falte; exige ``--confirmar "CREAR INFRA ADJUNTOS DEV"``.
* ``verify``   prueba de extremo a extremo con un archivo de prueba de antivirus (EICAR).
* ``rollback`` elimina todo; exige ``--confirmar "ELIMINAR INFRA ADJUNTOS DEV"``.

Uso: ``python deployment/aws/adjuntos_s3_infra.py plan --profile tpi-dev``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

ACCOUNT_ID = "821656895812"
REGION = "us-east-2"
BUCKET = f"tpi-dev-adjuntos-{ACCOUNT_ID}-{REGION}"
OBJECT_PREFIX = "leads/"
VERIFY_PREFIX = f"{OBJECT_PREFIX}_verificacion/"
GUARDDUTY_ROLE = "tpi-dev-guardduty-malware-s3-role"
GUARDDUTY_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/{GUARDDUTY_ROLE}"
APP_ROLE = "tpi-backoffice-dev-ec2-role"
APP_POLICY = "tpi-backoffice-dev-adjuntos-s3"
SCAN_TAG = "GuardDutyMalwareScanStatus"
LIFECYCLE_RULE_ID = "abort-incomplete-multipart"
TAGS = {
    "Project": "TPI",
    "Environment": "dev",
    "Application": "tpi-backoffice",
    "Purpose": "lead-attachments",
}
APPLY_PHRASE = "CREAR INFRA ADJUNTOS DEV"
ROLLBACK_PHRASE = "ELIMINAR INFRA ADJUNTOS DEV"
IAM_DIR = Path(__file__).resolve().parents[1] / "iam"
POLICY_FILES = {
    "bucket": "tpi-dev-adjuntos-bucket-policy.json",
    "guardduty_trust": "tpi-dev-guardduty-malware-s3-role-trust.json",
    "guardduty_role": "tpi-dev-guardduty-malware-s3-role.json",
    "app_role": "tpi-backoffice-dev-adjuntos-s3.json",
}
NOT_FOUND_CODES = {"404", "NoSuchBucket", "NotFound", "NoSuchEntity"}
PLAN_RETRIES = 6
PLAN_RETRY_SECONDS = 15
SCAN_WAIT_SECONDS = 300
SCAN_POLL_SECONDS = 10

Sleeper = Callable[[float], None]


class InfraError(RuntimeError):
    """Error de la herramienta (cuenta equivocada, estado inesperado, verificacion fallida)."""


@dataclass(frozen=True)
class Aws:
    """Clientes de AWS que usa la herramienta; las pruebas inyectan dobles."""

    sts: Any
    s3: Any
    iam: Any
    guardduty: Any


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # OK | FALTA | DIFIERE
    detail: str = ""


def build_aws(profile: str | None) -> Aws:
    session = boto3.Session(profile_name=profile, region_name=REGION)
    return Aws(
        sts=session.client("sts"),
        s3=session.client("s3"),
        iam=session.client("iam"),
        guardduty=session.client("guardduty"),
    )


def load_policy(key: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((IAM_DIR / POLICY_FILES[key]).read_text(encoding="utf-8"))
    return document


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def _is_missing(error: ClientError) -> bool:
    return _code(error) in NOT_FOUND_CODES


def require_account(aws: Aws) -> str:
    identity = aws.sts.get_caller_identity()
    if identity["Account"] != ACCOUNT_ID:
        raise InfraError(f"cuenta inesperada {identity['Account']}: se esperaba {ACCOUNT_ID}")
    return str(identity["Arn"])


# --------------------------------------------------------------------------------------------
# Lectura del estado
# --------------------------------------------------------------------------------------------


def _bucket_exists(aws: Aws) -> bool:
    try:
        aws.s3.head_bucket(Bucket=BUCKET)
    except ClientError as error:
        if _is_missing(error):
            return False
        raise InfraError(
            f"no se puede leer el bucket {BUCKET} ({_code(error)}): ¿existe en otra cuenta?"
        ) from error
    return True


def _read(call: Callable[[], Any], *missing_codes: str) -> Any | None:
    """Ejecuta una lectura y devuelve None si el recurso o su configuracion no existe."""
    try:
        return call()
    except ClientError as error:
        if _is_missing(error) or _code(error) in missing_codes:
            return None
        raise


def _check_bucket_settings(aws: Aws) -> list[Check]:
    s3 = aws.s3
    checks: list[Check] = []

    block = _read(
        lambda: s3.get_public_access_block(Bucket=BUCKET),
        "NoSuchPublicAccessBlockConfiguration",
    )
    config = (block or {}).get("PublicAccessBlockConfiguration", {})
    keys = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
    if not block:
        checks.append(Check("acceso publico bloqueado", "FALTA"))
    elif all(config.get(key) is True for key in keys):
        checks.append(Check("acceso publico bloqueado", "OK"))
    else:
        checks.append(Check("acceso publico bloqueado", "DIFIERE", json.dumps(config)))

    ownership = _read(
        lambda: s3.get_bucket_ownership_controls(Bucket=BUCKET),
        "OwnershipControlsNotFoundError",
    )
    rules = ((ownership or {}).get("OwnershipControls") or {}).get("Rules") or [{}]
    if not ownership:
        checks.append(Check("ACL deshabilitadas (BucketOwnerEnforced)", "FALTA"))
    elif rules[0].get("ObjectOwnership") == "BucketOwnerEnforced":
        checks.append(Check("ACL deshabilitadas (BucketOwnerEnforced)", "OK"))
    else:
        checks.append(Check("ACL deshabilitadas (BucketOwnerEnforced)", "DIFIERE"))

    encryption = _read(
        lambda: s3.get_bucket_encryption(Bucket=BUCKET),
        "ServerSideEncryptionConfigurationNotFoundError",
    )
    enc_rules = ((encryption or {}).get("ServerSideEncryptionConfiguration") or {}).get(
        "Rules"
    ) or [{}]
    algorithm = (enc_rules[0].get("ApplyServerSideEncryptionByDefault") or {}).get("SSEAlgorithm")
    if not encryption:
        checks.append(Check("cifrado en reposo SSE-S3", "FALTA"))
    elif algorithm == "AES256":
        checks.append(Check("cifrado en reposo SSE-S3", "OK"))
    else:
        checks.append(Check("cifrado en reposo SSE-S3", "DIFIERE", str(algorithm)))

    versioning = s3.get_bucket_versioning(Bucket=BUCKET).get("Status")
    if versioning is None:
        checks.append(Check("sin versionado", "OK"))
    else:
        checks.append(Check("sin versionado", "DIFIERE", f"versionado {versioning}"))

    lifecycle = _read(
        lambda: s3.get_bucket_lifecycle_configuration(Bucket=BUCKET),
        "NoSuchLifecycleConfiguration",
    )
    lifecycle_ok = any(
        rule.get("ID") == LIFECYCLE_RULE_ID
        and rule.get("Status") == "Enabled"
        and (rule.get("AbortIncompleteMultipartUpload") or {}).get("DaysAfterInitiation") == 1
        for rule in (lifecycle or {}).get("Rules", [])
    )
    checks.append(Check("aborta subidas multiparte incompletas", "OK" if lifecycle_ok else "FALTA"))

    policy = _read(lambda: s3.get_bucket_policy(Bucket=BUCKET), "NoSuchBucketPolicy")
    if not policy:
        checks.append(Check("politica del bucket", "FALTA"))
    elif json.loads(policy["Policy"]) == load_policy("bucket"):
        checks.append(Check("politica del bucket", "OK"))
    else:
        checks.append(Check("politica del bucket", "DIFIERE"))

    tagging = _read(lambda: s3.get_bucket_tagging(Bucket=BUCKET), "NoSuchTagSet")
    current = {tag["Key"]: tag["Value"] for tag in (tagging or {}).get("TagSet", [])}
    checks.append(
        Check(
            "etiquetas del bucket",
            "OK" if all(current.get(key) == value for key, value in TAGS.items()) else "FALTA",
        )
    )
    return checks


def _check_roles(aws: Aws) -> list[Check]:
    iam = aws.iam
    checks: list[Check] = []

    role = _read(lambda: iam.get_role(RoleName=GUARDDUTY_ROLE))
    if not role:
        checks.append(Check("rol de GuardDuty", "FALTA"))
    elif role["Role"]["AssumeRolePolicyDocument"] == load_policy("guardduty_trust"):
        checks.append(Check("rol de GuardDuty (confianza)", "OK"))
    else:
        checks.append(Check("rol de GuardDuty (confianza)", "DIFIERE"))

    inline = _read(lambda: iam.get_role_policy(RoleName=GUARDDUTY_ROLE, PolicyName=GUARDDUTY_ROLE))
    if not inline:
        checks.append(Check("permisos del rol de GuardDuty", "FALTA"))
    elif inline["PolicyDocument"] == load_policy("guardduty_role"):
        checks.append(Check("permisos del rol de GuardDuty", "OK"))
    else:
        checks.append(Check("permisos del rol de GuardDuty", "DIFIERE"))

    if not _read(lambda: iam.get_role(RoleName=APP_ROLE)):
        checks.append(Check("rol de la instancia de la app", "FALTA", f"no existe {APP_ROLE}"))
        return checks
    app = _read(lambda: iam.get_role_policy(RoleName=APP_ROLE, PolicyName=APP_POLICY))
    if not app:
        checks.append(Check("permiso de la app sobre el bucket", "FALTA"))
    elif app["PolicyDocument"] == load_policy("app_role"):
        checks.append(Check("permiso de la app sobre el bucket", "OK"))
    else:
        checks.append(Check("permiso de la app sobre el bucket", "DIFIERE"))
    return checks


def find_plan(aws: Aws) -> dict[str, Any] | None:
    """Devuelve el plan de GuardDuty que protege el bucket, si existe."""
    token: str | None = None
    while True:
        kwargs = {"NextToken": token} if token else {}
        page = aws.guardduty.list_malware_protection_plans(**kwargs)
        for item in page.get("MalwareProtectionPlans", []):
            plan_id = item["MalwareProtectionPlanId"]
            plan: dict[str, Any] = aws.guardduty.get_malware_protection_plan(
                MalwareProtectionPlanId=plan_id
            )
            bucket = (plan.get("ProtectedResource") or {}).get("S3Bucket") or {}
            if bucket.get("BucketName") == BUCKET:
                plan["MalwareProtectionPlanId"] = plan_id
                return plan
        token = page.get("NextToken")
        if not token:
            return None


def _check_plan(aws: Aws) -> list[Check]:
    plan = find_plan(aws)
    if plan is None:
        return [Check("plan de GuardDuty Malware Protection", "FALTA")]
    bucket = plan["ProtectedResource"]["S3Bucket"]
    problems = []
    if plan.get("Status") != "ACTIVE":
        problems.append(f"estado {plan.get('Status')}")
    if (plan.get("Actions") or {}).get("Tagging", {}).get("Status") != "ENABLED":
        problems.append("etiquetado desactivado")
    if bucket.get("ObjectPrefixes") != [OBJECT_PREFIX]:
        problems.append(f"prefijos {bucket.get('ObjectPrefixes')}")
    if plan.get("Role") != GUARDDUTY_ROLE_ARN:
        problems.append("rol distinto")
    if problems:
        return [Check("plan de GuardDuty Malware Protection", "DIFIERE", ", ".join(problems))]
    return [Check("plan de GuardDuty Malware Protection", "OK", plan["MalwareProtectionPlanId"])]


def inspect(aws: Aws) -> list[Check]:
    """Compara el estado real con el esperado. Solo lecturas."""
    checks: list[Check] = []
    if _bucket_exists(aws):
        checks.append(Check(f"bucket {BUCKET}", "OK"))
        checks.extend(_check_bucket_settings(aws))
    else:
        checks.append(Check(f"bucket {BUCKET}", "FALTA"))
    checks.extend(_check_roles(aws))
    checks.extend(_check_plan(aws))
    return checks


def print_checks(checks: Sequence[Check]) -> None:
    for check in checks:
        detail = f" ({check.detail})" if check.detail else ""
        print(f"  [{check.status:<7}] {check.name}{detail}")


# --------------------------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------------------------


def _step(number: int, total: int, text: str) -> None:
    print(f"[{number}/{total}] {text}")


def _put_role_policy(aws: Aws, role: str, name: str, document: dict[str, Any]) -> None:
    aws.iam.put_role_policy(RoleName=role, PolicyName=name, PolicyDocument=json.dumps(document))


def apply(aws: Aws, *, sleep: Sleeper = time.sleep) -> None:
    """Crea o corrige lo que falte. Idempotente: se puede repetir tras un fallo."""
    total = 10
    s3, iam = aws.s3, aws.iam
    if not _read(lambda: iam.get_role(RoleName=APP_ROLE)):
        raise InfraError(f"no existe el rol de la instancia {APP_ROLE}: no se cambia nada")

    _step(1, total, f"bucket {BUCKET}")
    if not _bucket_exists(aws):
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
            ObjectOwnership="BucketOwnerEnforced",
        )
    s3.put_bucket_tagging(
        Bucket=BUCKET, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]}
    )

    _step(2, total, "acceso publico bloqueado y ACL deshabilitadas")
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_ownership_controls(
        Bucket=BUCKET, OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}
    )

    _step(3, total, "cifrado SSE-S3 y regla de subidas multiparte incompletas")
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    s3.put_bucket_lifecycle_configuration(
        Bucket=BUCKET,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": LIFECYCLE_RULE_ID,
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                }
            ]
        },
    )
    if s3.get_bucket_versioning(Bucket=BUCKET).get("Status") is not None:
        raise InfraError("el bucket tiene versionado: no se cambia (el diseno exige borrado real)")

    _step(4, total, f"rol de GuardDuty {GUARDDUTY_ROLE}")
    created_role = False
    trust = json.dumps(load_policy("guardduty_trust"))
    if _read(lambda: iam.get_role(RoleName=GUARDDUTY_ROLE)):
        iam.update_assume_role_policy(RoleName=GUARDDUTY_ROLE, PolicyDocument=trust)
    else:
        iam.create_role(
            RoleName=GUARDDUTY_ROLE,
            AssumeRolePolicyDocument=trust,
            Description="GuardDuty Malware Protection for S3: escaneo de los adjuntos de leads",
            Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
        )
        created_role = True

    _step(5, total, "permisos del rol de GuardDuty")
    _put_role_policy(aws, GUARDDUTY_ROLE, GUARDDUTY_ROLE, load_policy("guardduty_role"))

    _step(6, total, f"permiso minimo de {APP_ROLE} sobre {OBJECT_PREFIX}*")
    _put_role_policy(aws, APP_ROLE, APP_POLICY, load_policy("app_role"))

    _step(7, total, "politica del bucket")
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps(load_policy("bucket")))

    _step(8, total, "plan de GuardDuty Malware Protection for S3")
    if created_role:
        sleep(PLAN_RETRY_SECONDS)  # propagacion del rol nuevo
    if find_plan(aws) is None:
        _create_plan(aws, sleep=sleep)

    _step(9, total, "espera a que el plan quede ACTIVE")
    _wait_plan_active(aws, sleep=sleep)

    _step(10, total, "estado final")
    print_checks(inspect(aws))


def _create_plan(aws: Aws, *, sleep: Sleeper) -> None:
    last: ClientError | None = None
    for attempt in range(1, PLAN_RETRIES + 1):
        try:
            aws.guardduty.create_malware_protection_plan(
                ClientToken=str(uuid.uuid4()),
                Role=GUARDDUTY_ROLE_ARN,
                ProtectedResource={
                    "S3Bucket": {"BucketName": BUCKET, "ObjectPrefixes": [OBJECT_PREFIX]}
                },
                Actions={"Tagging": {"Status": "ENABLED"}},
                Tags=dict(TAGS),
            )
            return
        except ClientError as error:
            last = error
            message = str(error.response.get("Error", {}).get("Message", ""))
            print(f"  intento {attempt}/{PLAN_RETRIES}: {_code(error)}: {message}")
            if "detector" in message.lower():
                raise InfraError(
                    "GuardDuty exige un detector activo en esta region: decision del humano "
                    "(activarlo tiene costo); no se activa solo"
                ) from error
            if attempt < PLAN_RETRIES:
                sleep(PLAN_RETRY_SECONDS)
    raise InfraError(f"no se pudo crear el plan de GuardDuty: {last}") from last


def _wait_plan_active(aws: Aws, *, sleep: Sleeper) -> None:
    for _ in range(18):
        plan = find_plan(aws)
        status = (plan or {}).get("Status")
        if status == "ACTIVE":
            print("  plan ACTIVE")
            return
        if status in {"ERROR", "WARNING"}:
            reasons = (plan or {}).get("StatusReasons")
            raise InfraError(f"el plan quedo en {status}: {reasons}")
        sleep(10)
    raise InfraError("el plan no quedo ACTIVE en 3 minutos")


# --------------------------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------------------------


def _eicar() -> bytes:
    """Cadena estandar de prueba de antivirus, armada en partes para no marcar este archivo."""
    parts = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*")
    return "".join(parts).encode("ascii")


def _scan_status(aws: Aws, key: str) -> str | None:
    tags = aws.s3.get_object_tagging(Bucket=BUCKET, Key=key).get("TagSet", [])
    for tag in tags:
        if tag["Key"] == SCAN_TAG:
            return str(tag["Value"])
    return None


def _wait_scan_tag(aws: Aws, key: str, *, sleep: Sleeper) -> str | None:
    waited = 0
    while waited <= SCAN_WAIT_SECONDS:
        status = _scan_status(aws, key)
        if status is not None:
            return status
        sleep(SCAN_POLL_SECONDS)
        waited += SCAN_POLL_SECONDS
    return None


def _denied(call: Callable[[], Any]) -> bool:
    try:
        call()
    except ClientError as error:
        return _code(error) in {"AccessDenied", "403"}
    return False


def verify(aws: Aws, *, sleep: Sleeper = time.sleep) -> bool:
    """Prueba de extremo a extremo. Devuelve True si todas las comprobaciones pasan."""
    s3 = aws.s3
    run_id = uuid.uuid4().hex[:12]
    clean_key = f"{VERIFY_PREFIX}{run_id}-limpio.txt"
    virus_key = f"{VERIFY_PREFIX}{run_id}-eicar.txt"
    results: list[tuple[str, bool]] = []

    def record(name: str, passed: bool) -> None:
        results.append((name, passed))
        print(f"  [{'PASA' if passed else 'FALLA'}] {name}")

    try:
        s3.put_object(Bucket=BUCKET, Key=clean_key, Body=b"adjunto de prueba sin amenazas")
        if _denied(lambda: s3.get_object(Bucket=BUCKET, Key=clean_key)):
            record("un objeto recien subido y sin escanear no se puede leer", True)
        elif _scan_status(aws, clean_key) is not None:
            print("  [INCONCLUSO] el escaneo termino antes de la lectura; no prueba nada")
        else:
            record("un objeto recien subido y sin escanear no se puede leer", False)
        s3.put_object(Bucket=BUCKET, Key=virus_key, Body=_eicar())

        clean_status = _wait_scan_tag(aws, clean_key, sleep=sleep)
        record(
            f"el archivo limpio queda NO_THREATS_FOUND (obtuvo {clean_status})",
            clean_status == "NO_THREATS_FOUND",
        )
        record(
            "el archivo limpio ya se puede leer",
            clean_status == "NO_THREATS_FOUND"
            and not _denied(lambda: s3.get_object(Bucket=BUCKET, Key=clean_key)),
        )

        virus_status = _wait_scan_tag(aws, virus_key, sleep=sleep)
        record(
            f"el archivo EICAR queda THREATS_FOUND (obtuvo {virus_status})",
            virus_status == "THREATS_FOUND",
        )
        record(
            "el archivo EICAR no se puede leer",
            _denied(lambda: s3.get_object(Bucket=BUCKET, Key=virus_key)),
        )

        record(
            "no se puede falsificar la etiqueta de escaneo",
            _denied(
                lambda: s3.put_object_tagging(
                    Bucket=BUCKET,
                    Key=virus_key,
                    Tagging={"TagSet": [{"Key": SCAN_TAG, "Value": "NO_THREATS_FOUND"}]},
                )
            )
            and _denied(
                lambda: s3.put_object(
                    Bucket=BUCKET,
                    Key=f"{VERIFY_PREFIX}{run_id}-falso.txt",
                    Body=b"x",
                    Tagging=f"{SCAN_TAG}=NO_THREATS_FOUND",
                )
            ),
        )
    finally:
        for key in (clean_key, virus_key):
            try:
                s3.delete_object(Bucket=BUCKET, Key=key)
            except ClientError as error:
                print(f"  no se pudo borrar {key}: {_code(error)}")

    record("el permiso de la app solo cubre leads/*", _app_permissions_ok(aws))
    return all(passed for _, passed in results)


def _app_permissions_ok(aws: Aws) -> bool:
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{APP_ROLE}"
    expected = {
        ("s3:PutObject", f"arn:aws:s3:::{BUCKET}/{OBJECT_PREFIX}x"): True,
        ("s3:GetObject", f"arn:aws:s3:::{BUCKET}/{OBJECT_PREFIX}x"): True,
        ("s3:DeleteObject", f"arn:aws:s3:::{BUCKET}/{OBJECT_PREFIX}x"): True,
        ("s3:ListBucket", f"arn:aws:s3:::{BUCKET}"): False,
        ("s3:PutObjectTagging", f"arn:aws:s3:::{BUCKET}/{OBJECT_PREFIX}x"): False,
        ("s3:PutObject", f"arn:aws:s3:::{BUCKET}/otro/x"): False,
    }
    for (action, resource), allowed in expected.items():
        response = aws.iam.simulate_principal_policy(
            PolicySourceArn=role_arn, ActionNames=[action], ResourceArns=[resource]
        )
        decision = response["EvaluationResults"][0]["EvalDecision"]
        if (decision == "allowed") != allowed:
            print(
                f"  {action} sobre {resource}: {decision} (se esperaba {'allowed' if allowed else 'denegado'})"
            )
            return False
    return True


# --------------------------------------------------------------------------------------------
# rollback
# --------------------------------------------------------------------------------------------


def rollback(aws: Aws, *, sleep: Sleeper = time.sleep) -> None:
    """Elimina la infraestructura. Se niega si el bucket tiene adjuntos reales."""
    s3, iam = aws.s3, aws.iam
    if _bucket_exists(aws):
        listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=OBJECT_PREFIX)
        real = [
            item["Key"]
            for item in listing.get("Contents", [])
            if not item["Key"].startswith(VERIFY_PREFIX)
        ]
        if real:
            raise InfraError(f"el bucket tiene {len(real)} adjuntos reales: no se elimina nada")

    print("[1/5] plan de GuardDuty")
    plan = find_plan(aws)
    if plan is not None:
        aws.guardduty.delete_malware_protection_plan(
            MalwareProtectionPlanId=plan["MalwareProtectionPlanId"]
        )
        sleep(5)

    print("[2/5] permiso de la app")
    if _read(lambda: iam.get_role_policy(RoleName=APP_ROLE, PolicyName=APP_POLICY)):
        iam.delete_role_policy(RoleName=APP_ROLE, PolicyName=APP_POLICY)

    print("[3/5] bucket")
    if _bucket_exists(aws):
        _read(lambda: s3.delete_bucket_policy(Bucket=BUCKET))
        for item in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=item["Key"])
        s3.delete_bucket(Bucket=BUCKET)

    print("[4/5] rol de GuardDuty")
    if _read(lambda: iam.get_role(RoleName=GUARDDUTY_ROLE)):
        if _read(lambda: iam.get_role_policy(RoleName=GUARDDUTY_ROLE, PolicyName=GUARDDUTY_ROLE)):
            iam.delete_role_policy(RoleName=GUARDDUTY_ROLE, PolicyName=GUARDDUTY_ROLE)
        iam.delete_role(RoleName=GUARDDUTY_ROLE)

    print("[5/5] estado final")
    print_checks(inspect(aws))


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("command", choices=["plan", "apply", "verify", "rollback"])
    parser.add_argument("--profile", default=None, help="perfil de AWS (por ejemplo tpi-dev)")
    parser.add_argument("--confirmar", default="", help="frase de confirmacion de apply o rollback")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    aws_factory: Callable[[str | None], Aws] = build_aws,
    sleep: Sleeper = time.sleep,
) -> int:
    args = _parser().parse_args(argv)
    aws = aws_factory(args.profile)
    try:
        caller = require_account(aws)
        print(f"cuenta {ACCOUNT_ID} region {REGION} como {caller}")
        if args.command == "plan":
            print_checks(inspect(aws))
            return 0
        if args.command == "verify":
            return 0 if verify(aws, sleep=sleep) else 1
        phrase = APPLY_PHRASE if args.command == "apply" else ROLLBACK_PHRASE
        if args.confirmar != phrase:
            print_checks(inspect(aws))
            print(f'\nNo se cambio nada. Para {args.command} repite con: --confirmar "{phrase}"')
            return 2
        if args.command == "apply":
            apply(aws, sleep=sleep)
        else:
            rollback(aws, sleep=sleep)
        return 0
    except InfraError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
