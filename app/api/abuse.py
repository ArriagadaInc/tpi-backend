"""Small DEV-only abuse controls without external infrastructure dependencies."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request, status


@dataclass
class InMemoryRateLimiter:
    """Fixed-window limiter appropriate only for a DEV single instance."""

    max_requests: int
    window_seconds: int
    attempts: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, client_key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        attempts = self.attempts[client_key]
        while attempts and attempts[0] <= window_start:
            attempts.popleft()
        if len(attempts) >= self.max_requests:
            return False
        attempts.append(now)
        return True


def resolve_client_ip(request: Request, trusted_proxy_cidrs: str) -> str:
    """Honor X-Forwarded-For only when the direct peer is an approved proxy."""
    direct_peer = request.client.host if request.client else "unknown"
    trusted_networks = [
        ip_network(value.strip()) for value in trusted_proxy_cidrs.split(",") if value.strip()
    ]
    if not trusted_networks:
        return direct_peer

    try:
        peer_is_trusted = any(ip_address(direct_peer) in network for network in trusted_networks)
    except ValueError:
        return direct_peer

    if not peer_is_trusted:
        return direct_peer
    forwarded_for = request.headers.get("x-forwarded-for", "")
    return forwarded_for.split(",", maxsplit=1)[0].strip() or direct_peer


def enforce_rate_limit(request: Request) -> None:
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    client_key = resolve_client_ip(request, request.app.state.settings.api_trusted_proxy_cidrs)
    if not limiter.allow(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Intenta nuevamente mas tarde.",
        )
