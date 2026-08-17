"""PII-safe HMAC fingerprints for idempotent public requests."""

from __future__ import annotations

import hashlib
import hmac
import json

from app.api.schemas import PublicLeadCreateRequest


def build_payload_fingerprint(request: PublicLeadCreateRequest, secret: str) -> str:
    """Return a keyed fingerprint without persisting the original payload."""
    canonical_payload = request.model_dump(mode="json", exclude={"honeypot"})
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
