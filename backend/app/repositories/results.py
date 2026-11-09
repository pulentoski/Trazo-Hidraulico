"""Persistencia de corridas de simulación y resultados por nudo/tramo y periodo."""
import uuid

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import NetworkLink, NetworkNode, ResultLink, ResultNode, SimulationRun


def latest_run(session: Session, version_id: uuid.UUID, epanet_sha: str | None) -> SimulationRun | None:
    stmt = select(SimulationRun).where(SimulationRun.version_id == version_id).order_by(SimulationRun.created_at.desc())
    for run in session.scalars(stmt):
        if run.engine.get("epanet_sha") == epanet_sha and run.status != "error":
            return run
    return None


def get_run(session: Session, run_id: uuid.UUID) -> SimulationRun | None:
    return session.get(SimulationRun, run_id)


def list_runs(session: Session, version_ids: list[uuid.UUID]) -> list[SimulationRun]:
    stmt = select(SimulationRun).where(SimulationRun.version_id.in_(version_ids)).order_by(SimulationRun.created_at.desc())
    return list(session.scalars(stmt))


def insert_results(session: Session, run_id: uuid.UUID, node_rows: list[dict], link_rows: list[dict]) -> None:
    for i in range(0, len(node_rows), 5000):
        session.execute(insert(ResultNode), [dict(r, run_id=run_id) for r in node_rows[i:i + 5000]])
    for i in range(0, len(link_rows), 5000):
        session.execute(insert(ResultLink), [dict(r, run_id=run_id) for r in link_rows[i:i + 5000]])


def load_results(session: Session, run_id: uuid.UUID):
    nodes = session.execute(
        select(NetworkNode.label, ResultNode.period, ResultNode.t_seconds, ResultNode.pressure, ResultNode.head,
               ResultNode.demand)
        .join(NetworkNode, NetworkNode.id == ResultNode.node_id)
        .where(ResultNode.run_id == run_id).order_by(NetworkNode.id, ResultNode.period)
    ).all()
    links = session.execute(
        select(NetworkLink.label, ResultLink.period, ResultLink.flow, ResultLink.velocity, ResultLink.headloss,
               ResultLink.status)
        .join(NetworkLink, NetworkLink.id == ResultLink.link_id)
        .where(ResultLink.run_id == run_id).order_by(NetworkLink.id, ResultLink.period)
    ).all()
    return nodes, links
