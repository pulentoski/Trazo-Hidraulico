"""Registro de funcionamiento: lecturas de medidor → caudal, presiones y niveles medidos, y comparación con el
modelo (mismo instante del día en la simulación) con tolerancias configurables por proyecto."""
from __future__ import annotations

import csv
import io
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Measurement, Project
from app.schemas.measurement import (CompareSeries, ComparePoint, MeasurementIn, MeasurementOut, MonitoringSettings)
from app.schemas.network import NetworkModel
from app.schemas.simulation import SimulationResult

KIND_LABEL = {"meter": "medidor", "pressure": "presión", "level": "nivel"}
TYPE_LABEL = {"node": "nudo", "link": "tramo", "client": "cliente", "well": "pozo"}
MAX_ROWS = 50000


def settings(project: Project) -> MonitoringSettings:
    return MonitoringSettings.model_validate(project.monitoring or {})


def out(m: Measurement) -> MeasurementOut:
    return MeasurementOut(id=m.id, element_type=m.element_type, element_id=m.element_id, kind=m.kind,
                          measured_at=m.measured_at, value=m.value, note=m.note)


def list_for(session: Session, project: Project, element_type: str | None = None, element_id: str | None = None):
    q = select(Measurement).where(Measurement.project_id == project.id)
    if element_type:
        q = q.where(Measurement.element_type == element_type)
    if element_id:
        q = q.where(Measurement.element_id == element_id)
    return list(session.scalars(q.order_by(Measurement.element_type, Measurement.element_id, Measurement.kind,
                                           Measurement.measured_at)))


def add(session: Session, project: Project, items: list[MeasurementIn]) -> list[Measurement]:
    rows = [Measurement(project_id=project.id, **i.model_dump()) for i in items]
    session.add_all(rows)
    session.commit()
    return rows


def remove(session: Session, project: Project, ids: list[int]) -> int:
    r = session.execute(delete(Measurement).where(Measurement.project_id == project.id, Measurement.id.in_(ids)))
    session.commit()
    return r.rowcount or 0


# ── Importación (CSV o Excel) ──

def _norm(s: object) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().strip().lower()


TYPES = {"nudo": "node", "node": "node", "estanque": "node", "tramo": "link", "bomba": "link", "valvula": "link", "link": "link",
         "cliente": "client", "client": "client", "pozo": "well", "well": "well"}
KINDS = {"medidor": "meter", "lectura": "meter", "meter": "meter", "presion": "pressure", "pressure": "pressure",
         "nivel": "level", "level": "level"}
HEADERS = {"elemento": "type", "tipo": "type", "id": "id", "medicion": "kind", "magnitud": "kind",
           "fecha y hora": "at", "fecha": "at", "fecha hora": "at", "valor": "value", "nota": "note",
           "observacion": "note"}


def _parse_dt(v) -> datetime:
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v).strip().replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S",
                    "%d/%m/%Y %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"fecha y hora «{v}» no reconocida (use AAAA-MM-DD HH:MM)")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _num(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    return float(s)


def parse_table(table: list[list]) -> tuple[list[MeasurementIn], list[str]]:
    if not table:
        return [], ["El archivo está vacío."]
    head = [HEADERS.get(_norm(h)) if h is not None else None for h in table[0]]
    missing = [h for h in ("type", "id", "kind", "at", "value") if h not in head]
    if missing:
        return [], ["Faltan columnas: Elemento, ID, Medición, Fecha y hora, Valor."]
    out, errors = [], []
    for n, raw in enumerate(table[1:], start=2):
        if not any(v not in (None, "") for v in raw):
            continue
        row = {k: (raw[i] if i < len(raw) else None) for i, k in enumerate(head) if k}
        try:
            et = TYPES.get(_norm(row["type"] or ""))
            kd = KINDS.get(_norm(row["kind"] or ""))
            if et is None:
                raise ValueError(f"elemento «{row['type']}» (nudo, tramo, cliente o pozo)")
            if kd is None:
                raise ValueError(f"medición «{row['kind']}» (medidor, presión o nivel)")
            ident = str(int(row["id"]) if isinstance(row["id"], float) and row["id"].is_integer() else row["id"]).strip()
            out.append(MeasurementIn(element_type=et, element_id=ident, kind=kd, measured_at=_parse_dt(row["at"]),
                                     value=_num(row["value"]), note=(str(row["note"])[:200] if row.get("note") else None)))
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f"Fila {n}: {exc}")
        if len(out) > MAX_ROWS:
            errors.append("Demasiadas filas.")
            break
    return out, errors


