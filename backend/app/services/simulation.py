"""Simulación de una versión del modelo: validación → motor → persistencia → alertas de criterios."""
import json
import logging
import uuid
import zlib

from sqlalchemy.orm import Session

from app.core.cache import get_redis
from app.core.config import get_settings
from app.hydraulic.engine import EngineRun, run_model
from app.hydraulic.inp_writer import write_inp
from app.hydraulic.messages import EngineMessage
from app.hydraulic.version import engine_info
from app.models import Project, ProjectVersion, SimulationRun
from app.repositories import catalog as catalog_repo
from app.repositories import network as network_repo
from app.repositories import results as results_repo
from app.schemas.network import NetworkModel
from app.schemas.simulation import EngineInfo, LinkSeries, NodeSeries, SimulationResult
from app.schemas.validation import ValidationReport
from app.services.criteria import criteria_alerts, criteria_map
from app.services.errors import SimulationBlockedError
from app.services.network import get_version_or_404, load_model, sha256_of
from app.validators.network_validator import ValidatorSettings, validate_model  # noqa: F401

log = logging.getLogger(__name__)
CACHE_TTL_S = 24 * 3600


def validation_for(session: Session, project: Project, model: NetworkModel) -> ValidationReport:
    profile = catalog_repo.get_profile(session, project.design_profile_id)
    s = get_settings()
    settings = ValidatorSettings(short_pipe_m=s.short_pipe_m, elevation_jump_m=s.elevation_jump_m,
                                 criteria=criteria_map(profile.criteria if profile else None))
    return validate_model(model, catalog_repo.catalog_index(session), settings)


def _r(x: float) -> float:
    return round(float(x), 6)


def _series_from_engine(run: EngineRun):
    res = run.results
    if res is None:
        return [], {}, {}
    nodes = {nid: NodeSeries(pressure=[_r(v) for v in res.nodes["pressure"][:, i]],
                             head=[_r(v) for v in res.nodes["head"][:, i]],
                             demand=[_r(v) for v in res.nodes["demand"][:, i]])
             for i, nid in enumerate(res.node_ids)}
    links = {lid: LinkSeries(flow=[_r(v) for v in res.links["flow"][:, j]],
                             velocity=[_r(v) for v in res.links["velocity"][:, j]],
                             headloss=[_r(v) for v in res.links["headloss"][:, j]],
                             status=[int(v) for v in res.links["status"][:, j]])
             for j, lid in enumerate(res.link_ids)}
    return list(res.times), nodes, links


def _cache_key(epanet_sha: str | None, inp_sha: str) -> str:
    return f"trazo:sim:{(epanet_sha or 'x')[:12]}:{inp_sha}"


def _cache_get(key: str) -> dict | None:
    try:
        raw = get_redis().get(key)
        return json.loads(zlib.decompress(raw)) if raw else None
    except Exception:  # noqa: BLE001  (la caché es opcional)
        log.warning("Caché no disponible", exc_info=True)
        return None


def _cache_set(key: str, payload: dict) -> None:
    try:
        get_redis().set(key, zlib.compress(json.dumps(payload).encode()), ex=CACHE_TTL_S)
    except Exception:  # noqa: BLE001
        log.warning("Caché no disponible", exc_info=True)


def _status(ok: bool, messages: list[EngineMessage]) -> str:
    if not ok or any(m.severity == "error" for m in messages):
        return "error"
    return "warning" if messages else "ok"


