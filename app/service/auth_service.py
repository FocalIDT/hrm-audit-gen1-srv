"""Authentication and authorisation for the audit service.

Two kinds of callers:

* Readers (the audit log UI, through the orchestrator) send the user's bearer
  token. The token is validated against the user manager, exactly like the
  other HRM services do, and only a SUPER ADMIN may read. The tenant is always
  the token's client_id, so a super admin only ever sees their own company.
* Writers (the orchestrator and other trusted services) send the shared
  X-Audit-Service-Key. There is deliberately no user-token write path: audit
  records must not be forgeable from a browser.
"""
import asyncio
import base64
import hmac
import json as _json
import time
from typing import Optional

import requests
from fastapi import Header, Request

from app.config.config import AUDIT_SERVICE_KEY, USER_MANAGER_URL
from app.config.logging_config import get_logger
from app.exception import ForbiddenException, UnauthorizedException
from app.model.access_token import AccessToken

logger = get_logger(class_name=__name__)

_token_cache: dict = {}
_CACHE_TTL = 300  # seconds
_CACHE_MAX_ENTRIES = 5000


def _jwt_exp(auth_header: str) -> float:
    try:
        token = auth_header.split(' ', 1)[-1]
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        return float(_json.loads(base64.urlsafe_b64decode(payload_b64)).get('exp', 0))
    except Exception:
        return 0.0


def _cache_is_valid(auth_header: str) -> bool:
    expires_at = _token_cache.get(auth_header)
    if expires_at is None:
        return False
    if time.time() >= expires_at:
        _token_cache.pop(auth_header, None)
        return False
    return True


def _cache_mark_valid(auth_header: str) -> None:
    if len(_token_cache) >= _CACHE_MAX_ENTRIES:
        _token_cache.clear()
    now = time.time()
    jwt_exp = _jwt_exp(auth_header)
    _token_cache[auth_header] = min(jwt_exp, now + _CACHE_TTL) if jwt_exp > now else now + _CACHE_TTL


def _validate_with_user_manager(auth_header: str) -> int:
    try:
        response = requests.get(f"{USER_MANAGER_URL}/access/by-auth-header",
                                headers={"Authorization": auth_header}, timeout=10)
        return response.status_code
    except requests.RequestException as e:
        logger.error(f"User manager unreachable while validating token: {e}")
        return 503


async def validate_token(auth_header: str) -> None:
    """Raise UnauthorizedException unless the user manager accepts the token."""
    if _cache_is_valid(auth_header):
        return
    status_code = await asyncio.to_thread(_validate_with_user_manager, auth_header)
    if status_code == 503:
        raise UnauthorizedException("Unable to verify the session right now. Please try again.", 503)
    if status_code != 200:
        raise UnauthorizedException("Your session has expired. Please sign in again.")
    _cache_mark_valid(auth_header)


async def require_super_admin(request: Request) -> AccessToken:
    """FastAPI dependency: a valid token belonging to a SUPER ADMIN of a tenant."""
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header:
        raise UnauthorizedException("Authorization header is missing")

    try:
        access_token = AccessToken(auth_header)
    except Exception:
        raise UnauthorizedException("Invalid access token")

    await validate_token(auth_header)

    if not access_token.is_super_admin:
        raise ForbiddenException("The audit log is available to super administrators only")
    if not access_token.client_id:
        raise ForbiddenException("The access token is not bound to a company")
    return access_token


def require_service_key(x_audit_service_key: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency for the write API: constant-time shared-key check."""
    if not AUDIT_SERVICE_KEY:
        # Fail closed: an unconfigured key must never mean "open to everyone".
        raise ForbiddenException("Audit ingestion is not configured")
    if not x_audit_service_key or not hmac.compare_digest(x_audit_service_key, AUDIT_SERVICE_KEY):
        raise UnauthorizedException("Invalid audit service key")
