"""Definición de las hojas de la planilla: una por tipo de elemento, con columnas, unidades y listas.

La misma definición sirve para la plantilla, la exportación, la importación (vista previa y aplicación),
las consultas y las exportaciones GeoPackage. Las claves internas (`key`) son nombres de propiedades del
modelo; las que empiezan con «_» se tratan aparte (geometría, clase de válvula, etc.).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

PIPE_CONDITION = {"bueno": "bueno", "regular": "regular", "malo": "malo", "fuera_servicio": "fuera de servicio"}
ASSET_CONDITION = {"bueno": "bueno", "regular": "regular", "malo": "malo", "inoperativo": "inoperativo"}
NETWORK_TYPE = {"matriz": "matriz", "distribucion": "distribución", "aduccion": "aducción", "impulsion": "impulsión"}
PIPE_STATUS = {"open": "abierta", "closed": "cerrada", "cv": "retención"}
PUMP_STATUS = {"open": "abierta", "closed": "cerrada"}
LENGTH_CHOICE = {"plan": "planta", "slope": "con pendiente", "manual": "manual"}
VALVE_CLASS = {"corte": "corte", "control": "control"}
VALVE_TYPE = {"compuerta": "compuerta", "mariposa": "mariposa", "bola": "bola", "otra": "otra",
              "PRV": "PRV", "PSV": "PSV", "PBV": "PBV", "FCV": "FCV", "TCV": "TCV", "GPV": "GPV", "PCV": "PCV"}
SHUTOFF_TYPES = {"compuerta", "mariposa", "bola", "otra"}
VALVE_STATE = {"open": "abierta", "closed": "cerrada", "active": "activa"}
HYDRANT_TYPE = {"columna": "columna", "subterraneo": "subterráneo"}
CLIENT_TYPE = {"residencial": "residencial", "comercial": "comercial", "industrial": "industrial", "publico": "público"}
CLIENT_STATUS = {"activo": "activo", "proyectado": "proyectado", "suspendido": "suspendido"}
CONSUMPTION_UNIT = {"L/s": "L/s", "m3/mes": "m3/mes"}
YES_NO = {"si": "sí", "no": "no"}


def norm(text: object) -> str:
    """Texto normalizado para comparar encabezados y valores de lista: sin tildes, minúsculas, sin espacios extra."""
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[\s_]+", " ", s)


@dataclass(frozen=True)
class Col:
    key: str
    header: str
    kind: str = "str"  # str | float | int | choice | bool | lat | lon | east | north | vertices
    unit: str = ""
    desc: str = ""
    choices: dict[str, str] | None = None
    strict: bool = True  # lista cerrada (False: la lista es sugerencia; se acepta otro texto)
    required: bool = False  # obligatoria al crear el elemento
    computed: bool = False  # solo se exporta (no se importa ni se compara)
    aliases: tuple[str, ...] = ()
    query: bool = True  # disponible en consultas

    @property
    def is_geo(self) -> bool:
        return self.kind in ("lat", "lon", "east", "north")

    def label_of(self, value: object) -> object:
        if value is None:
            return None
        if self.choices is not None:
            return self.choices.get(str(value), value)
        if self.kind == "bool":
            return "sí" if value else "no"
        return value


GEO = (
    Col("_lat", "Latitud", "lat", "°", "Latitud WGS84 (negativa al sur). Use Latitud/Longitud o Este/Norte",
        aliases=("lat",), query=False),
    Col("_lon", "Longitud", "lon", "°", "Longitud WGS84 (negativa al oeste)", aliases=("lon", "lng"), query=False),
    Col("_east", "Este", "east", "m", "Coordenada UTM Este (huso indicado al importar)", aliases=("e", "utm e", "x"),
        query=False),
    Col("_north", "Norte", "north", "m", "Coordenada UTM Norte", aliases=("n", "utm n", "y"), query=False),
)


@dataclass(frozen=True)
class Sheet:
    key: str  # clave interna (nudos, tramos, ...)
    name: str  # nombre de la hoja
    element: str  # node | link | shutoff_or_valve | hydrant | well | client
    kind: str | None  # junction | tank | reservoir | pipe | pump | None
    prefix: str  # prefijo de IDs generados
    title: str  # nombre en singular para mensajes
    cols: tuple[Col, ...] = field(default_factory=tuple)
    sum_field: str | None = None  # campo que se suma en consultas

    def col(self, key: str) -> Col | None:
        return next((c for c in self.cols if c.key == key), None)

    @property
    def has_points(self) -> bool:
        return any(c.is_geo for c in self.cols)


ID = Col("id", "ID", "str", "", "Identificador único (máx. 31 caracteres, sin espacios). Vacío = lo genera el sistema",
         aliases=("codigo", "código"))


def _sheets() -> tuple[Sheet, ...]:
    desc = Col("description", "Observaciones", desc="Texto libre", aliases=("descripcion", "descripción"))
    return (
        Sheet("nudos", "Nudos", "node", "junction", "J", "nudo", (
            ID, *GEO,
            Col("elevation", "Cota", "float", "m", "Cota de terreno del nudo", required=True),
            Col("base_demand", "Demanda base", "float", "L/s", "Demanda manual adicional a la de los clientes"),
            Col("demand_pattern", "Patrón de demanda", desc="ID del patrón (curva de modulación)"),
            desc,
        )),
        Sheet("tramos", "Tramos", "link", "pipe", "P", "tramo", (
            ID,
            Col("from_node", "Nudo inicial", desc="ID del nudo, estanque o reservorio inicial", required=True),
            Col("to_node", "Nudo final", desc="ID del nudo final", required=True),
            Col("_vertices", "Vértices", "vertices", "",
                "Opcional: puntos intermedios «lat lon; lat lon» (o «E N; E N» en UTM)", query=False),
            Col("dn", "DN", "int", "mm", "Diámetro nominal"),
            Col("inner_diameter_mm", "D interior", "float", "mm", "Vacío = se toma del catálogo (material, DN y clase)"),
            Col("material", "Material", "choice", "", "Material de la tubería", choices={}, strict=False),
            Col("pipe_class", "Clase", desc="Clase o presión nominal (C10, PN10…)"),
            Col("roughness", "Rugosidad", "float", "", "C de Hazen-Williams (o ε mm / n según la fórmula). "
                "Vacío = catálogo"),
            Col("minor_loss", "Coef. pérdidas singulares", "float", "", "Coeficiente K de pérdidas menores"),
            Col("initial_status", "Estado hidráulico", "choice", "", "Abierta, cerrada o con retención",
                choices=PIPE_STATUS),
            Col("length_choice", "Largo de cálculo", "choice", "", "Planta, con pendiente o manual",
                choices=LENGTH_CHOICE),
            Col("_length_manual", "Largo manual", "float", "m", "Solo si «Largo de cálculo» es manual", query=False),
            Col("length_hydraulic_m", "Largo", "float", "m", "Largo usado en el cálculo (calculado; no se importa)",
                computed=True),
            Col("condition", "Estado", "choice", "", "Estado físico", choices=PIPE_CONDITION),
            Col("install_year", "Año de instalación", "int", "", "Año (AAAA)"),
            Col("network_type", "Tipo de red", "choice", "", "Matriz, distribución, aducción o impulsión",
                choices=NETWORK_TYPE),
            desc,
        ), sum_field="length_hydraulic_m"),
        Sheet("estanques", "Estanques", "node", "tank", "E", "estanque", (
            ID, *GEO,
            Col("elevation", "Cota de fondo", "float", "m", "Cota del fondo del estanque", required=True),
            Col("init_level", "Nivel inicial", "float", "m", "Nivel de agua inicial sobre el fondo", required=True),
            Col("min_level", "Nivel mínimo", "float", "m", "", required=True),
            Col("max_level", "Nivel máximo", "float", "m", "", required=True),
            Col("tank_diameter", "Diámetro", "float", "m", "Diámetro equivalente (cilindro)", required=True),
            Col("min_volume", "Volumen mínimo", "float", "m³", ""),
            Col("volume_curve", "Curva de volumen", desc="ID de la curva (opcional)"),
            Col("can_overflow", "Rebalse", "bool", "", "Sí / no", choices=None),
            desc,
        )),
        Sheet("reservorios", "Reservorios", "node", "reservoir", "R", "reservorio", (
            ID, *GEO,
            Col("elevation", "Cota de terreno", "float", "m", "Cota del terreno (referencial)"),
            Col("head", "Carga total", "float", "m", "Cota piezométrica de la fuente. Vacío con pozo asociado = "
                "cota del pozo − nivel dinámico"),
            Col("head_pattern", "Patrón de carga", desc="ID del patrón (opcional)"),
            desc,
        )),
        Sheet("valvulas", "Válvulas", "valve", None, "V", "válvula", (
            ID,
            Col("_class", "Clase", "choice", "", "Corte (sobre un tramo) o control (PRV, FCV…, entre dos nudos)",
                choices=VALVE_CLASS),
            Col("_type", "Tipo", "choice", "", "Corte: compuerta, mariposa, bola, otra. Control: PRV, PSV, PBV, "
                "FCV, TCV, GPV, PCV", choices=VALVE_TYPE),
            Col("_state", "Estado", "choice", "", "Abierta o cerrada (control: también activa)", choices=VALVE_STATE),
            Col("condition", "Condición", "choice", "", "Una válvula inoperativa no sirve para cortar",
                choices=ASSET_CONDITION),
            Col("_diameter", "Diámetro", "float", "mm", ""),
            Col("_depth", "Profundidad", "float", "m", "Profundidad de la válvula"),
            Col("link", "Tramo", desc="Corte: ID del tramo. Vacío con coordenadas = el tramo más cercano"),
            Col("position", "Posición", "float", "0–1", "Corte: fracción del largo del tramo desde el nudo inicial"),
            *GEO,
            Col("from_node", "Nudo inicial", desc="Control: nudo aguas arriba"),
            Col("to_node", "Nudo final", desc="Control: nudo aguas abajo"),
            Col("valve_setting", "Consigna", "float", "", "Control: presión (m), caudal (L/s) o coeficiente"),
            Col("valve_curve", "Curva", desc="Control GPV: ID de la curva"),
            Col("name", "Nombre", desc="Nombre o referencia en terreno"),
        )),
        Sheet("grifos", "Grifos", "hydrant", None, "G", "grifo", (
            ID, *GEO,
            Col("node", "Nudo", desc="ID del nudo de consumo. Vacío con coordenadas = el más cercano"),
            Col("hydrant_type", "Tipo", "choice", "", "Columna o subterráneo", choices=HYDRANT_TYPE),
            Col("condition", "Estado", "choice", "", "Condición", choices=ASSET_CONDITION),
            Col("diameter_mm", "Diámetro", "float", "mm", "Diámetro de salida"),
            Col("fire_flow_lps", "Caudal de incendio", "float", "L/s", "Caudal requerido (16 L/s por defecto; "
                "no verificado)"),
            Col("min_pressure_m", "Presión residual mínima", "float", "m", "Presión mínima durante el incendio "
                "(5 m por defecto; no verificado)"),
            desc,
        )),
        Sheet("pozos", "Pozos", "well", None, "PZ", "pozo", (
            ID, *GEO,
            Col("node", "Reservorio asociado", desc="ID del reservorio que representa el pozo en el modelo"),
            Col("ground_elevation", "Cota de terreno", "float", "m", ""),
            Col("depth_m", "Profundidad", "float", "m", ""),
            Col("static_level_m", "Nivel estático", "float", "m", "Profundidad del nivel estático bajo el terreno"),
            Col("dynamic_level_m", "Nivel dinámico", "float", "m", "Profundidad del nivel de bombeo bajo el terreno"),
            Col("authorized_flow_lps", "Caudal autorizado", "float", "L/s", "Derecho de aprovechamiento"),
            Col("condition", "Estado", "choice", "", "Condición", choices=ASSET_CONDITION),
            desc,
        )),
        Sheet("bombas", "Bombas", "link", "pump", "B", "bomba", (
            ID,
            Col("from_node", "Nudo inicial", desc="Nudo de succión", required=True),
            Col("to_node", "Nudo final", desc="Nudo de descarga", required=True),
            Col("_vertices", "Vértices", "vertices", "", "Opcional: «lat lon; lat lon»", query=False),
            Col("pump_curve", "Curva", desc="ID de la curva caudal–altura (o use Potencia)"),
            Col("pump_power", "Potencia", "float", "kW", "Potencia constante (si no hay curva)"),
            Col("pump_speed", "Velocidad relativa", "float", "", "1 = nominal"),
            Col("pump_pattern", "Patrón", desc="Patrón de velocidad (opcional)"),
            Col("initial_status", "Estado inicial", "choice", "", "Abierta (en marcha) o cerrada", choices=PUMP_STATUS),
            desc,
        )),
        Sheet("clientes", "Clientes", "client", None, "C", "cliente", (
            ID,
            Col("client_number", "N° cliente", desc="Número de cliente (comercial)"),
            Col("name", "Nombre", desc="Nombre del titular"),
            Col("address", "Dirección", desc=""),
            Col("route", "Ruta", desc="Ruta de lectura"),
            Col("meter_number", "N° medidor", desc="Número de medidor", aliases=("medidor",)),
            Col("client_type", "Tipo", "choice", "", "Residencial, comercial, industrial o público", choices=CLIENT_TYPE),
            Col("status", "Estado", "choice", "", "Activo, proyectado o suspendido (solo los activos suman demanda)",
                choices=CLIENT_STATUS),
            Col("consumption_value", "Consumo", "float", "", "Consumo en la unidad indicada", required=True),
            Col("consumption_unit", "Unidad", "choice", "", "L/s o m3/mes", choices=CONSUMPTION_UNIT),
            *GEO,
            Col("node", "Nudo", desc="ID del nudo que lo abastece. Vacío = el más cercano a las coordenadas"),
            Col("link", "Tramo", desc="ID del tramo que lo abastece (opcional)"),
            Col("elevation", "Cota", "float", "m", "Cota del terreno en el cliente"),
        ), sum_field="_consumption_lps"),
    )


SHEETS: tuple[Sheet, ...] = _sheets()
SHEET_BY_KEY = {s.key: s for s in SHEETS}
SHEET_BY_NAME = {norm(s.name): s for s in SHEETS} | {s.key: s for s in SHEETS}
NODE_SHEETS = ("nudos", "estanques", "reservorios")
MODEL_SHEET = "Modelo"
INSTRUCTIONS_SHEET = "Instrucciones"


def with_materials(materials: list[str]) -> None:
    """Completa la lista de materiales del catálogo (sugerencia, no cerrada)."""
    col = SHEET_BY_KEY["tramos"].col("material")
    assert col is not None and col.choices is not None
    col.choices.clear()
    col.choices.update({m: m for m in materials})
