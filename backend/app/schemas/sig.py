"""Esquemas del SIG: importación desde planilla, cuarteles de corta, consultas, grifos y ortofotos."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Scalar = str | int | float | bool | None


class FieldChange(BaseModel):
    field: str = Field(description="Encabezado de la columna")
    old: Scalar = None
    new: Scalar = None


class ChangeItem(BaseModel):
    sheet: str = Field(description="Nombre de la hoja")
    id: str
    row: int | None = Field(None, description="Fila del archivo (None si el cambio no viene de una fila)")
    changes: list[FieldChange] = Field(default_factory=list)


class RowError(BaseModel):
    sheet: str | None = None
    row: int | None = None
    id: str | None = None
    message: str


class SheetSummary(BaseModel):
    sheet: str
    new: int = 0
    modified: int = 0
    unchanged: int = 0
    deleted: int = 0
    errors: int = 0


class ImportPreview(BaseModel):
    ok: bool = Field(description="Sin errores: se puede aplicar")
    base_version: int | None = None
    coord_srid: int = Field(description="SRID UTM usado para Este/Norte")
    delete_missing: bool = False
    new: list[ChangeItem] = Field(default_factory=list)
    modified: list[ChangeItem] = Field(default_factory=list)
    unchanged: list[ChangeItem] = Field(default_factory=list)
    deleted: list[ChangeItem] = Field(default_factory=list)
    errors: list[RowError] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    summary: list[SheetSummary] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.new or self.modified or self.deleted)


class ImportApplyResult(BaseModel):
    version: int | None = Field(None, description="Versión creada (None si no hubo cambios)")
    created: bool
    project_id: str
    preview: ImportPreview


# ── Cuarteles de corta ──

class SectorPiece(BaseModel):
    link: str
    start: float = Field(ge=0, le=1, description="Fracción inicial del tramo")
    end: float = Field(ge=0, le=1, description="Fracción final del tramo")


class Sector(BaseModel):
    id: str = Field(description="Código del cuartel (C-01, C-02, …)")
    valves: list[str] = Field(description="Válvulas a cerrar para aislar el cuartel")
    links: list[str] = Field(description="Tramos (total o parcialmente) dentro del cuartel")
    pieces: list[SectorPiece]
    length_m: float = Field(description="Metros de red dentro del cuartel")
    nodes: list[str]
    clients: list[str] = Field(description="Clientes del cuartel (quedan sin agua al cortarlo)")
    downstream_nodes: list[str] = Field(description="Nudos de otros cuarteles que pierden su fuente al cerrar")
    downstream_clients: list[str] = Field(description="Clientes de otros sectores que también quedan sin agua")
    affected_clients: int
    affected_consumption_lps: float
    has_source: bool = Field(description="El cuartel contiene una fuente (reservorio o estanque)")


class SectorsResult(BaseModel):
    project_id: str
    model_version: int
    sectors: list[Sector]
    inoperative_valves: list[str] = Field(default_factory=list, description="Válvulas ignoradas (inoperativas)")
    notes: list[str] = Field(default_factory=list)


# ── Consultas ──

Op = Literal["eq", "ne", "lt", "le", "gt", "ge", "contains", "starts", "in", "empty", "not_empty"]


class Condition(BaseModel):
    field: str
    op: Op = "eq"
    value: Scalar | list[Scalar] = None


class ConditionGroup(BaseModel):
    logic: Literal["and", "or"] = "and"
    conditions: list[Condition | ConditionGroup] = Field(default_factory=list)


class QueryDef(BaseModel):
    element: str = Field(description="Hoja/tipo de elemento: nudos, tramos, clientes, …")
    where: ConditionGroup = Field(default_factory=ConditionGroup)


class QueryRequest(QueryDef):
    model_version: int | None = None


class QueryField(BaseModel):
    key: str
    label: str
    type: Literal["str", "float", "int", "choice", "bool"]
    unit: str = ""
    choices: list[tuple[str, str]] | None = None


class QueryElement(BaseModel):
    key: str
    label: str
    fields: list[QueryField]
    sum_field: str | None = None


class QueryResult(BaseModel):
    element: str
    model_version: int
    count: int
    total: int = Field(description="Elementos del tipo en el modelo")
    sums: dict[str, float] = Field(default_factory=dict)
    columns: list[QueryField]
    rows: list[dict[str, Scalar]]


class SavedQueryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: QueryDef


class SavedQueryOut(SavedQueryIn):
    id: int
    created_at: datetime


class SearchHit(BaseModel):
    element: str = Field(description="Hoja del elemento")
    element_type: str = Field(description="node | link | client | shutoff | hydrant | well")
    id: str
    text: str
    match: str = Field(description="Campo que coincide")


# ── Grifos ──

class HydrantResult(BaseModel):
    id: str
    node: str
    fire_flow_lps: float
    min_pressure_m: float
    static_pressure_m: float | None = Field(None, description="Presión sin incendio (mínima del periodo)")
    residual_pressure_m: float | None = Field(None, description="Presión con el caudal de incendio (mínima)")
    available_flow_lps: float | None = Field(None, description="Caudal disponible a la presión residual mínima")
    ok: bool | None = None
    message: str | None = None


class FireResult(BaseModel):
    project_id: str
    model_version: int
    hydrants: list[HydrantResult]


# ── Ortofotos ──

class Gcp(BaseModel):
    px: float = Field(description="Columna en la imagen (píxeles, origen arriba a la izquierda)")
    py: float = Field(description="Fila en la imagen (píxeles)")
    lon: float
    lat: float


class GcpFit(BaseModel):
    method: Literal["similitud", "afín"]
    world: list[float] = Field(description="Parámetros del archivo world [A, D, B, E, C, F] en el SRID indicado")
    srid: int
    residuals_m: list[float]
    rms_m: float


class OrthophotoOut(BaseModel):
    id: str
    name: str
    source: str | None
    captured_on: date | None
    georef: Literal["geotiff", "worldfile", "gcp"]
    status: Literal["uploaded", "pending", "processing", "ready", "error"]
    error: str | None
    original_name: str
    src_crs: str | None
    residual_m: float | None
    width: int | None
    height: int | None
    bounds: list[float] | None
    size_bytes: int
    opacity: float
    visible: bool
    created_at: datetime
    tile_url: str | None = Field(None, description="Plantilla XYZ de teselas ({z}/{x}/{y})")


class OrthophotoUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    source: str | None = Field(None, max_length=200)
    captured_on: date | None = None
    opacity: float | None = Field(None, ge=0, le=1)
    visible: bool | None = None


class GcpRequest(BaseModel):
    gcps: list[Gcp] = Field(min_length=2, max_length=50)
    apply: bool = Field(False, description="Procesar la ortofoto con este ajuste")


ConditionGroup.model_rebuild()
