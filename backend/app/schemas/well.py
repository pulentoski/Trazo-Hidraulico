"""Pozo y bombeo: resultado del cálculo de altura manométrica, potencia y corriente."""
from pydantic import BaseModel, Field


class PumpSegment(BaseModel):
    name: str
    material: str | None
    dn: int | None
    inner_diameter_mm: float
    length_m: float
    velocity_ms: float
    headloss_m: float


class PumpCalc(BaseModel):
    well: str
    formula: str
    conventions: str
    design_flow_lps: float
    ground_elevation: float
    static_level_elevation: float | None
    dynamic_level_elevation: float
    pump_elevation: float
    arrival_elevation: float
    segments: list[PumpSegment]
    friction_loss_m: float
    geometric_head_m: float = Field(description="Cota de llegada − cota del nivel dinámico (m)")
    minor_loss_pct: float
    manometric_head_m: float
    hydraulic_power_kw: float
    shaft_power_kw: float
    shaft_power_hp: float
    shaft_power_cv: float
    electric_power_kw: float
    current_a: float = Field(description="Corriente trifásica (A)")
    curve_points: list[tuple[float, float]] = Field(description="Curva de 3 puntos desde el punto de diseño (L/s, m)")
    warnings: list[str]
    notes: list[str]


class CurveApplied(BaseModel):
    version: int
    pump: str
    curve_points: list[tuple[float, float]]
    reservoir: str | None
    reservoir_head: float | None
