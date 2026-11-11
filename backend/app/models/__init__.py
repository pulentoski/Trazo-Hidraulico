"""Modelos ORM. Importar este paquete registra todas las tablas en Base.metadata."""
from app.models.auth import (AuditLog, Membership, OneTimeToken, Organization, PlatformSetting, UsageCounter, User,
                             UserSession, VersionReview)
from app.models.catalog import CatalogPipe, DesignProfile
from app.models.gestion import (ChlorineRecord, ClientReading, Complaint, EnergyRecord, FeasibilityRecord,
                                MaintenanceLog, MaintenanceTask, ServiceOutage)
from app.models.network import NetworkClient, NetworkHydrant, NetworkLink, NetworkNode, NetworkShutoff, NetworkWell
from app.models.project import Project, ProjectVersion
from app.models.sig import LeakEvent, Measurement, Orthophoto, SavedQuery
from app.models.simulation import ResultLink, ResultNode, SimulationRun

__all__ = [
    "AuditLog", "Membership", "PlatformSetting", "OneTimeToken", "Organization", "UsageCounter", "User", "UserSession", "VersionReview",
    "CatalogPipe", "DesignProfile", "NetworkClient", "NetworkLink", "NetworkNode", "NetworkShutoff",
    "NetworkHydrant", "NetworkWell", "Orthophoto", "SavedQuery", "Measurement", "LeakEvent",
    "Project", "ProjectVersion", "ResultLink", "ResultNode", "SimulationRun",
    "ChlorineRecord", "ClientReading", "Complaint", "EnergyRecord", "FeasibilityRecord", "MaintenanceLog",
    "MaintenanceTask", "ServiceOutage",
]
