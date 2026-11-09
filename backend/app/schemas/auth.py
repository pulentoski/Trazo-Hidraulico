"""Autenticación, organizaciones, auditoría y uso."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "proyectista", "revisor", "lector"]


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LoginOut(BaseModel):
    mfa_required: bool


class CodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=8)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class RecoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)


class RecoverOut(BaseModel):
    email_enabled: bool = Field(description="Hay correo saliente; si no, pida un enlace al administrador")


class ResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=256)


class OrgRef(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class Me(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_superadmin: bool
    mfa_enabled: bool
    mfa_pending: bool
    mfa_setup_required: bool
    current_org: uuid.UUID | None
    orgs: list[OrgRef]


class AuthStatus(BaseModel):
    email_enabled: bool
    mfa_required_for_admins: bool
    password_min_length: int


class MfaSetup(BaseModel):
    secret: str
    uri: str
    qr_svg: str


class MfaDisable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=256)


class SessionOut(BaseModel):
    id: str = Field(description="Identificador corto de la sesión")
    current: bool
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class OrgSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    org_id: uuid.UUID


class InvitationInfo(BaseModel):
    org_name: str
    email: str
    role: Role
    existing_user: bool


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field("", max_length=200)
    password: str = Field(max_length=256)


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role
    send_email: bool = True


class LinkOut(BaseModel):
    link: str
    emailed: bool = False


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: Role
    active: bool
    mfa_enabled: bool
    last_login_at: datetime | None


class MemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role | None = None
    active: bool | None = None


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    user_email: str | None
    action: str
    project_id: uuid.UUID | None
    version: int | None
    detail: dict | None
    ip: str | None


class Usage(BaseModel):
    month: str
    simulations: int
    map_loads: int
    ortho_mb: float
    projects: int
    limits: dict


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    kind: str
    plan: str
    limits: dict | None
    suspended: bool
    created_at: datetime


class OrgAdminOut(OrgOut):
    members: int
    usage: Usage


class OrgCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=200)
    kind: Literal["apr", "consultora", "sanitaria", "otra"] = "apr"
    plan: Literal["basico", "profesional", "ilimitado"] = "basico"
    admin_email: str | None = Field(None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrgCreated(BaseModel):
    org: OrgOut
    admin_invitation: str | None


class OrgUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=200)
    plan: Literal["basico", "profesional", "ilimitado"] | None = None
    limits: dict[str, int | None] | None = None
    suspended: bool | None = None


class UserAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    active: bool
    is_superadmin: bool
    mfa_enabled: bool
    locked: bool
    last_login_at: datetime | None
    orgs: list[OrgRef]


class UserAdminUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool | None = None


class MapLoadOut(BaseModel):
    allowed: bool
    count: int
    limit: int | None


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["comentario", "aprobada", "observada"]
    comment: str = Field("", max_length=4000)


class ReviewOut(BaseModel):
    id: int
    version: int
    user_email: str | None
    status: str
    comment: str
    created_at: datetime
