"""Panel general del proyecto («Resumen»): configuración, eventos de pérdidas y resultado agregado."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ElementType = Literal["node", "link", "client", "shutoff", "hydrant", "well"]
LeakKind = Literal["fuga", "rotura", "reparacion"]

# Vida útil sugerida por material (años). Valores de partida típicos: no verificados.
DEFAULT_LIFE: dict[str, int] = {"PVC": 50, "HDPE": 50, "PEAD": 50, "AC": 40, "Acero": 40, "FFD": 60, "HA": 50}


class PriceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    material: str = Field("*", description="Material («*» = cualquiera)")
    dn_max: int = Field(description="Se aplica a tramos con DN ≤ este valor (mm)")
    price_m: float = Field(ge=0, description="Costo de renovación por metro (CLP/m, con excavación y reposición)")


DEFAULT_PRICES = [PriceRow(material="*", dn_max=75, price_m=45000), PriceRow(material="*", dn_max=110, price_m=60000),
                  PriceRow(material="*", dn_max=200, price_m=90000), PriceRow(material="*", dn_max=100000, price_m=130000)]


class ProductionMeter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector: str = Field(min_length=1, max_length=60, description="Sector abastecido («Total» = todos los clientes)")
    element_type: Literal["well", "link"] = Field(description="Medidor del pozo o macromedidor en un tramo")
    element_id: str = Field(min_length=1, max_length=31)


class SummarySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pressure_ranges: list[float] = Field(default_factory=lambda: [15.0, 30.0, 50.0, 70.0], min_length=1, max_length=8,
                                         description="Límites de los rangos de presión (m.c.a., crecientes)")
    area_margin_m: float = Field(50.0, ge=0, le=2000, description="Margen del área operacional alrededor de red y clientes (m)")
    service_life: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_LIFE),
                                         description="Vida útil por material (años)")
    default_life: int = Field(50, ge=1, le=200, description="Vida útil de materiales sin valor propio (años)")
    life_verified: bool = Field(False, description="Vida útil revisada por el usuario")
    prices: list[PriceRow] = Field(default_factory=lambda: [p.model_copy() for p in DEFAULT_PRICES])
    prices_verified: bool = False
    top_n: Literal[10, 20] = 10
    sector_attribute: str = Field("Sector", min_length=1, max_length=40,
                                  description="Atributo libre de clientes (y tramos) que indica el sector")
    production_meters: list[ProductionMeter] = Field(
        default_factory=list, description="Medidores de producción por sector. Vacío = automático (pozos → Total; "
                                          "macromedidores → sector del tramo)")

    @field_validator("pressure_ranges")
    @classmethod
    def _ascending(cls, v: list[float]) -> list[float]:
        if any(b <= a for a, b in zip(v, v[1:])):
            raise ValueError("Los límites de los rangos de presión deben ser crecientes")
        return v


class LeakEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    link_id: str = Field(min_length=1, max_length=31, description="ID del tramo")
    event_date: date
    kind: LeakKind
    flow_lps: float | None = Field(None, ge=0, description="Caudal estimado perdido (L/s)")
    note: str | None = Field(None, max_length=300)


class LeakEventOut(LeakEventIn):
    id: int
    created_at: datetime


class LeakImportResult(BaseModel):
    created: int
    errors: list[str]


class Group(BaseModel):
    key: str
    count: int = 0
    km: float | None = None
    m3_day: float | None = None
    ids: list[str] = Field(default_factory=list)


class ElementList(BaseModel):
    type: ElementType
    count: int
    ids: list[str] = Field(default_factory=list)


class ClientsBlock(BaseModel):
    total: ElementList
    active: ElementList
    projected: ElementList
    suspended: ElementList
    connections: int = Field(description="N° de arranques (puntos de conexión distintos)")
    by_route: list[Group]
    by_sector: list[Group]


class NetworkBlock(BaseModel):
    km_total: float
    pipes: ElementList
    by_material: list[Group]
    by_dn: list[Group]
    by_condition: list[Group]
    by_age: list[Group]
    valves: ElementList
    control_valves: ElementList
    hydrants: ElementList
    tanks: ElementList
    wells: ElementList
    pumps: ElementList


class PipeClients(BaseModel):
    link: str
    clients: int
    ids: list[str]


class ValueAt(BaseModel):
    value: float
    id: str


class PressureBlock(BaseModel):
    pmin: float
    pmax: float
    min: ValueAt | None = None
    max: ValueAt | None = None
    avg: float | None = None
    below_min: ElementList
    above_max: ElementList
    clients_below: ElementList
    unsupplied: ElementList
    critical_period: int | None = None
    critical_time: int | None = None
    critical_value: float | None = None
    critical_node: str | None = None


class ZoneFeature(BaseModel):
    node: str
    pressure: float
    cls: int
    geometry: dict[str, Any]


class ZoneRange(BaseModel):
    cls: int
    label: str
    lo: float | None
    hi: float | None
    area_km2: float
    nodes: ElementList
    clients: ElementList


class ZonesBlock(BaseModel):
    ranges: list[ZoneRange]
    features: list[ZoneFeature]


class OverElevation(BaseModel):
    client: str
    name: str | None
    node: str
    ground: float
    head: float
    pmin: float
    deficit: float = Field(description="Cota de terreno + presión mínima − cota piezométrica (m)")


class Consumer(BaseModel):
    client: str
    name: str | None
    route: str | None
    lps: float
    m3_month: float
    pct: float


class ProjectionPoint(BaseModel):
    years: int
    year: int
    factor: float
    m3_day: float
    m3_month: float


class ConsumptionBlock(BaseModel):
    lps: float
    m3_day: float
    m3_month: float
    by_sector: list[Group]
    by_route: list[Group]
    projection: list[ProjectionPoint]
    projection_note: str


class AreaBlock(BaseModel):
    margin_m: float
    area_km2: float
    geometry: dict[str, Any] | None


class LinkEvents(BaseModel):
    link: str
    events: int
    last_date: date
    kinds: dict[str, int]
    flow_lps: float


class BalanceRow(BaseModel):
    sector: str
    meters: list[str]
    period_from: datetime
    period_to: datetime
    production_m3_day: float
    consumption_m3_day: float
    nrw_m3_day: float
    nrw_pct: float | None
    clients: ElementList


class LossesBlock(BaseModel):
    events: list[LeakEventOut]
    total_events: int
    by_kind: dict[str, int]
    top_links: list[LinkEvents]
    balance: list[BalanceRow]
    has_events: bool
    has_production: bool
    help: str


class LifeRow(BaseModel):
    material: str
    years: int
    suggested: int | None


class PipeLife(BaseModel):
    link: str
    material: str | None
    dn: int | None
    length_m: float
    install_year: int | None
    expiry_year: int | None
    condition: str | None
    cost: float | None


class DueBlock(BaseModel):
    years: int
    km: float
    ids: list[str]


class PlanYear(BaseModel):
    year: int
    km: float
    cost: float
    ids: list[str]


class MaintenanceBlock(BaseModel):
    current_year: int
    life: list[LifeRow]
    life_verified: bool
    prices_verified: bool
    pipes: list[PipeLife]
    expired: DueBlock
    due: list[DueBlock]
    bad_condition: ElementList
    bad_condition_km: float
    unknown_year: ElementList
    plan: list[PlanYear]
    plan_cost: float


class TankInfo(BaseModel):
    id: str
    useful_m3: float | None
    outflow_lps: float | None
    autonomy_h: float | None
    level_min: float | None = Field(None, description="Nivel mínimo alcanzado en la simulación (m)")
    level_max: float | None = None


class WellInfo(BaseModel):
    id: str
    pump: str | None
    authorized_lps: float | None
    pump_hours_day: float | None
    flow_running_lps: float | None
    m3_day: float | None
    authorized_m3_day: float | None
    use_pct: float | None
    over_authorized: bool


class TankWellBlock(BaseModel):
    tanks: list[TankInfo]
    wells: list[WellInfo]


class SummaryAlert(BaseModel):
    severity: Literal["error", "warning"]
    topic: str
    text: str
    type: ElementType | None = None
    id: str | None = None


class ScenarioOption(BaseModel):
    id: str
    name: str


class SummaryResult(BaseModel):
    project_id: str
    model_version: int
    scenario: str
    scenarios: list[ScenarioOption]
    simulated: bool
    sim_note: str | None
    times: list[int]
    period: int | None
    peak_period: int | None
    generated_at: datetime
    settings: SummarySettings
    clients: ClientsBlock
    network: NetworkBlock
    clients_per_pipe: list[PipeClients]
    pressures: PressureBlock
    zones: ZonesBlock
    over_elevation: list[OverElevation]
    over_elevation_period: int | None
    top_consumers: list[Consumer]
    consumption: ConsumptionBlock
    area: AreaBlock
    losses: LossesBlock
    maintenance: MaintenanceBlock
    tank_well: TankWellBlock
    alerts: list[SummaryAlert]