def simulate_version(session: Session, project: Project, number: int) -> SimulationResult:
    version = get_version_or_404(session, project, number)
    model = load_model(session, version)
    report = validation_for(session, project, model)
    if not report.ok:
        raise SimulationBlockedError(version.number, report)

    info = engine_info()
    existing = results_repo.latest_run(session, version.id, info["epanet_sha"])
    if existing is not None:
        return result_from_db(session, project, version, existing, model, report, cached=True)

    inp_sha = sha256_of(write_inp(model))
    key = _cache_key(info["epanet_sha"], inp_sha)
    cached = _cache_get(key)
    if cached is not None:
        ok, elapsed = cached["ok"], cached["elapsed_ms"]
        messages = [EngineMessage(**m) for m in cached["messages"]]
        times = cached["times"]
        nodes = {k: NodeSeries(**v) for k, v in cached["nodes"].items()}
        links = {k: LinkSeries(**v) for k, v in cached["links"].items()}
        meta = cached["meta"]
    else:
        run = run_model(model)
        assert run.inp_sha256 == inp_sha
        ok, elapsed, messages = run.ok, run.elapsed_ms, run.messages
        times, nodes, links = _series_from_engine(run)
        res = run.results
        meta = {"report_start": res.report_start if res else 0, "report_step": res.report_step if res else 0,
                "duration": res.duration if res else 0}
        _cache_set(key, {"ok": ok, "elapsed_ms": elapsed, "messages": [m.model_dump() for m in messages],
                         "times": times, "nodes": {k: v.model_dump() for k, v in nodes.items()},
                         "links": {k: v.model_dump() for k, v in links.items()}, "meta": meta})

    status = _status(ok, messages)
    run_row = SimulationRun(id=uuid.uuid4(), version_id=version.id, status=status, engine=info,
                            engine_version=info["wheel_version"], options=model.options.model_dump(mode="json"),
                            inp_sha256=inp_sha, messages=[m.model_dump() for m in messages],
                            report_start=meta["report_start"], report_step=meta["report_step"],
                            duration=meta["duration"], n_periods=len(times), elapsed_ms=elapsed)
    session.add(run_row)
    session.flush()
    if times:
        nid = network_repo.node_ids(session, version.id)
        lid = network_repo.link_ids(session, version.id)
        node_rows = [{"node_id": nid[label], "period": k, "t_seconds": t, "pressure": s.pressure[k],
                      "head": s.head[k], "demand": s.demand[k]}
                     for label, s in nodes.items() for k, t in enumerate(times)]
        link_rows = [{"link_id": lid[label], "period": k, "t_seconds": t, "flow": s.flow[k],
                      "velocity": s.velocity[k], "headloss": s.headloss[k], "status": s.status[k], "setting": 0.0}
                     for label, s in links.items() for k, t in enumerate(times)]
        results_repo.insert_results(session, run_row.id, node_rows, link_rows)
    session.commit()
    session.refresh(run_row)
    return _build(project, version, run_row, model, report, times, nodes, links, messages, cached=False,
                  session=session)


def _build(project, version, run_row: SimulationRun, model, report, times, nodes, links, messages, *, cached,
           session) -> SimulationResult:
    profile = catalog_repo.get_profile(session, project.design_profile_id)
    alerts = criteria_alerts(model, times, nodes, links, criteria_map(profile.criteria if profile else None))
    return SimulationResult(
        run_id=run_row.id, project_id=project.id, model_version=version.number, status=run_row.status,
        cached=cached, created_at=run_row.created_at, elapsed_ms=run_row.elapsed_ms,
        engine=EngineInfo(**run_row.engine), options=model.options, inp_sha256=run_row.inp_sha256,
        times=times, nodes=nodes, links=links, messages=messages, alerts=alerts, validation=report,
        profile_name=profile.name if profile else None, profile_verified=bool(profile and profile.verified),
    )


def result_from_db(session: Session, project: Project, version: ProjectVersion, run_row: SimulationRun,
                   model: NetworkModel | None = None, report: ValidationReport | None = None,
                   cached: bool = True) -> SimulationResult:
    model = model or load_model(session, version)
    report = report or validation_for(session, project, model)
    node_rows, link_rows = results_repo.load_results(session, run_row.id)
    times: list[int] = []
    nodes: dict[str, NodeSeries] = {}
    for label, period, t, p, h, d in node_rows:
        s = nodes.setdefault(label, NodeSeries(pressure=[], head=[], demand=[]))
        s.pressure.append(p)
        s.head.append(h)
        s.demand.append(d)
        if len(nodes) == 1:
            times.append(t)
    links: dict[str, LinkSeries] = {}
    for label, period, q, v, hl, st in link_rows:
        s = links.setdefault(label, LinkSeries(flow=[], velocity=[], headloss=[], status=[]))
        s.flow.append(q)
        s.velocity.append(v)
        s.headloss.append(hl)
        s.status.append(st)
    messages = [EngineMessage(**m) for m in run_row.messages]
    return _build(project, version, run_row, model, report, times, nodes, links, messages, cached=cached,
                  session=session)
