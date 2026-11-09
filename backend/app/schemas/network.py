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
InnerDiameterSource = Literal["catalogo", "manual"]
ClientType = Literal["residencial", "comercial", "industrial", "publico"]
ClientStatus = Literal["activo", "proyectado", "suspendido"]
ConsumptionUnit = Literal["L/s", "m3/mes"]
ConnectionMode = Literal["nearest", "new_node"]
ShutoffState = Literal["open", "closed"]
PipeCondition = Literal["bueno", "regular", "malo", "fuera_servicio"]
NetworkType = Literal["matriz", "distribucion", "aduccion", "impulsion"]
ShutoffType = Literal["compuerta", "mariposa", "bola", "otra"]
AssetCondition = Literal["bueno", "regular", "malo", "inoperativo"]
HydrantType = Literal["columna", "subterraneo"]
AttrValue = str | int | float | None
Attributes = dict[str, AttrValue]
ATTRIBUTES_DESC = "Atributos libres (columnas no reconocidas de la planilla): nombre → valor"

# Conversión de m³/mes a L/s con mes de 30 días (facturación habitual).
SECONDS_PER_MONTH = 30 * 86400


def to_lps(value: float, unit: str) -> float:
    return value if unit == "L/s" else value * 1000.0 / SECONDS_PER_MONTH

ROUGHNESS_MEANING: dict[str, str] = {
    "H-W": "Coeficiente C de Hazen-Williams (adimensional)",
    "D-W": "Rugosidad absoluta ε de Darcy-Weisbach (mm)",
    "C-M": "Coeficiente n de Chezy-Manning (s/m^1/3)",
}


class LevelControl(BaseModel):
    """Control por nivel de un estanque: enciende (abre) bajo `on_below` y apaga (cierra) sobre `off_above`."""

    model_config = ConfigDict(extra="forbid")
    tank: str = Field(description="ID del estanque")
    on_below: float = Field(description="Nivel (m sobre el fondo) bajo el cual enciende")
    off_above: float = Field(description="Nivel (m sobre el fondo) sobre el cual apaga")


class HydraulicOptions(BaseModel):
    """Opciones hidráulicas del modelo. La rugosidad de los tramos se interpreta según `headloss`."""

    model_config = ConfigDict(extra="forbid")

    headloss: HeadlossFormula = "H-W"
    demand_model: DemandModel = "DDA"
    include_projected_clients: bool = Field(
        False, description="Sumar también los clientes en estado «proyectado» a la demanda de su nudo")
    minimum_pressure: float = Field(0.0, description="PDA: presión bajo la cual no hay entrega (m)")
    required_pressure: float = Field(15.0, description="PDA: presión para entregar la demanda completa (m)")
    pressure_exponent: float = Field(0.5, gt=0, description="PDA: exponente de la relación presión-caudal")
    duration_h: float | None = Field(
        None, ge=0, le=8760, description="Duración de la simulación (h). None = la de [TIMES] (estática si no hay)")
    hydraulic_step_min: int = Field(60, ge=1, le=1440, description="Paso hidráulico (min)")
    pattern_step_min: int = Field(60, ge=1, le=1440, description="Paso de los patrones (min)")
    report_step_min: int = Field(60, ge=1, le=1440, description="Paso de reporte (min)")
    demand_multiplier: float = Field(1.0, gt=0, description="Multiplicador global de demandas (escenario de demanda)")
    demand_scenario: str | None = Field(None, description="Escenario de demanda aplicado (base, actual, horizonte)")
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
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)


class LinkProperties(BaseModel):
    element: Literal["link"] = "link"
    uid: str | None = None
    kind: LinkKind = "pipe"
    from_node: str = Field(description="ID del nudo inicial")
    to_node: str = Field(description="ID del nudo final")
    description: str | None = None
    dn: int | None = Field(None, description="Diámetro nominal (mm)")
    inner_diameter_mm: float | None = Field(None, description="Diámetro interior de cálculo (mm)")
    inner_diameter_source: InnerDiameterSource = Field(
        "catalogo", description="Origen del diámetro interior: catálogo o ingreso manual")
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
    schedule: list[int] | None = Field(
        None, min_length=24, max_length=24, description="Bomba o válvula: horario 0/1 por hora (0–23 h)")
    level_control: LevelControl | None = Field(None, description="Bomba o válvula: control por nivel de estanque")
    curve_points: list[tuple[float, float]] | None = Field(
        None, min_length=1, max_length=20, description="Bomba: curva caudal (L/s) – altura (m), 1 o 3+ puntos")
    condition: PipeCondition | None = Field(None, description="Estado físico (gestión)")
    install_year: int | None = Field(None, ge=1850, le=2200, description="Año de instalación")
    network_type: NetworkType | None = Field(None, description="Tipo de red")
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)


