from datetime import date

from pydantic import BaseModel, ConfigDict


class CatalogPipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    material: str
    standard: str
    dn: int
    pipe_class: str
    od_mm: float
    wall_mm: float
    inner_diameter_mm: float
    hw_c: float
    dw_roughness_mm: float
    manning_n: float
    verified: bool
    source: str


class Criterion(BaseModel):
    key: str
    label: str
    min: float | None = None
    max: float | None = None
    unit: str


class DesignProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source: str
    version: str
    valid_from: date
    valid_to: date | None
    verified: bool
    status: str
    criteria: list[Criterion]
    notes: str
