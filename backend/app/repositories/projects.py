import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import NetworkLink, NetworkNode, Project, ProjectVersion, SimulationRun


def list_projects(session: Session, org_ids: list[uuid.UUID] | None = None) -> list[tuple[Project, int | None, int]]:
    stmt = (
        select(Project, func.max(ProjectVersion.number), func.count(ProjectVersion.id))
        .outerjoin(ProjectVersion, ProjectVersion.project_id == Project.id)
        .where(Project.org_id.in_(org_ids or []) if org_ids is not None else True)
        .group_by(Project.id)
        .order_by(Project.updated_at.desc())
    )
    return [(p, latest, count) for p, latest, count in session.execute(stmt)]


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
