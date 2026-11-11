"""Factibilidad de un nuevo cliente: se simula la red con el cliente agregado temporalmente.

No modifica el proyecto. El cliente se conecta con un nudo nuevo en el punto de la tubería (la tubería se
divide en dos). Criterio: el punto nuevo debe quedar con presión ≥ mínima y ningún consumo existente
(cliente, o nudo con demanda propia) puede pasar a quedar bajo la mínima. Si no es factible, se aumenta
el DN del cuello de botella al siguiente del catálogo (mismo material y clase), hasta 3 veces.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.hydraulic.engine import EngineRun, run_model
from app.hydraulic.version import engine_info
from app.models import CatalogPipe, Project
from app.repositories import catalog as catalog_repo
from app.schemas.analysis import (AffectedClient, Criterion, FeasibilityRequest, FeasibilityResult, LinkIssue,
                                  UpgradeAttempt)
from app.schemas.network import NetworkModel
from app.schemas.simulation import EngineInfo
from app.services import design
from app.services.connection import Projection, project_on_link, split_pipe, unique_id
from app.services.errors import NotFound, SimulationBlockedError
from app.services.geometry import recompute_lengths
from app.services.network import get_version_or_404, load_model

MAX_UPGRADES = 3
EPS = 1e-6


def build_scenario(model: NetworkModel, req: FeasibilityRequest, srid: int) -> tuple[NetworkModel, Projection, str,
                                                                                         tuple[str, str]]:
    """Modelo temporal con el nuevo cliente: nudo nuevo en el punto de conexión con su consumo."""
    lk = next((x for x in model.network.links() if x.id == req.link), None)
    if lk is None or lk.properties.kind != "pipe":
        raise NotFound(f"Tubería «{req.link}» no encontrada")
    scenario = model.model_copy(deep=True)
    pr = project_on_link(lk, req.point[0], req.point[1], srid)
    new_id = unique_id({n.id for n in scenario.network.nodes()}, "NUEVO")
    parts = split_pipe(scenario.network, pr, new_id, req.elevation, base_demand=req.consumption_lps)
    recompute_lengths(scenario.network, srid)
    return scenario, pr, new_id, parts


def _min_series(run: EngineRun, kind: str, var: str) -> dict[str, float]:
    res = run.results
    if res is None:
        return {}
    ids = res.node_ids if kind == "node" else res.link_ids
    arr = (res.nodes if kind == "node" else res.links)[var]
    return {i: float(arr[:, k].min()) for k, i in enumerate(ids)}


def _max_abs(run: EngineRun, var: str) -> dict[str, float]:
    res = run.results
    if res is None:
        return {}
    arr = res.links[var]
    return {i: float(abs(arr[:, k]).max()) for k, i in enumerate(res.link_ids)}


def _consumers(model: NetworkModel) -> list[tuple[str, str | None, str]]:
    """Puntos de consumo existentes: (id, nombre, nudo). Clientes; y nudos con demanda propia sin clientes."""
    out = [(c.id, c.properties.name, c.properties.node) for c in model.network.clients()
           if c.properties.status == "activo" or model.options.include_projected_clients]
    with_clients = {node for _, _, node in out}
    for n in model.network.nodes():
        p = n.properties
        if p.kind == "junction" and n.id not in with_clients and (p.base_demand > 0 or any(d.base > 0 for d in p.demands)):
            out.append((n.id, None, n.id))
    return out


def _evaluate(base_model: NetworkModel, base: EngineRun, scen: NetworkModel, run: EngineRun, new_id: str,
              pmin: float, vmax: float, hmax: float):
    reasons: list[str] = []
    errors = [m for m in run.messages if m.severity == "error"]
    if not run.ok or run.results is None or errors:
        reasons.append("El motor no pudo resolver la red con el nuevo cliente.")
        return False, None, [], [], reasons
    p_before = _min_series(base, "node", "pressure")
    p_after = _min_series(run, "node", "pressure")
    p_new = p_after.get(new_id)
    if p_new is None or p_new < pmin:
        reasons.append(f"Presión en el punto {_es(p_new)} m.c.a. bajo el mínimo de {_es(pmin, 1)} m.c.a.")
    affected = []
    for cid, name, node in _consumers(base_model):
        before, after = p_before.get(node), p_after.get(node)
        if after is not None and after < pmin:
            newly = before is not None and before >= pmin
            affected.append(AffectedClient(id=cid, name=name, node=node, before=_r(before), after=_r(after),
                                           newly_below=newly))
    newly = [a for a in affected if a.newly_below]
    if newly:
        reasons.append(f"{len(newly)} consumo(s) existente(s) quedan bajo la presión mínima: "
                       + ", ".join(a.id for a in newly[:10]) + ("…" if len(newly) > 10 else "") + ".")
    v_before, v_after = _max_abs(base, "velocity"), _max_abs(run, "velocity")
    h_before, h_after = _max_abs(base, "headloss"), _max_abs(run, "headloss")
    issues = []
    for lk in scen.network.links():
        if lk.properties.kind != "pipe":
            continue
        va, ha = v_after.get(lk.id, 0.0), h_after.get(lk.id, 0.0)
        over_v, over_h = va > vmax, ha > hmax
        if over_v or over_h:
            orig = lk.id if lk.id in v_before else lk.id.rsplit("_", 1)[0]
            issues.append(LinkIssue(id=lk.id, dn=lk.properties.dn, velocity_before=_r(v_before.get(orig, 0.0)),
                                    velocity_after=_r(va), headloss_before=_r(h_before.get(orig, 0.0)),
                                    headloss_after=_r(ha), over_velocity=over_v, over_headloss=over_h))
    feasible = not reasons
    return feasible, p_new, affected, issues, reasons


def _bottleneck(base: EngineRun, run: EngineRun, scen: NetworkModel) -> str | None:
    """Tubería con mayor pérdida unitaria entre las que aumentaron su caudal por el nuevo cliente."""
    q_before, q_after = _max_abs(base, "flow"), _max_abs(run, "flow")
    h_after = _max_abs(run, "headloss")
    pipes = [lk for lk in scen.network.links() if lk.properties.kind == "pipe"]
    loaded = [lk for lk in pipes
              if q_after.get(lk.id, 0.0) - q_before.get(lk.id, q_before.get(lk.id.rsplit("_", 1)[0], 0.0)) > EPS]
    pool = loaded or pipes
    return max(pool, key=lambda lk: h_after.get(lk.id, 0.0)).id if pool else None


def _next_dn(catalog: list[CatalogPipe], props) -> CatalogPipe | None:
    if not props.material or not props.pipe_class:
        return None
    larger = [c for c in catalog if c.material == props.material and c.pipe_class == props.pipe_class
              and c.inner_diameter_mm > (props.inner_diameter_mm or 0) + EPS and (props.dn is None or c.dn > props.dn)]
    return min(larger, key=lambda c: c.dn) if larger else None


def _roughness(item: CatalogPipe, formula: str) -> float:
    return {"H-W": item.hw_c, "D-W": item.dw_roughness_mm, "C-M": item.manning_n}[formula]


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)


def _es(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def assess(session: Session, project: Project, req: FeasibilityRequest) -> tuple[FeasibilityResult, NetworkModel]:
    version = get_version_or_404(session, project, req.model_version)
    model = load_model(session, version)
    from app.services.simulation import validation_for

    report = validation_for(session, project, model)
    if not report.ok:
        raise SimulationBlockedError(version.number, report)
    params = design.effective(session, project)
    pmin = float(design.param(params, "pressure_min").value)
    vmax = float(design.param(params, "velocity_max").value)
    hmax = float(design.param(params, "unit_headloss_max").value)

    base = run_model(model)
    scen, pr, new_id, parts = build_scenario(model, req, project.length_srid)
    run = run_model(scen)
    feasible, p_new, affected, issues, reasons = _evaluate(model, base, scen, run, new_id, pmin, vmax, hmax)

    bottleneck = None
    upgrades: list[UpgradeAttempt] = []
    upgrade_feasible = None
    if not feasible and run.results is not None:
        catalog = catalog_repo.list_pipes(session)
        current, cur_run = scen.model_copy(deep=True), run
        for _ in range(MAX_UPGRADES):
            bn = _bottleneck(base, cur_run, current)
            if bn is None:
                break
            bottleneck = bottleneck or bn
            lk = next(x for x in current.network.links() if x.id == bn)
            p = lk.properties
            item = _next_dn(catalog, p)
            if item is None:
                upgrades.append(UpgradeAttempt(link=bn, material=p.material, pipe_class=p.pipe_class, dn_from=p.dn,
                                               dn_to=None, inner_from=p.inner_diameter_mm, inner_to=None,
                                               pressure_new=None, feasible=False,
                                               note="Sin DN mayor en el catálogo para este material y clase."))
                break
            attempt = UpgradeAttempt(link=bn, material=p.material, pipe_class=p.pipe_class, dn_from=p.dn, dn_to=item.dn,
                                     inner_from=p.inner_diameter_mm, inner_to=item.inner_diameter_mm,
                                     pressure_new=None, feasible=False)
            p.dn, p.inner_diameter_mm, p.catalog_pipe_id = item.dn, item.inner_diameter_mm, item.id
            p.roughness, p.inner_diameter_source = _roughness(item, current.options.headloss), "catalogo"
            cur_run = run_model(current)
            ok, p_up, *_ = _evaluate(model, base, current, cur_run, new_id, pmin, vmax, hmax)
            attempt.pressure_new, attempt.feasible = _r(p_up), ok
            upgrades.append(attempt)
            if ok:
                break
        upgrade_feasible = bool(upgrades and upgrades[-1].feasible)

    info = engine_info()
    crit = [Criterion(key=x.key, label=x.label, value=float(x.value), unit=x.unit, source=x.source, verified=x.verified)
            for x in params if x.key in ("pressure_min", "velocity_max", "unit_headloss_max")]
    verdict = "FACTIBLE" if feasible else "NO FACTIBLE"
    result = FeasibilityResult(
        feasible=feasible, verdict=verdict, project_id=str(project.id), project_name=project.name,
        model_version=version.number, created_at=datetime.now(UTC), analysis=model.options.demand_model,
        engine=EngineInfo(**info), inp_sha256=run.inp_sha256, location=pr.point, link=req.link,
        distance_m=round(pr.distance_m, 3), new_node=new_id, split_links=parts, consumption_lps=req.consumption_lps,
        elevation=req.elevation, criteria=crit, pressure_new=_r(p_new),
        margin=_r(p_new - pmin) if p_new is not None else None, affected_clients=affected, link_issues=issues,
        bottleneck=bottleneck, upgrades=upgrades, upgrade_feasible=upgrade_feasible, messages=run.messages,
        reasons=reasons,
    )
    return result, scen


def record(session: Session, project: Project, req: FeasibilityRequest, result: FeasibilityResult) -> None:
    """Historial de factibilidades (página «Gestión» → Planificación): cada evaluación queda registrada."""
    from app.models import FeasibilityRecord
    from app.services import auth

    p = auth.current.get()
    session.add(FeasibilityRecord(project_id=project.id, created_by=p.email if p and not p.system else None,
                                  model_version=result.model_version, link_id=req.link,
                                  location=list(result.location),
                                  consumption_lps=req.consumption_lps, elevation=req.elevation, feasible=result.feasible,
                                  pressure_new=result.pressure_new, bottleneck=result.bottleneck,
                                  name=req.name or None))
    session.commit()
