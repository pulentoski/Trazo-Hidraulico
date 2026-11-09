"""Parámetros de diseño editables por proyecto (criterios, dotación, pérdidas, coeficientes y curvas)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DesignParam(BaseModel):
    key: str
    label: str
    group: Literal["criterio", "demanda", "curva"]
    value: float | list[float]
    unit: str
    bound: Literal["min", "max"] | None = Field(None, description="Criterios: el valor es un mínimo o un máximo")
    source: str
    verified: bool = False


class DesignParamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: float | list[float]
    verified: bool = False
    source: str | None = Field(None, max_length=300, description="Fuente del valor; por defecto «Ingresado en el proyecto»")


class DesignParamsOut(BaseModel):
    project_id: str
    profile_name: str | None
    customized: bool = Field(description="True si el proyecto modificó algún valor por defecto")
    params: list[DesignParam]
