"""Esquemas de análisis: escenarios de llaves, factibilidad de nuevos clientes e importación de clientes."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.hydraulic.messages import EngineMessage
from app.schemas.simulation import EngineInfo

BUILTIN_SCENARIOS = {"normal": "Operación normal (todas abiertas)", "todas_cerradas": "Todas cerradas",
                     "actual": "Estado del modelo (cada llave según su estado)"}


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: int
    scenario: str = Field("normal", description="normal, todas_cerradas, actual o el ID de un escenario personalizado")


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: int
    a: str = "normal"
    b: str


class NodeState(BaseModel):
    id: str
    supplied: bool
    pressure: float | None = Field(None, description="Presión mínima del periodo (m); None si no hay suministro")
    demand: float = Field(0.0, description="Demanda de diseño del nudo (L/s)")


class ClientState(BaseModel):
    id: str
    name: str | None
    node: str
    status: str
    consumption_lps: float
    supplied: bool
    pressure: float | None
    below_min: bool
    affected: bool = Field(description="Sin suministro o bajo la presión mínima")


class ScenarioResult(BaseModel):
    project_id: str
    model_version: int
    scenario: str
    scenario_name: str
    closed_shutoffs: list[str]
    closed_links: list[str]
    pressure_min: float
    nodes: list[NodeState]
    clients: list[ClientState]
    unsupplied_nodes: list[str]
    unsupplied_links: list[str] = Field(description="Tramos sin suministro (ambos extremos desconectados)")
    summary: dict[str, float]
    messages: list[EngineMessage]
    inp_sha256: str


class CompareRow(BaseModel):
    kind: str  # nudo | cliente
    id: str
    name: str | None = None
    a: float | None
    b: float | None
    diff: float | None
    supplied_a: bool
    supplied_b: bool


class CompareResult(BaseModel):
    a: ScenarioResult
    b: ScenarioResult
    rows: list[CompareRow]


# ── Factibilidad ──
class FeasibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_version: int
    link: str = Field(description="Tubería donde se conecta el nuevo cliente")
    point: tuple[float, float] = Field(description="Punto [lon, lat]; se proyecta sobre la tubería")
    consumption_lps: float = Field(gt=0, le=10000)
    elevation: float = Field(description="Cota del terreno en el punto (m)")
    name: str | None = Field(None, max_length=200)


class AffectedClient(BaseModel):
    id: str
    name: str | None
    node: str
    before: float | None
    after: float | None
    newly_below: bool


class LinkIssue(BaseModel):
    id: str
    dn: int | None
    velocity_before: float
    velocity_after: float
    headloss_before: float
    headloss_after: float
    over_velocity: bool
    over_headloss: bool


class UpgradeAttempt(BaseModel):
    link: str
    material: str | None
    pipe_class: str | None
    dn_from: int | None
    dn_to: int | None
    inner_from: float | None
    inner_to: float | None
    pressure_new: float | None
    feasible: bool
    note: str | None = None


class Criterion(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    source: str
    verified: bool


class FeasibilityResult(BaseModel):
    feasible: bool
    verdict: str
    project_id: str
    project_name: str
    model_version: int
    created_at: datetime
    analysis: str = Field(description="DDA o PDA")
    engine: EngineInfo
    inp_sha256: str
    location: tuple[float, float] = Field(description="Punto de conexión sobre la tubería [lon, lat]")
    link: str
    distance_m: float
    new_node: str
    split_links: tuple[str, str]
    consumption_lps: float
    elevation: float
    criteria: list[Criterion]
    pressure_new: float | None
    margin: float | None
    affected_clients: list[AffectedClient]
    link_issues: list[LinkIssue]
    bottleneck: str | None
    upgrades: list[UpgradeAttempt]
    upgrade_feasible: bool | None = Field(None, description="Si aumentar el DN del cuello de botella lo hace factible")
    messages: list[EngineMessage]
    reasons: list[str]


# ── Importación de clientes ──
class ClientImportRow(BaseModel):
    line: int
    id: str
    name: str | None
    consumption_lps: float
    node: str
    link: str
    distance_m: float
    warning: str | None = None


class ClientImportResult(BaseModel):
    version: int
    created: int
    rows: list[ClientImportRow]
