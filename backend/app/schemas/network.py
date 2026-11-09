"""Representación de la red como GeoJSON (EPSG:4326) y opciones hidráulicas.

Es la representación de dominio que comparten la API, el validador, el escritor/lector .inp
y el repositorio. Unidades SI: m, mm (diámetros), L/s (caudal), m³ (volumen).
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

HeadlossFormula = Literal["H-W", "D-W", "C-M"]
DemandModel = Literal["DDA", "PDA"]
NodeKind = Literal["junction", "reservoir", "tank"]
LinkKind = Literal["pipe", "pump", "valve"]
ElevationSource = Literal["manual", "inp", "supuesta"]
LengthChoice = Literal["plan", "slope", "manual"]
LinkStatus = Literal["open", "closed", "cv", "active"]
ValveType = Literal["PRV", "PSV", "PBV", "FCV", "TCV", "GPV", "PCV"]

ROUGHNESS_MEANING: dict[str, str] = {
    "H-W": "Coeficiente C de Hazen-Williams (adimensional)",
    "D-W": "Rugosidad absoluta ε de Darcy-Weisbach (mm)",
    "C-M": "Coeficiente n de Chezy-Manning (s/m^1/3)",
}


class HydraulicOptions(BaseModel):
    """Opciones hidráulicas del modelo. La rugosidad de los tramos se interpreta según `headloss`."""

    model_config = ConfigDict(extra="forbid")

    headloss: HeadlossFormula = "H-W"
    demand_model: DemandModel = "DDA"
    minimum_pressure: float = Field(0.0, description="PDA: presión bajo la cual no hay entrega (m)")
    required_pressure: float = Field(15.0, description="PDA: presión para entregar la demanda completa (m)")
    pressure_exponent: float = Field(0.5, gt=0, description="PDA: exponente de la relación presión-caudal")
    extra: dict[str, str] = Field(
        default_factory=dict,
        description="Otras opciones del motor en formato .inp (TRIALS, ACCURACY, PATTERN, ...)",
    )


class DemandCategory(BaseModel):
    base: float = Field(description="Demanda base (L/s)")
    pattern: str | None = None
    name: str | None = None


class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] = Field(description="[longitud, latitud] EPSG:4326")


class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] = Field(min_length=2, description="[[lon, lat], ...] EPSG:4326")


class NodeProperties(BaseModel):
    element: Literal["node"] = "node"
    uid: str | None = None
    kind: NodeKind
    description: str | None = None
    elevation: float | None = Field(None, description="Cota de terreno (m)")
    elevation_source: ElevationSource = "manual"
    elevation_method: str | None = None
    base_demand: float = Field(0.0, description="Demanda base (L/s)")
    demand_pattern: str | None = None
    demands: list[DemandCategory] = Field(default_factory=list, description="Categorías de demanda adicionales")
    emitter_coeff: float | None = None
    initial_quality: float | None = None
    head: float | None = Field(None, description="Reservorio: carga total (m)")
    head_pattern: str | None = None
    init_level: float | None = Field(None, description="Estanque: nivel inicial (m)")
    min_level: float | None = None
    max_level: float | None = None
    tank_diameter: float | None = Field(None, description="Estanque: diámetro (m)")
    min_volume: float | None = Field(None, description="Estanque: volumen mínimo (m³)")
    volume_curve: str | None = None
    can_overflow: bool = False


class LinkProperties(BaseModel):
    element: Literal["link"] = "link"
    uid: str | None = None
    kind: LinkKind = "pipe"
    from_node: str = Field(description="ID del nudo inicial")
    to_node: str = Field(description="ID del nudo final")
    description: str | None = None
    dn: int | None = Field(None, description="Diámetro nominal (mm)")
    inner_diameter_mm: float | None = Field(None, description="Diámetro interior de cálculo (mm)")
    material: str | None = None
    pipe_class: str | None = None
    catalog_pipe_id: int | None = None
    roughness: float | None = Field(None, description="C (H-W), ε mm (D-W) o n (C-M)")
    minor_loss: float = 0.0
    initial_status: LinkStatus = "open"
    length_plan_m: float | None = Field(None, description="Largo geométrico en planta (m)")
    length_slope_m: float | None = Field(None, description="Largo con pendiente desde las cotas (m)")
    length_hydraulic_m: float | None = Field(None, description="Largo usado en el cálculo (m)")
    length_choice: LengthChoice = "slope"
    pump_curve: str | None = None
    pump_power: float | None = Field(None, description="Potencia constante (kW)")
    pump_speed: float | None = None
    pump_pattern: str | None = None
    valve_type: ValveType | None = None
    valve_setting: float | None = None
    valve_curve: str | None = None


class NodeFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID EPANET del nudo")
    geometry: PointGeometry
    properties: NodeProperties


class LinkFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID EPANET del tramo")
    geometry: LineStringGeometry
    properties: LinkProperties


def _feature_tag(v: Any) -> str:
    if isinstance(v, dict):
        props = v.get("properties") or {}
        geom = v.get("geometry") or {}
        element = props.get("element")
        if element in ("node", "link"):
            return element
        return "node" if geom.get("type") == "Point" else "link"
    return "node" if isinstance(v, NodeFeature) else "link"


Feature = Annotated[
    Annotated[NodeFeature, Tag("node")] | Annotated[LinkFeature, Tag("link")],
    Discriminator(_feature_tag),
]


class NetworkFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature] = Field(default_factory=list)

    def nodes(self) -> list[NodeFeature]:
        return [f for f in self.features if isinstance(f, NodeFeature)]

    def links(self) -> list[LinkFeature]:
        return [f for f in self.features if isinstance(f, LinkFeature)]


class NetworkModel(BaseModel):
    """Modelo hidráulico completo: red + opciones + secciones complementarias (.inp)."""

    title: str = ""
    options: HydraulicOptions = Field(default_factory=HydraulicOptions)
    aux: dict[str, str] = Field(
        default_factory=dict,
        description="Secciones .inp complementarias en texto (times, patterns, curves, controls, rules, ...)",
    )
    network: NetworkFeatureCollection = Field(default_factory=NetworkFeatureCollection)