def read_file(filename: str, content: bytes) -> tuple[list[MeasurementIn], list[str]]:
    if filename.lower().endswith(".xlsx") or content[:2] == b"PK":
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            return [], ["El archivo no es una planilla .xlsx válida."]
        ws = wb.worksheets[0] if "Mediciones" not in wb.sheetnames else wb["Mediciones"]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        if len(table) > 1 and table[1] and isinstance(table[1][0], str) and table[1][0].startswith("nudo, tramo"):
            table = [table[0], *table[2:]]  # fila de ayuda de la plantilla
        return parse_table(table)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    delim = ";" if text[:2000].count(";") >= text[:2000].count(",") else ","
    return parse_table([list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)])


def template_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Mediciones"
    ws.append(["Elemento", "ID", "Medición", "Fecha y hora", "Valor", "Nota"])
    ws.append(["nudo, tramo, cliente o pozo", "ID del elemento", "medidor (m³), presión (m) o nivel (m)",
               "AAAA-MM-DD HH:MM", "lectura", "opcional"])
    for c in range(1, 7):
        ws.cell(1, c).font = Font(bold=True)
        ws.cell(2, c).font = Font(italic=True, color="666666")
    ws.append(["pozo", "PZ-1", "medidor", "2026-11-09 08:00", 1373232.8, "lectura inicial"])
    ws.append(["pozo", "PZ-1", "medidor", "2026-11-09 08:15:30", 1373247.21, None])
    ws.append(["nudo", "J-5", "presión", "2026-11-09 08:00", 34.5, "manómetro"])
    ws.append(["estanque", "E-1", "nivel", "2026-11-09 08:00", 2.9, None])
    ws.cell(6, 1).value = "nudo"
    for col, w in zip("ABCDEF", (24, 12, 32, 20, 14, 24)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Comparación ──

def meter_flows(points: list[tuple[datetime, float]]) -> tuple[list[tuple[datetime, float]], float | None]:
    """Lecturas acumuladas (m³) → caudal (L/s) entre lecturas consecutivas (al punto medio) y caudal medio total."""
    pts = sorted(points)
    flows = []
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        dt = (t1 - t0).total_seconds()
        if dt > 0:
            flows.append((t0 + (t1 - t0) / 2, (v1 - v0) * 1000 / dt))
    total = (pts[-1][0] - pts[0][0]).total_seconds() if len(pts) > 1 else 0
    avg = (pts[-1][1] - pts[0][1]) * 1000 / total if total > 0 else None
    return flows, avg


def _model_at(series: list[float], times: list[int], t: datetime) -> float | None:
    if not series:
        return None
    if len(times) <= 1:
        return series[0]
    tod = t.hour * 3600 + t.minute * 60 + t.second
    span = times[-1] or 86400
    tod = tod % span if span < 86400 else tod
    k = max(i for i, x in enumerate(times) if x <= tod) if tod >= times[0] else 0
    return series[k]


def compare(model: NetworkModel, sim: SimulationResult | None, items: list[Measurement],
            cfg: MonitoringSettings) -> list[CompareSeries]:
    nodes = {n.id: n for n in model.network.nodes()}
    links = {lk.id: lk for lk in model.network.links()}
    clients = {c.id: c for c in model.network.clients()}
    wells = {w.id: w for w in model.network.wells()}
    groups: dict[tuple[str, str, str], list[Measurement]] = {}
    for m in items:
        groups.setdefault((m.element_type, m.element_id, m.kind), []).append(m)
    out = []
    times = sim.times if sim else []
    for (et, eid, kind), ms in groups.items():
        series_model: list[float] = []
        adj = 0.0
        quantity, unit, tol_pct = "", "", False
        if kind == "meter":
            quantity, unit, tol_pct = "caudal", "L/s", True
            link = links.get(eid) if et == "link" else None
            if et == "well" and eid in wells and wells[eid].properties.node:
                res = wells[eid].properties.node
                link = next((lk for lk in links.values() if lk.properties.kind == "pump"
                             and res in (lk.properties.from_node, lk.properties.to_node)), None)
            if link is not None and sim and link.id in sim.links:
                series_model = [abs(v) for v in sim.links[link.id].flow]
            flows, avg = meter_flows([(m.measured_at, m.value) for m in ms])
            measured = flows
        elif kind == "pressure":
            quantity, unit = "presión", "m"
            node_id = eid if et == "node" else clients[eid].properties.node if et == "client" and eid in clients else None
            if et == "client" and eid in clients and node_id in nodes:
                ce, ne = clients[eid].properties.elevation, nodes[node_id].properties.elevation
                adj = (ne - ce) if ce is not None and ne is not None else 0.0
            if node_id and sim and node_id in sim.nodes:
                series_model = sim.nodes[node_id].pressure
            measured, avg = [(m.measured_at, m.value) for m in ms], None
        else:
            quantity, unit = "nivel", "m"
            if et == "node" and sim and eid in sim.nodes:
                series_model = sim.nodes[eid].pressure  # estanque: nivel sobre el fondo
            elif et == "well" and eid in wells:
                w = wells[eid].properties
                res = nodes.get(w.node or "")
                if res and sim and res.id in sim.nodes and w.ground_elevation is not None:
                    series_model = [w.ground_elevation - h for h in sim.nodes[res.id].head]  # profundidad del agua
            measured, avg = [(m.measured_at, m.value) for m in ms], None
        tol = cfg.flow_pct if tol_pct else cfg.pressure_m if kind == "pressure" else cfg.level_m
        points = []
        for t, v in measured:
            mv = _model_at(series_model, times, t)
            mv = mv + adj if mv is not None else None
            diff = mv - v if mv is not None else None
            limit = abs(v) * tol / 100 if tol_pct else tol
            points.append(ComparePoint(time=t, measured=round(v, 4), model=None if mv is None else round(mv, 4),
                                       diff=None if diff is None else round(diff, 4),
                                       ok=None if diff is None else abs(diff) <= limit + 1e-9))
        diffs = [abs(p.diff) for p in points if p.diff is not None]
        alert = any(p.ok is False for p in points)
        name = f"{TYPE_LABEL[et]} {eid}"
        if not series_model:
            msg = f"{KIND_LABEL[kind].capitalize()} de {name}: sin valor del modelo para comparar."
        elif alert:
            bad = sum(1 for p in points if p.ok is False)
            msg = (f"{quantity.capitalize()} de {name}: {bad} de {len(points)} mediciones difieren del modelo más que "
                   f"la tolerancia ({tol:g} {'%' if tol_pct else unit}); diferencia máxima {max(diffs):.2f} {unit}.")
        else:
            msg = f"{quantity.capitalize()} de {name}: el modelo coincide con las mediciones dentro de la tolerancia."
        out.append(CompareSeries(element_type=et, element_id=eid, kind=kind, quantity=quantity, unit=unit, points=points,
                                 average_measured=None if avg is None else round(avg, 4),
                                 max_abs_diff=round(max(diffs), 4) if diffs else None, tolerance=tol, alert=alert,
                                 message=msg))
    return out


def as_utc(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


__all__ = ["add", "compare", "list_for", "meter_flows", "out", "read_file", "remove", "settings", "template_xlsx",
           "timedelta"]
