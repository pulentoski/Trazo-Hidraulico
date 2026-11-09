"""Modelos ORM. Importar este paquete registra todas las tablas en Base.metadata."""
from app.models.catalog import CatalogPipe, DesignProfile
from app.models.network import NetworkClient, NetworkLink, NetworkNode, NetworkShutoff
from app.models.project import Project, ProjectVersion
from app.models.simulation import ResultLink, ResultNode, SimulationRun

__all__ = [
    "CatalogPipe", "DesignProfile", "NetworkClient", "NetworkLink", "NetworkNode", "NetworkShutoff",
    "Project", "ProjectVersion", "ResultLink", "ResultNode", "SimulationRun",
]
