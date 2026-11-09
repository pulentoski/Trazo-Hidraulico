"""Registro de funcionamiento: mediciones reales y comparación con el modelo."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ElementType = Literal["node", "link", "client", "well"]
Kind = Literal["meter", "pressure", "level"]


class MeasurementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    element_type: ElementType
    element_id: str = Field(min_length=1, max_length=31)
    kind: Kind = Field(description="meter: lectura de medidor (m³); pressure: presión (m); level: nivel (m)")
    measured_at: datetime
    value: float
    note: str | None = Field(None, max_length=200)


class MeasurementOut(MeasurementIn):
    id: int


class MonitoringSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flow_pct: float = Field(10.0, gt=0, le=100, description="Tolerancia de caudal (% del medido)")
    pressure_m: float = Field(2.0, gt=0, description="Tolerancia de presión (m)")
    level_m: float = Field(0.3, gt=0, description="Tolerancia de nivel (m)")


class ComparePoint(BaseModel):
    time: datetime
    measured: float
    model: float | None
    diff: float | None
    ok: bool | None


class CompareSeries(BaseModel):
    element_type: ElementType
    element_id: str
    kind: Kind
    quantity: str = Field(description="Magnitud comparada (caudal L/s, presión m, nivel m)")
    unit: str
    points: list[ComparePoint]
    average_measured: float | None = Field(None, description="Medidor: caudal medio entre la primera y la última lectura")
    max_abs_diff: float | None
    tolerance: float
    alert: bool
    message: str


class MeasureCompareResult(BaseModel):
    project_id: str
    model_version: int
    settings: MonitoringSettings
    series: list[CompareSeries]


class MeasurementImportResult(BaseModel):
    created: int
    errors: list[str]
