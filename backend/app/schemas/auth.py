"""Autenticación, organizaciones, auditoría y uso."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.summary import PriceRow

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
    support_org: OrgRef | None = Field(None, description="Organización en la que el superadministrador está como soporte")


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
    users: int = Field(0, description="Usuarios activos de la organización")
    pending_invitations: int = Field(0, description="Invitaciones vigentes sin aceptar")
    invitations_today: int = Field(0, description="Invitaciones creadas hoy")
    invite_days: int = Field(7, description="Días de vigencia de una invitación")
    limits: dict


OrgKind = Literal["apr", "consultora", "sanitaria", "otra"]
PlanName = Literal["basico", "profesional", "ilimitado"]


class OrgInfo(BaseModel):
    """Datos de contacto de la organización (todos opcionales)."""
    model_config = ConfigDict(extra="forbid")
    rut: str | None = Field(None, max_length=20)
    region: str | None = Field(None, max_length=80)
    comuna: str | None = Field(None, max_length=80)
    address: str | None = Field(None, max_length=200, description="Dirección")
    contact: str | None = Field(None, max_length=120, description="Persona de contacto")
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    kind: str
    plan: str
    limits: dict | None
    suspended: bool
    created_at: datetime
    info: dict | None = None


class OrgDataUpdate(BaseModel):
    """Lo que el administrador de la organización puede cambiar (no plan, límites ni suspensión)."""
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=200)
    kind: OrgKind | None = None
    info: OrgInfo | None = None


class OrgAdminOut(OrgOut):
    members: int
    usage: Usage


class OrgCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=200)
    kind: OrgKind = "apr"
    plan: PlanName = "basico"
    admin_email: str | None = Field(None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OrgCreated(BaseModel):
    org: OrgOut
    admin_invitation: str | None


class OrgUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=2, max_length=200)
    plan: PlanName | None = None
    limits: dict[str, int | None] | None = None
    suspended: bool | None = None
    confirm: str | None = Field(None, max_length=200, description="Nombre de la organización (exigido para suspender)")


class OrgDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(max_length=200, description="Nombre exacto de la organización")


class LimitUse(BaseModel):
    key: str
    label: str
    used: float
    limit: float | None
    ratio: float | None = Field(None, description="Uso / límite (0–1+); sin límite = None")


class OrgDetail(BaseModel):
    org: OrgOut
    usage: Usage
    limits_use: list[LimitUse]
    members: list[MemberOut]


class NearLimit(BaseModel):
    org: OrgOut
    worst: LimitUse


class AdminOverview(BaseModel):
    orgs_active: int
    orgs_suspended: int
    users_total: int
    users_active: int
    projects_total: int
    ortho_count: int
    ortho_mb: float
    disk_total_gb: float | None
    disk_used_gb: float | None
    disk_free_gb: float | None
    near_limit: list[NearLimit]
    recent_audit: list["AuditOut"]


class PlansUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plans: dict[PlanName, dict[str, int | None]]


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
    is_superadmin: bool | None = None


class InvitationOut(BaseModel):
    id: str = Field(description="Identificador corto de la invitación")
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime


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


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200, description="Nombre visible")


class OrgSettings(BaseModel):
    """Ajustes de la organización: se aplican a los proyectos nuevos y a los que no tienen valores propios."""
    model_config = ConfigDict(extra="forbid")
    default_profile_id: int | None = Field(None, description="Perfil de criterios de diseño para proyectos nuevos")
    service_life: dict[str, int] | None = Field(None, description="Vida útil por material (años); vacío = sugerida")
    default_life: int | None = Field(None, ge=1, le=200)
    life_verified: bool = False
    prices: list[PriceRow] | None = Field(None, description="Precios de renovación por metro (material, DN máximo, CLP/m)")
    prices_verified: bool = False


class ServiceStatus(BaseModel):
    name: str
    status: Literal["ok", "error", "sin datos"]
    detail: str | None = None


class SystemInfo(BaseModel):
    api_version: str
    engine: dict
    services: list[ServiceStatus]
    last_backup: dict | None = Field(None, description="Último respaldo automático (fecha, carpeta, tamaño)")
    plans: dict[str, dict]


AdminOverview.model_rebuild()