class ClientProperties(BaseModel):
    element: Literal["client"] = "client"
    uid: str | None = None
    name: str | None = Field(None, description="Nombre o dirección")
    client_type: ClientType = "residencial"
    status: ClientStatus = "activo"
    consumption_value: float = Field(ge=0, description="Consumo en la unidad indicada")
    consumption_unit: ConsumptionUnit = "L/s"
    node: str = Field(description="ID del nudo de consumo al que se conecta")
    link: str | None = Field(None, description="Tubería sobre la que se proyectó el arranque")
    connection: tuple[float, float] | None = Field(None, description="Punto de conexión [lon, lat]")
    connection_mode: ConnectionMode = "nearest"
    elevation: float | None = Field(None, description="Cota del terreno en el cliente (m)")
    client_number: str | None = Field(None, max_length=40, description="N° de cliente")
    address: str | None = Field(None, max_length=200, description="Dirección")
    route: str | None = Field(None, max_length=40, description="Ruta de lectura")
    meter_number: str | None = Field(None, max_length=40, description="N° de medidor")
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)

    @property
    def consumption_lps(self) -> float:
        return to_lps(self.consumption_value, self.consumption_unit)


class ShutoffProperties(BaseModel):
    element: Literal["shutoff"] = "shutoff"
    uid: str | None = None
    name: str | None = None
    link: str = Field(description="ID de la tubería donde está la llave")
    position: float = Field(0.5, ge=0, le=1, description="Posición a lo largo de la tubería (0 = inicio, 1 = fin)")
    state: ShutoffState = "open"
    valve_type: ShutoffType | None = Field(None, description="Tipo de válvula de corte")
    condition: AssetCondition | None = Field(None, description="Condición; una válvula inoperativa no sirve para cortar")
    diameter_mm: float | None = Field(None, description="Diámetro (mm)")
    depth_m: float | None = Field(None, description="Profundidad (m)")
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)


class HydrantProperties(BaseModel):
    element: Literal["hydrant"] = "hydrant"
    uid: str | None = None
    node: str = Field(description="ID del nudo de consumo al que se conecta")
    description: str | None = Field(None, description="Observaciones")
    hydrant_type: HydrantType | None = None
    condition: AssetCondition | None = None
    diameter_mm: float | None = Field(None, description="Diámetro de salida (mm)")
    fire_flow_lps: float = Field(16.0, gt=0, description="Caudal de incendio requerido (L/s)")
    min_pressure_m: float = Field(5.0, ge=0, description="Presión residual mínima durante el incendio (m)")
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)


class PumpLine(BaseModel):
    """Tramo de la columna o de la impulsión del pozo."""

    model_config = ConfigDict(extra="forbid")
    material: str | None = None
    dn: int | None = Field(None, description="Diámetro nominal (mm)")
    pipe_class: str | None = None
    inner_diameter_mm: float = Field(gt=0, description="Diámetro interior (mm)")
    length_m: float = Field(ge=0, description="Largo (m)")
    roughness: float | None = Field(None, gt=0, description="C (H-W), ε mm (D-W) o n (C-M); vacío = 140 / 0,0015 / 0,009")


class WellPumpDesign(BaseModel):
    """Datos de diseño del bombeo del pozo (hoja BombaPozo1 de ModeloPozo)."""

    model_config = ConfigDict(extra="forbid")
    pump_depth_m: float = Field(ge=0, description="Profundidad de instalación de la bomba bajo el terreno (m)")
    design_flow_lps: float = Field(gt=0, description="Caudal de diseño (L/s)")
    column: PumpLine = Field(description="Columna (de la bomba a la superficie)")
    impulsion: PumpLine = Field(description="Impulsión (de la superficie a la llegada)")
    arrival_elevation_m: float | None = Field(None, description="Cota de llegada (m). Vacío = cota de rebalse del estanque")
    arrival_tank: str | None = Field(None, description="Estanque de llegada (ID)")
    minor_loss_pct: float = Field(5.0, ge=0, le=100, description="Pérdidas singulares (% de la altura)")
    pump_efficiency: float = Field(0.75, gt=0, le=1, description="Rendimiento de la bomba (0–1)")
    motor_efficiency: float = Field(0.9, gt=0, le=1, description="Rendimiento del motor (0–1)")
    power_factor: float = Field(0.85, gt=0, le=1, description="Factor de potencia")
    voltage_v: float = Field(380.0, gt=0, description="Tensión trifásica (V)")


