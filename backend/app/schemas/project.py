import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.network import HydraulicOptions, NetworkFeatureCollection, ValveScenario

VersionKind = Literal["auto", "manual", "import"]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    length_srid: int | None = Field(None, description="SRID métrico para largos (por defecto LENGTH_SRID, p. ej. 32719)")
    design_profile_id: int | None = None
    options: HydraulicOptions | None = None


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    length_srid: int | None = None
    design_profile_id: int | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str
    length_srid: int
    design_profile_id: int | None
    created_at: datetime
    updated_at: datetime
    latest_version: int | None = None
    version_count: int = 0
    client_count: int | None = Field(None, description="Clientes de la última versión (solo en el listado)")
    network_km: float | None = Field(None, description="Km de tuberías de la última versión (solo en el listado)")


class VersionOut(BaseModel):
    number: int
    kind: VersionKind
    label: str | None
    parent_number: int | None
    created_at: datetime
    content_sha256: str
    node_count: int
    link_count: int
    has_results: bool = False


class NetworkDocument(BaseModel):
    """Red de una versión: GeoJSON + opciones hidráulicas + secciones complementarias."""
    project_id: uuid.UUID
    version: int
    kind: VersionKind
    label: str | None
    created_at: datetime
    length_srid: int
    options: HydraulicOptions
    aux: dict[str, str]
    network: NetworkFeatureCollection
    scenarios: list[ValveScenario] = Field(default_factory=list)


class NetworkSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_version: int | None = Field(None, description="Versión sobre la que se editó (control de concurrencia)")
    kind: Literal["auto", "manual"] = "auto"
    label: str | None = Field(None, max_length=200)
    options: HydraulicOptions | None = Field(None, description="Si se omite, se conservan las de la versión base")
    aux: dict[str, str] | None = None
    network: NetworkFeatureCollection
    scenarios: list[ValveScenario] | None = Field(None, description="Si se omite, se conservan los de la versión base")


class LinkLengths(BaseModel):
    length_plan_m: float | None
    length_slope_m: float | None
    length_hydraulic_m: float | None


class NetworkSaveResult(BaseModel):
    version: int
    created: bool = Field(description="False si el contenido era idéntico a la versión base (guardado automático)")
    content_sha256: str
    lengths: dict[str, LinkLengths] = Field(description="Largos recalculados por ID de tramo")


class ImportResult(BaseModel):
    project: ProjectOut
    version: int
    georeference: str
    notes: list[str]
    node_count: int
    link_count: int
