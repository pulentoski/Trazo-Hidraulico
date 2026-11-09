"""Excepciones de dominio que los routers traducen a respuestas HTTP."""
from app.schemas.validation import ValidationReport


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class InvalidNetwork(Exception):
    def __init__(self, report: ValidationReport, detail: str):
        self.report = report
        self.detail = detail
        super().__init__(detail)


class SimulationBlockedError(Exception):
    def __init__(self, model_version: int, report: ValidationReport):
        self.model_version = model_version
        self.report = report
        super().__init__("La red tiene errores bloqueantes; no se ejecutó la simulación.")