class WellProperties(BaseModel):
    element: Literal["well"] = "well"
    uid: str | None = None
    node: str | None = Field(None, description="ID del reservorio que representa el pozo en el modelo")
    description: str | None = Field(None, description="Observaciones")
    condition: AssetCondition | None = None
    ground_elevation: float | None = Field(None, description="Cota de terreno (m)")
    depth_m: float | None = Field(None, ge=0, description="Profundidad (m)")
    static_level_m: float | None = Field(None, ge=0, description="Nivel estático bajo el terreno (m)")
    dynamic_level_m: float | None = Field(None, ge=0, description="Nivel dinámico bajo el terreno (m)")
    authorized_flow_lps: float | None = Field(None, ge=0, description="Caudal autorizado (L/s)")
    pump_design: WellPumpDesign | None = Field(None, description="Diseño del bombeo (columna, impulsión, rendimientos)")
    attributes: Attributes = Field(default_factory=dict, description=ATTRIBUTES_DESC)


class ValveScenario(BaseModel):
    """Escenario de operación de llaves: las llaves listadas quedan cerradas; el resto, abiertas."""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=120)
    closed: list[str] = Field(default_factory=list, description="IDs de llaves cerradas")


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


class ClientFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID del cliente")
    geometry: PointGeometry
    properties: ClientProperties


class ShutoffFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID de la llave")
    geometry: PointGeometry
    properties: ShutoffProperties


class HydrantFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID del grifo")
    geometry: PointGeometry
    properties: HydrantProperties


class WellFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str = Field(description="ID del pozo")
    geometry: PointGeometry
    properties: WellProperties


def _feature_tag(v: Any) -> str:
    if isinstance(v, dict):
        props = v.get("properties") or {}
        geom = v.get("geometry") or {}
        element = props.get("element")
        if element in ("node", "link", "client", "shutoff", "hydrant", "well"):
            return element
        return "node" if geom.get("type") == "Point" else "link"
    return {NodeFeature: "node", LinkFeature: "link", ClientFeature: "client", ShutoffFeature: "shutoff",
            HydrantFeature: "hydrant", WellFeature: "well"}[type(v)]


Feature = Annotated[
    Annotated[NodeFeature, Tag("node")] | Annotated[LinkFeature, Tag("link")]
    | Annotated[ClientFeature, Tag("client")] | Annotated[ShutoffFeature, Tag("shutoff")]
    | Annotated[HydrantFeature, Tag("hydrant")] | Annotated[WellFeature, Tag("well")],
    Discriminator(_feature_tag),
]


class NetworkFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature] = Field(default_factory=list)

    def nodes(self) -> list[NodeFeature]:
        return [f for f in self.features if isinstance(f, NodeFeature)]

    def links(self) -> list[LinkFeature]:
        return [f for f in self.features if isinstance(f, LinkFeature)]

    def clients(self) -> list[ClientFeature]:
        return [f for f in self.features if isinstance(f, ClientFeature)]

    def shutoffs(self) -> list[ShutoffFeature]:
        return [f for f in self.features if isinstance(f, ShutoffFeature)]

    def hydrants(self) -> list[HydrantFeature]:
        return [f for f in self.features if isinstance(f, HydrantFeature)]

    def wells(self) -> list[WellFeature]:
        return [f for f in self.features if isinstance(f, WellFeature)]


class NetworkModel(BaseModel):
    """Modelo hidráulico completo: red + opciones + secciones complementarias (.inp)."""

    title: str = ""
    options: HydraulicOptions = Field(default_factory=HydraulicOptions)
    aux: dict[str, str] = Field(
        default_factory=dict,
        description="Secciones .inp complementarias en texto (times, patterns, curves, controls, rules, ...)",
    )
    network: NetworkFeatureCollection = Field(default_factory=NetworkFeatureCollection)
    scenarios: list[ValveScenario] = Field(default_factory=list, description="Escenarios de llaves personalizados")

    def client_demands(self) -> dict[str, list[ClientFeature]]:
        """Clientes que aportan demanda, por nudo (activos; también proyectados si la opción lo indica)."""
        out: dict[str, list[ClientFeature]] = {}
        for c in self.network.clients():
            if c.properties.status == "activo" or self.options.include_projected_clients:
                out.setdefault(c.properties.node, []).append(c)
        return out

    def closed_links(self, closed_shutoffs: set[str] | None = None) -> set[str]:
        """Tuberías cerradas por llaves (estado propio de cada llave, o el conjunto dado por un escenario) y
        tuberías marcadas «fuera de servicio»."""
        out = {lk.id for lk in self.network.links() if lk.properties.condition == "fuera_servicio"}
        for sh in self.network.shutoffs():
            closed = sh.id in closed_shutoffs if closed_shutoffs is not None else sh.properties.state == "closed"
            if closed:
                out.add(sh.properties.link)
        return out
