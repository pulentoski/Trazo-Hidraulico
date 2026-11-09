from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.network import HydraulicOptions, NetworkFeatureCollection


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    element_type: Literal["node", "link", "client", "shutoff", "network"] | None = None
    element_id: str | None = None


class ValidationReport(BaseModel):
    ok: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]


class ValidateRequest(BaseModel):
    """Valida una versión guardada (`model_version`) o una red en edición (`network`)."""
    model_config = ConfigDict(extra="forbid")
    model_version: int | None = None
    network: NetworkFeatureCollection | None = None
    options: HydraulicOptions | None = None
    aux: dict[str, str] | None = None
