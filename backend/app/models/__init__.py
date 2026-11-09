"""Modelos ORM. Importar este paquete registra todas las tablas en Base.metadata."""
from app.models.catalog import CatalogPipe, DesignProfile
from app.models.network import NetworkClient, NetworkHydrant, NetworkLink, NetworkNode, NetworkShutoff, NetworkWell
from app.models.project import Project, ProjectVersion
from app.models.sig import Orthophoto, SavedQuery
from app.models.simulation import ResultLink, ResultNode, SimulationRun

__all__ = [
    "CatalogPipe", "DesignProfile", "NetworkClient", "NetworkLink", "NetworkNode", "NetworkShutoff",
    "NetworkHydrant", "NetworkWell", "Orthophoto", "SavedQuery",
    "Project", "ProjectVersion", "ResultLink", "ResultNode", "SimulationRun",
]
