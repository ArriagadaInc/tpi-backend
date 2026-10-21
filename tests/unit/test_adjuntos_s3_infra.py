"""Pruebas de deployment/aws/adjuntos_s3_infra.py con un AWS simulado en memoria."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from typing import Any

import pytest
from botocore.exceptions import ClientError

from deployment.aws import adjuntos_s3_infra as infra


def _error(code: str, message: str = "", operation: str = "op") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message or code}}, operation)


class FakeS3:
    def __init__(self, owner: FakeAws) -> None:
        self.owner = owner
        self.exists = False
        self.config: dict[str, Any] = {}
        self.objects: dict[str, dict[str, Any]] = {}
        self.versioning: str | None = None

    def _mutate(self, name: str) -> None:
        self.owner.mutations.append(name)

    def _missing(self, key: str, code: str) -> Any:
        if key not in self.config:
            raise _error(code)
        return self.config[key]

    def head_bucket(self, Bucket: str) -> None:
        if not self.exists:
            raise _error("404")

    def create_bucket(self, Bucket: str, **kwargs: Any) -> None:
        self._mutate("create_bucket")
        self.exists = True
        self.config["ownership"] = {
            "OwnershipControls": {"Rules": [{"ObjectOwnership": kwargs["ObjectOwnership"]}]}
        }

    def put_bucket_tagging(self, Bucket: str, Tagging: dict[str, Any]) -> None:
        self._mutate("put_bucket_tagging")
        self.config["tagging"] = Tagging

    def get_bucket_tagging(self, Bucket: str) -> dict[str, Any]:
        return self._missing("tagging", "NoSuchTagSet")

    def put_public_access_block(self, Bucket: str, PublicAccessBlockConfiguration: dict) -> None:
        self._mutate("put_public_access_block")
        self.config["bpa"] = {"PublicAccessBlockConfiguration": PublicAccessBlockConfiguration}

    def get_public_access_block(self, Bucket: str) -> dict[str, Any]:
        return self._missing("bpa", "NoSuchPublicAccessBlockConfiguration")

    def put_bucket_ownership_controls(self, Bucket: str, OwnershipControls: dict) -> None:
        self._mutate("put_bucket_ownership_controls")
        self.config["ownership"] = {"OwnershipControls": OwnershipControls}

    def get_bucket_ownership_controls(self, Bucket: str) -> dict[str, Any]:
        return self._missing("ownership", "OwnershipControlsNotFoundError")

    def put_bucket_encryption(self, Bucket: str, ServerSideEncryptionConfiguration: dict) -> None:
        self._mutate("put_bucket_encryption")
        self.config["encryption"] = {
            "ServerSideEncryptionConfiguration": ServerSideEncryptionConfiguration
        }

    def get_bucket_encryption(self, Bucket: str) -> dict[str, Any]:
        return self._missing("encryption", "ServerSideEncryptionConfigurationNotFoundError")

    def put_bucket_lifecycle_configuration(self, Bucket: str, LifecycleConfiguration: dict) -> None:
        self._mutate("put_bucket_lifecycle_configuration")
        self.config["lifecycle"] = LifecycleConfiguration

    def get_bucket_lifecycle_configuration(self, Bucket: str) -> dict[str, Any]:
        return self._missing("lifecycle", "NoSuchLifecycleConfiguration")

    def get_bucket_versioning(self, Bucket: str) -> dict[str, Any]:
        return {"Status": self.versioning} if self.versioning else {}

    def put_bucket_policy(self, Bucket: str, Policy: str) -> None:
        self._mutate("put_bucket_policy")
        self.config["policy"] = {"Policy": Policy}

    def get_bucket_policy(self, Bucket: str) -> dict[str, Any]:
        return self._missing("policy", "NoSuchBucketPolicy")

    def delete_bucket_policy(self, Bucket: str) -> None:
        self._mutate("delete_bucket_policy")
        self.config.pop("policy", None)

    def delete_bucket(self, Bucket: str) -> None:
        self._mutate("delete_bucket")
        self.exists = False
        self.config = {}
        self.objects = {}

    # objetos -------------------------------------------------------------------------------
    def put_object(self, Bucket: str, Key: str, Body: bytes, Tagging: str = "") -> None:
        if infra.SCAN_TAG in Tagging:
            raise _error("AccessDenied")
        self._mutate("put_object")
        self.objects[Key] = {"body": Body, "tags": {}}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        tags = self.objects[Key]["tags"]
        if tags.get(infra.SCAN_TAG) != "NO_THREATS_FOUND":
            raise _error("AccessDenied")
        return {"Body": self.objects[Key]["body"]}

    def get_object_tagging(self, Bucket: str, Key: str) -> dict[str, Any]:
        tags = self.objects[Key]["tags"]
        return {"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]}

    def put_object_tagging(self, Bucket: str, Key: str, Tagging: dict[str, Any]) -> None:
        raise _error("AccessDenied")

    def delete_object(self, Bucket: str, Key: str) -> None:
        self._mutate("delete_object")
        self.objects.pop(Key, None)

    def list_objects_v2(self, Bucket: str, Prefix: str = "") -> dict[str, Any]:
        keys = [key for key in self.objects if key.startswith(Prefix)]
        return {"Contents": [{"Key": key} for key in keys]} if keys else {}

    def run_scanner(self) -> None:
        """Simula a GuardDuty: etiqueta los objetos sin etiqueta."""
        for item in self.objects.values():
            if not item["tags"]:
                is_virus = b"EICAR" in item["body"]
                item["tags"][infra.SCAN_TAG] = "THREATS_FOUND" if is_virus else "NO_THREATS_FOUND"


class FakeIam:
    def __init__(self, owner: FakeAws) -> None:
        self.owner = owner
        self.roles: dict[str, dict[str, Any]] = {
            infra.APP_ROLE: {"trust": {}, "policies": {}, "tags": []}
        }

    def _role(self, name: str) -> dict[str, Any]:
        if name not in self.roles:
            raise _error("NoSuchEntity")
        return self.roles[name]

    def get_role(self, RoleName: str) -> dict[str, Any]:
        role = self._role(RoleName)
        return {"Role": {"RoleName": RoleName, "AssumeRolePolicyDocument": role["trust"]}}

    def create_role(self, RoleName: str, AssumeRolePolicyDocument: str, **kwargs: Any) -> None:
        self.owner.mutations.append("create_role")
        self.roles[RoleName] = {
            "trust": json.loads(AssumeRolePolicyDocument),
            "policies": {},
            "tags": kwargs.get("Tags", []),
        }

    def update_assume_role_policy(self, RoleName: str, PolicyDocument: str) -> None:
        self.owner.mutations.append("update_assume_role_policy")
        self._role(RoleName)["trust"] = json.loads(PolicyDocument)

    def put_role_policy(self, RoleName: str, PolicyName: str, PolicyDocument: str) -> None:
        self.owner.mutations.append("put_role_policy")
        self._role(RoleName)["policies"][PolicyName] = json.loads(PolicyDocument)

    def get_role_policy(self, RoleName: str, PolicyName: str) -> dict[str, Any]:
        policies = self._role(RoleName)["policies"]
        if PolicyName not in policies:
            raise _error("NoSuchEntity")
        return {"PolicyDocument": policies[PolicyName]}

    def delete_role_policy(self, RoleName: str, PolicyName: str) -> None:
        self.owner.mutations.append("delete_role_policy")
        self._role(RoleName)["policies"].pop(PolicyName, None)

    def delete_role(self, RoleName: str) -> None:
        self.owner.mutations.append("delete_role")
        self.roles.pop(RoleName, None)

    def simulate_principal_policy(
        self, PolicySourceArn: str, ActionNames: list[str], ResourceArns: list[str]
    ) -> dict[str, Any]:
        role = PolicySourceArn.rsplit("/", 1)[-1]
        allowed = False
        for policy in self._role(role)["policies"].values():
            for statement in policy["Statement"]:
                actions = statement["Action"]
                resources = statement["Resource"]
                actions = [actions] if isinstance(actions, str) else actions
                resources = [resources] if isinstance(resources, str) else resources
                if ActionNames[0] in actions and any(
                    fnmatch.fnmatch(ResourceArns[0], resource) for resource in resources
                ):
                    allowed = True
        return {"EvaluationResults": [{"EvalDecision": "allowed" if allowed else "implicitDeny"}]}


class FakeGuardDuty:
    def __init__(self, owner: FakeAws) -> None:
        self.owner = owner
        self.plans: dict[str, dict[str, Any]] = {}
        self.create_errors: list[ClientError] = []
        self.final_status = "ACTIVE"

    def list_malware_protection_plans(self, **kwargs: Any) -> dict[str, Any]:
        return {"MalwareProtectionPlans": [{"MalwareProtectionPlanId": p} for p in self.plans]}

    def get_malware_protection_plan(self, MalwareProtectionPlanId: str) -> dict[str, Any]:
        return self.plans[MalwareProtectionPlanId]

    def create_malware_protection_plan(self, **kwargs: Any) -> dict[str, Any]:
        self.owner.mutations.append("create_malware_protection_plan")
        if self.create_errors:
            raise self.create_errors.pop(0)
        plan_id = f"plan-{len(self.plans) + 1}"
        self.plans[plan_id] = {
            "Role": kwargs["Role"],
            "ProtectedResource": kwargs["ProtectedResource"],
            "Actions": kwargs["Actions"],
            "Status": self.final_status,
            "StatusReasons": [{"Code": "X"}],
        }
        return {"MalwareProtectionPlanId": plan_id}

    def delete_malware_protection_plan(self, MalwareProtectionPlanId: str) -> None:
        self.owner.mutations.append("delete_malware_protection_plan")
        self.plans.pop(MalwareProtectionPlanId)


class FakeSts:
    def __init__(self, account: str) -> None:
        self.account = account

    def get_caller_identity(self) -> dict[str, str]:
        return {"Account": self.account, "Arn": f"arn:aws:iam::{self.account}:user/Alvaro"}


class FakeAws:
    def __init__(self, account: str = infra.ACCOUNT_ID) -> None:
        self.mutations: list[str] = []
        self.s3 = FakeS3(self)
        self.iam = FakeIam(self)
        self.guardduty = FakeGuardDuty(self)
        self.sts = FakeSts(account)
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.s3.run_scanner()


@pytest.fixture
def aws() -> FakeAws:
    return FakeAws()


def _statuses(aws: FakeAws) -> dict[str, str]:
    return {check.name: check.status for check in infra.inspect(aws)}


@pytest.mark.unit
def test_plan_on_empty_account_reports_everything_missing_and_changes_nothing(
    aws: FakeAws, capsys: pytest.CaptureFixture[str]
) -> None:
    code = infra.main(["plan"], aws_factory=lambda profile: aws, sleep=aws.sleep)

    assert code == 0
    assert aws.mutations == []
    assert set(_statuses(aws).values()) == {"FALTA"}
    assert "[FALTA" in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize("command", ["apply", "rollback"])
def test_apply_and_rollback_without_the_phrase_change_nothing(aws: FakeAws, command: str) -> None:
    for wrong in ([command], [command, "--confirmar", "si"]):
        code = infra.main(wrong, aws_factory=lambda profile: aws, sleep=aws.sleep)
        assert code == 2
    assert aws.mutations == []


@pytest.mark.unit
def test_wrong_account_aborts_before_any_call() -> None:
    other = FakeAws(account="111111111111")

    code = infra.main(
        ["apply", "--confirmar", infra.APPLY_PHRASE],
        aws_factory=lambda profile: other,
        sleep=other.sleep,
    )

    assert code == 1
    assert other.mutations == []


@pytest.mark.unit
def test_apply_builds_everything_and_the_plan_reports_all_ok(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)

    statuses = _statuses(aws)
    assert set(statuses.values()) == {"OK"}, statuses
    assert aws.s3.versioning is None
    plan = next(iter(aws.guardduty.plans.values()))
    assert plan["ProtectedResource"]["S3Bucket"] == {
        "BucketName": infra.BUCKET,
        "ObjectPrefixes": ["leads/"],
    }
    assert plan["Actions"] == {"Tagging": {"Status": "ENABLED"}}
    assert plan["Role"] == infra.GUARDDUTY_ROLE_ARN


@pytest.mark.unit
def test_apply_orders_the_role_before_the_bucket_policy_and_the_plan(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)

    order = aws.mutations
    assert order.index("create_bucket") < order.index("create_role")
    assert order.index("create_role") < order.index("put_bucket_policy")
    assert order.index("put_bucket_policy") < order.index("create_malware_protection_plan")


@pytest.mark.unit
def test_apply_is_idempotent(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)
    aws.mutations.clear()

    infra.apply(aws, sleep=aws.sleep)

    assert "create_bucket" not in aws.mutations
    assert "create_role" not in aws.mutations
    assert "create_malware_protection_plan" not in aws.mutations
    assert len(aws.guardduty.plans) == 1


@pytest.mark.unit
def test_apply_without_the_app_role_changes_nothing(aws: FakeAws) -> None:
    del aws.iam.roles[infra.APP_ROLE]

    with pytest.raises(infra.InfraError, match="rol de la instancia"):
        infra.apply(aws, sleep=aws.sleep)

    assert aws.mutations == []


@pytest.mark.unit
def test_apply_refuses_a_versioned_bucket(aws: FakeAws) -> None:
    aws.s3.exists = True
    aws.s3.versioning = "Enabled"

    with pytest.raises(infra.InfraError, match="versionado"):
        infra.apply(aws, sleep=aws.sleep)

    assert "create_role" not in aws.mutations


@pytest.mark.unit
def test_plan_creation_retries_while_the_new_role_propagates(aws: FakeAws) -> None:
    aws.guardduty.create_errors = [
        _error("BadRequestException", "the role cannot be assumed"),
        _error("BadRequestException", "the role cannot be assumed"),
    ]

    infra.apply(aws, sleep=aws.sleep)

    assert aws.mutations.count("create_malware_protection_plan") == 3
    assert len(aws.guardduty.plans) == 1


@pytest.mark.unit
def test_a_detector_requirement_stops_without_retrying(aws: FakeAws) -> None:
    aws.guardduty.create_errors = [_error("BadRequestException", "A detector must be enabled")] * 3

    with pytest.raises(infra.InfraError, match="detector"):
        infra.apply(aws, sleep=aws.sleep)

    assert aws.mutations.count("create_malware_protection_plan") == 1


@pytest.mark.unit
def test_a_plan_that_ends_in_error_fails_the_apply(aws: FakeAws) -> None:
    aws.guardduty.final_status = "ERROR"

    with pytest.raises(infra.InfraError, match="ERROR"):
        infra.apply(aws, sleep=aws.sleep)


@pytest.mark.unit
def test_inspect_flags_a_different_bucket_policy(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)
    aws.s3.config["policy"] = {"Policy": json.dumps({"Version": "2012-10-17", "Statement": []})}

    assert _statuses(aws)["politica del bucket"] == "DIFIERE"


@pytest.mark.unit
def test_verify_passes_when_the_scan_gate_works(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)

    assert infra.verify(aws, sleep=aws.sleep) is True

    assert aws.s3.objects == {}  # borra los archivos de prueba


@pytest.mark.unit
def test_verify_fails_when_the_scanner_never_tags(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)

    assert infra.verify(aws, sleep=lambda seconds: None) is False

    assert aws.s3.objects == {}


@pytest.mark.unit
def test_verify_fails_when_the_app_policy_is_too_broad(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)
    aws.iam.roles[infra.APP_ROLE]["policies"][infra.APP_POLICY]["Statement"][0]["Action"].append(
        "s3:PutObjectTagging"
    )

    assert infra.verify(aws, sleep=aws.sleep) is False


@pytest.mark.unit
def test_rollback_removes_everything_when_only_test_objects_remain(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)
    aws.s3.objects[f"{infra.VERIFY_PREFIX}prueba"] = {"body": b"x", "tags": {}}

    infra.rollback(aws, sleep=aws.sleep)

    assert aws.s3.exists is False
    assert aws.guardduty.plans == {}
    assert infra.GUARDDUTY_ROLE not in aws.iam.roles
    assert infra.APP_POLICY not in aws.iam.roles[infra.APP_ROLE]["policies"]


@pytest.mark.unit
def test_rollback_refuses_to_delete_real_attachments(aws: FakeAws) -> None:
    infra.apply(aws, sleep=aws.sleep)
    aws.s3.objects["leads/abc/def"] = {"body": b"x", "tags": {}}
    aws.mutations.clear()

    with pytest.raises(infra.InfraError, match="adjuntos reales"):
        infra.rollback(aws, sleep=aws.sleep)

    assert aws.mutations == []
    assert aws.s3.exists is True


@pytest.mark.unit
def test_eicar_payload_is_the_standard_antivirus_test_string() -> None:
    payload = infra._eicar()

    assert len(payload) == 68
    assert (
        hashlib.sha256(payload).hexdigest()
        == "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
    )
