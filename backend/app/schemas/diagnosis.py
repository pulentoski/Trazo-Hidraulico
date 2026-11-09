"""Diagnóstico automático de resultados."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class Ref(BaseModel):
    type: Literal["node", "link", "client", "well", "hydrant", "shutoff"]
    id: str


class DiagItem(BaseModel):
    section: Literal["general", "presion", "velocidad", "cuello", "estanque", "bomba", "sugerencia"]
    severity: Literal["ok", "warning", "problem"]
    text: str
    refs: list[Ref] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict, description="Datos que respaldan la afirmación")


class Suggestion(BaseModel):
    kind: Literal["upgrade_dn", "pump_schedule", "level_control"]
    text: str
    verified: bool
    verification: str
    refs: list[Ref] = Field(default_factory=list)
    action: dict[str, Any] = Field(default_factory=dict)


class DiagnosisResult(BaseModel):
    project_id: str
    model_version: int
    run_id: str
    status: Literal["cumple", "cumple con observaciones", "no cumple"]
    summary: DiagItem
    items: list[DiagItem]
    suggestions: list[Suggestion]
    criteria: dict[str, float]
