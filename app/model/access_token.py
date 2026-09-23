from typing import List, Optional

from app.utils.token_utils import decode_jwt

SUPER_ADMIN_ROLES = {"SUPER ADMIN", "SUPERADMIN"}


def _normalise_role(role: str) -> str:
    value = str(role or "").strip().upper().replace("_", " ")
    if value.startswith("ROLE "):
        value = value[5:].strip()
    return value


class AccessToken:
    user_id: Optional[str]
    roles: List[str]
    authorities: List[str]
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    email: Optional[str]
    client_id: Optional[str]
    tenant_id: Optional[str]
    token: Optional[str]

    def __init__(self, token):
        decoded_data = decode_jwt(token)

        self.user_id = decoded_data.get("user_id", "")
        # JWT uses "role" (singular string) in this system; fall back to "roles" for compatibility
        _roles_raw = decoded_data.get("roles") or decoded_data.get("role", "")
        self.roles = _roles_raw if isinstance(_roles_raw, list) else ([_roles_raw] if _roles_raw else [])
        _authorities = decoded_data.get("authorities") or []
        self.authorities = _authorities if isinstance(_authorities, list) else [_authorities]
        self.first_name = decoded_data.get("first_name", "")
        self.last_name = decoded_data.get("last_name", "")
        self.email = decoded_data.get("sub", "")
        client_id = decoded_data.get("client_id", "")
        self.client_id = str(client_id) if client_id not in (None, "") else ""
        self.tenant_id = decoded_data.get("tenant_id", "")
        self.full_name = " ".join(filter(None, [self.first_name, self.last_name]))
        self.token = token

    @property
    def is_super_admin(self) -> bool:
        candidates = [*self.roles, *self.authorities]
        return any(_normalise_role(role) in SUPER_ADMIN_ROLES for role in candidates)
