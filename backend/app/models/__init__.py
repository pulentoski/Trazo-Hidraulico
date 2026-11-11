"""Modelos ORM. Importar este paquete registra todas las tablas en Base.metadata."""
from app.models.auth import (AuditLog, Membership, OneTimeToken, Organization, UsageCounter, User, UserSession,
                             VersionReview)
from app.models.catalog import CatalogPipe, DesignProfile
from app.models.network import NetworkClient, NetworkHydrant, NetworkLink, NetworkNode, NetworkShutoff, NetworkWell
from app.models.project import Project, ProjectVersion
from app.models.sig import LeakEvent, Measurement, Orthophoto, SavedQuery
from app.models.simulation import ResultLink, ResultNode, SimulationRun

__all__ = [
    "AuditLog", "Membership", "OneTimeToken", "Organization", "UsageCounter", "User", "UserSession", "VersionReview",
    "CatalogPipe", "DesignProfile", "NetworkClient", "NetworkLink", "NetworkNode", "NetworkShutoff",
    "NetworkHydrant", "NetworkWell", "Orthophoto", "SavedQuery", "Measurement", "LeakEvent",
    "Project", "ProjectVersion", "ResultLink", "ResultNode", "SimulationRun",
]
