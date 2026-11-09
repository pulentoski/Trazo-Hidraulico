import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.hydraulic.messages import EngineMessage
from app.schemas.network import HydraulicOptions
from app.schemas.validation import ValidationReport


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: int = Field(description="Número de versión del modelo a simular")


class EngineInfo(BaseModel):
    engine: str
    wheel_package: str
    wheel_version: str
    en_getversion: int
    epanet_tag: str | None
    epanet_sha: str | None
    runepanet_banner: str | None


class NodeSeries(BaseModel):
    pressure: list[float] = Field(description="Presión (m)")
    head: list[float] = Field(description="Cota piezométrica (m)")
    demand: list[float] = Field(description="Demanda (L/s; negativa en fuentes)")


class LinkSeries(BaseModel):
    flow: list[float] = Field(description="Caudal (L/s); signo según sentido nudo inicial → final")
    velocity: list[float] = Field(description="Velocidad (m/s)")
    headloss: list[float] = Field(description="Pérdida unitaria (m/km) en tuberías; pérdida (m) en bombas y válvulas")
    status: list[int]


class CriteriaAlert(BaseModel):
    code: Literal["PRESSURE_LOW", "PRESSURE_HIGH", "VELOCITY_LOW", "VELOCITY_HIGH", "BOTTLENECK"]
    severity: Literal["warning"] = "warning"
    message: str
    element_type: Literal["node", "link"]
    element_id: str
    value: float
    limit: float
    unit: str
    time: int


class SimulationResult(BaseModel):
    run_id: uuid.UUID
    project_id: uuid.UUID
    model_version: int
    status: Literal["ok", "warning", "error"]
    cached: bool
    created_at: datetime
    elapsed_ms: float
    engine: EngineInfo
    options: HydraulicOptions
    inp_sha256: str
    times: list[int] = Field(description="Instantes de reporte (s)")
    nodes: dict[str, NodeSeries]
    links: dict[str, LinkSeries]
    messages: list[EngineMessage]
    alerts: list[CriteriaAlert]
    validation: ValidationReport
    profile_name: str | None = None
    profile_verified: bool = False


class SimulationBlocked(BaseModel):
    status: Literal["blocked"] = "blocked"
    model_version: int
    detail: str
    validation: ValidationReport
