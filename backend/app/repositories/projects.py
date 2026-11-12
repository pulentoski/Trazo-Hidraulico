import json
import math
import uuid
from datetime import date

from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import Session

from app.models import (MaintenanceTask, NetworkClient, NetworkLink, NetworkNode, Project, ProjectVersion,
                        SimulationRun)

# Miniatura del listado: a lo más tantas tuberías (las más largas) sobre una grilla de 1000 × 1000.
OUTLINE_MAX_LINKS = 1500
OUTLINE_SIZE = 1000


def list_projects(session: Session, org_ids: list[uuid.UUID] | None = None) -> list[tuple[Project, int | None, int]]:
    stmt = (
        select(Project, func.max(ProjectVersion.number), func.count(ProjectVersion.id))
        .outerjoin(ProjectVersion, ProjectVersion.project_id == Project.id)
        .where(Project.org_id.in_(org_ids or []) if org_ids is not None else True)
        .group_by(Project.id)
        .order_by(Project.updated_at.desc())
    )
    return [(p, latest, count) for p, latest, count in session.execute(stmt)]


def latest_stats(session: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, float]]:
    """(clientes, km de tuberías) de la última versión de cada proyecto, en dos consultas."""
    if not project_ids:
        return {}
    latest = (select(ProjectVersion.project_id, func.max(ProjectVersion.number).label("n"))
              .where(ProjectVersion.project_id.in_(project_ids)).group_by(ProjectVersion.project_id).subquery())
    versions = dict(session.execute(
        select(ProjectVersion.id, ProjectVersion.project_id)
        .join(latest, (latest.c.project_id == ProjectVersion.project_id) & (latest.c.n == ProjectVersion.number))).all())
    if not versions:
        return {}
    clients = dict(session.execute(select(NetworkClient.version_id, func.count(NetworkClient.id))
                                   .where(NetworkClient.version_id.in_(versions)).group_by(NetworkClient.version_id)).all())
    km = dict(session.execute(select(NetworkLink.version_id, func.sum(NetworkLink.length_hydraulic_m))
                              .where(NetworkLink.version_id.in_(versions), NetworkLink.kind == "pipe")
                              .group_by(NetworkLink.version_id)).all())
    return {pid: (int(clients.get(vid, 0)), round(float(km.get(vid) or 0) / 1000, 3)) for vid, pid in versions.items()}


def latest_outlines(session: Session, project_ids: list[uuid.UUID]
                    ) -> dict[uuid.UUID, tuple[list[float], list[list[int]]]]:
    """Centro [lon, lat] y trazado simplificado (miniatura) de las tuberías de la última versión de cada proyecto.

    Las coordenadas se proyectan en planta (lon × cos(lat)) y se escalan a 0–1000 conservando la proporción; los
    puntos consecutivos que caen en la misma celda de la grilla se funden, así la respuesta es breve aun en redes grandes."""
    if not project_ids:
        return {}
    latest = (select(ProjectVersion.project_id, func.max(ProjectVersion.number).label("n"))
              .where(ProjectVersion.project_id.in_(project_ids)).group_by(ProjectVersion.project_id).subquery())
    versions = dict(session.execute(
        select(ProjectVersion.id, ProjectVersion.project_id)
        .join(latest, (latest.c.project_id == ProjectVersion.project_id) & (latest.c.n == ProjectVersion.number))).all())
    if not versions:
        return {}
    ranked = (select(NetworkLink.version_id, func.ST_AsGeoJSON(NetworkLink.geom, 6).label("g"),
                     func.row_number().over(partition_by=NetworkLink.version_id,
                                            order_by=func.ST_Length(NetworkLink.geom).desc()).label("rk"))
              .where(NetworkLink.version_id.in_(versions)).subquery())
    lines: dict[uuid.UUID, list[list[list[float]]]] = {}
    for vid, g, _ in session.execute(select(ranked).where(ranked.c.rk <= OUTLINE_MAX_LINKS)):
        lines.setdefault(vid, []).append(json.loads(g)["coordinates"])
    out: dict[uuid.UUID, tuple[list[float], list[list[int]]]] = {}
    for vid, ls in lines.items():
        pts = [p for line in ls for p in line]
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        k = math.cos(math.radians(cy))
        span = max((x1 - x0) * k, y1 - y0) or 1e-9
        scale = (OUTLINE_SIZE - 40) / span
        ox = OUTLINE_SIZE / 2 - (x1 - x0) * k * scale / 2
        oy = OUTLINE_SIZE / 2 - (y1 - y0) * scale / 2
        polys = []
        for line in ls:
            flat: list[int] = []
            for lon, lat in line:
                x, y = round(ox + (lon - x0) * k * scale), round(oy + (y1 - lat) * scale)
                if not flat or (abs(flat[-2] - x) > 1 or abs(flat[-1] - y) > 1):
                    flat += [x, y]
            if len(flat) >= 4:
                polys.append(flat)
        out[versions[vid]] = ([round(cx, 6), round(cy, 6)], polys)
    return out


def overdue_tasks(session: Session, project_ids: list[uuid.UUID], today: date | None = None) -> dict[uuid.UUID, int]:
    """Mantenciones atrasadas por proyecto (próxima fecha vencida; una tarea única cumplida no cuenta)."""
    if not project_ids:
        return {}
    t = today or date.today()
    done_once = and_(MaintenanceTask.frequency_days.is_(None), MaintenanceTask.done_on.is_not(None))
    rows = session.execute(select(MaintenanceTask.project_id, func.count(MaintenanceTask.id))
                           .where(MaintenanceTask.project_id.in_(project_ids), MaintenanceTask.next_date < t,
                                  not_(done_once))
                           .group_by(MaintenanceTask.project_id)).all()
    return {pid: int(n) for pid, n in rows}


def get_project(session: Session, project_id: uuid.UUID) -> Project | None:
    return session.get(Project, project_id)


def version_stats(session: Session, project_id: uuid.UUID) -> tuple[int | None, int]:
    row = session.execute(
        select(func.max(ProjectVersion.number), func.count(ProjectVersion.id)).where(ProjectVersion.project_id == project_id)
    ).one()
    return row[0], row[1]


def get_version(session: Session, project_id: uuid.UUID, number: int | None) -> ProjectVersion | None:
    stmt = select(ProjectVersion).where(ProjectVersion.project_id == project_id)
    if number is None:
        stmt = stmt.order_by(ProjectVersion.number.desc()).limit(1)
    else:
        stmt = stmt.where(ProjectVersion.number == number)
    return session.scalars(stmt).first()


def list_versions(session: Session, project_id: uuid.UUID) -> list[tuple[ProjectVersion, int, int, bool]]:
    nodes = select(func.count(NetworkNode.id)).where(NetworkNode.version_id == ProjectVersion.id).scalar_subquery()
    links = select(func.count(NetworkLink.id)).where(NetworkLink.version_id == ProjectVersion.id).scalar_subquery()
    runs = select(func.count(SimulationRun.id)).where(SimulationRun.version_id == ProjectVersion.id).scalar_subquery()
    stmt = (select(ProjectVersion, nodes, links, runs).where(ProjectVersion.project_id == project_id)
            .order_by(ProjectVersion.number.desc()))
    return [(v, n, lk, r > 0) for v, n, lk, r in session.execute(stmt)]
