"""Proyección de demanda sanitaria y escenarios de demanda."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GrowthStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_year: int = Field(ge=1900, le=2300, description="Año desde el cual rige la tasa")
    rate_pct: float = Field(ge=-20, le=50, description="Tasa de crecimiento anual (%)")


class Addition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=1900, le=2300)
    dwellings: float = Field(ge=0, description="Viviendas que se incorporan ese año (conjunto habitacional)")


class DemandInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_year: int = Field(ge=1900, le=2300)
    model_year: int = Field(ge=1900, le=2300, description="Año que representan las demandas actuales del modelo")
    current_year: int = Field(ge=1900, le=2300, description="Año actual (escenario «año actual»)")
    base_mode: Literal["poblacion", "arranques"] = "arranques"
    base_population: float | None = Field(None, ge=0, description="Población del año base (hab)")
    base_connections: int | None = Field(None, ge=0, description="Arranques (clientes) del año base")
    persons_per_dwelling: float = Field(gt=0, description="Habitantes por vivienda")
    extra_population: float = Field(0.0, ge=0, description="Población adicional del año base (escuelas, etc.)")
    growth: list[GrowthStep] = Field(min_length=1, max_length=20, description="Tramos de tasa de crecimiento")
    additions: list[Addition] = Field(default_factory=list, max_length=20)
    horizon_years: int = Field(ge=1, le=60)
    dotation_lphd: float = Field(gt=0, le=2000, description="Dotación (L/hab/día)")
    losses_pct: float = Field(ge=0, lt=90, description="Pérdidas (%)")
    coef_day: float = Field(ge=1, le=5, description="Coeficiente de día de máximo consumo")
    coef_hour: float = Field(ge=1, le=5, description="Coeficiente de hora de máximo consumo")
    pump_hours: float = Field(gt=0, le=24, description="Horas de bombeo por día")
    regulation_pct: float = Field(ge=0, le=100, description="Volumen de regulación (% del volumen diario a QMD)")
    scenario_peak_day: bool = Field(False, description="Los escenarios aplican también el coef. de día máximo")


class DemandRow(BaseModel):
    n: int
    year: int
    population: float
    clients: float
    consumption_m3: float = Field(description="Consumo anual (m³)")
    production_m3: float = Field(description="Producción anual con pérdidas (m³)")
    qmed_lps: float
    qmd_lps: float
    qmh_lps: float
    pump_lps: float = Field(description="Caudal de bombeo: QMD·24/horas de bombeo")
    regulation_m3: float


class DemandScenario(BaseModel):
    id: Literal["base", "actual", "horizonte"]
    name: str
    year: int
    multiplier: float = Field(description="Multiplicador de demandas de nudos y clientes")


class DemandResult(BaseModel):
    project_id: str
    inputs: DemandInputs
    customized: bool
    verified: bool = False
    note: str
    rows: list[DemandRow]
    scenarios: list[DemandScenario]
    active_scenario: str | None = None
    active_multiplier: float = 1.0


class ScenarioApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["base", "actual", "horizonte"]


class ScenarioApplied(BaseModel):
    version: int
    multiplier: float
