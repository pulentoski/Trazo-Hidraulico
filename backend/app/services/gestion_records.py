"""Registros de operación de la página «Gestión»: energía, cloro, cortes, reclamos, mantenciones y lecturas de
clientes. Una especificación por registro define sus campos; con ella se validan los formularios, se arma la
plantilla Excel, se importa con vista previa (errores por fila) y se exporta a Excel o CSV."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (ChlorineRecord, ClientReading, Complaint, EnergyRecord, MaintenanceLog, MaintenanceTask, Project,
                        ServiceOutage)
from app.schemas.gestion import Column, FieldSpec, RecordImportPreview, PreviewRow, RecordSpec
from app.services import gestion_calc as calc
from app.sig.spec import norm

MAX_ROWS = 20000


@dataclass
class F:
    key: str
    label: str
    type: str  # date | datetime | month | float | int | str | choice | element
    required: bool = True
    choices: tuple[str, ...] = ()
    help: str = ""
    min: float | None = 0.0
    max_len: int = 200
    element_types: tuple[str, ...] = ()


@dataclass
class Spec:
    kind: str
    title: str
    model: type
    fields: list[F]
    order: str
    date_field: str
    help: str
    sheet: str
    computed: list[Column] = field(default_factory=list)
    unique: tuple[str, ...] = ()


MAINT_KINDS = ("ejercitar valvulas", "probar grifos", "lavar estanque", "revisar bomba", "cloracion", "reparacion", "otra")
SPECS: dict[str, Spec] = {
    "energia": Spec("energia", "Energía", EnergyRecord, [
        F("record_date", "Fecha", "date", help="Día del registro (o fin del período leído) AAAA-MM-DD"),
        F("equipment", "Equipo", "element", help="ID de la bomba (o del pozo)", element_types=("link", "well"), max_len=31),
        F("kwh", "Energía", "float", help="kWh consumidos"),
        F("hours", "Horas de funcionamiento", "float", required=False, help="Horas de bomba encendida en el período"),
        F("volume_m3", "Volumen bombeado", "float", required=False, help="m³ (vacío = medidor del pozo)"),
        F("note", "Observación", "str", required=False, max_len=300)],
        order="record_date", date_field="record_date", sheet="Energía",
        help="Lecturas del medidor eléctrico de la bomba (diarias o mensuales) con las horas de funcionamiento."),
    "cloro": Spec("cloro", "Cloro residual", ChlorineRecord, [
        F("measured_at", "Fecha y hora", "datetime", help="AAAA-MM-DD HH:MM"),
        F("point", "Punto", "str", help="ID del elemento o descripción del punto de muestreo", max_len=60),
        F("mg_l", "Cloro libre", "float", help="Cloro residual libre (mg/L)"),
        F("note", "Observación", "str", required=False, max_len=300)],
        order="measured_at", date_field="measured_at", sheet="Cloro",
        help="Mediciones de cloro residual libre en terreno (comparador o fotómetro)."),
    "cortes": Spec("cortes", "Cortes de servicio", ServiceOutage, [
        F("kind", "Tipo", "choice", choices=("programado", "emergencia")),
        F("started_at", "Inicio", "datetime", help="AAAA-MM-DD HH:MM"),
        F("ended_at", "Fin", "datetime", required=False, help="Vacío = el corte sigue activo"),
        F("sector", "Cuartel", "str", required=False, help="Código del cuartel (C-01…) o vacío si indica un tramo", max_len=31),
        F("link_id", "Tramo", "element", required=False, help="ID del tramo (se usa su cuartel)", element_types=("link",), max_len=31),
        F("clients_affected", "Clientes afectados", "int", required=False,
          help="Vacío = se calculan con los cuarteles de corta"),
        F("note", "Motivo", "str", required=False, max_len=300)],
        order="started_at", date_field="started_at", sheet="Cortes",
        help="Cortes programados o de emergencia; los clientes afectados se calculan con los cuarteles de corta.",
        computed=[Column(key="duration_h", label="Duración", unit="h", num=True),
                  Column(key="client_hours", label="Horas-cliente", unit="h", num=True)]),
    "reclamos": Spec("reclamos", "Reclamos", Complaint, [
        F("received_at", "Fecha", "datetime", help="Fecha y hora de recepción"),
        F("client", "Cliente", "element", required=False, help="ID o N° de cliente", element_types=("client",), max_len=40),
        F("kind", "Tipo", "choice", choices=("presion", "calidad", "corte", "fuga", "facturacion", "medidor", "otro")),
        F("status", "Estado", "choice", choices=("abierto", "en proceso", "cerrado")),
        F("responded_at", "Respuesta", "datetime", required=False, help="Fecha y hora de la respuesta"),
        F("note", "Detalle", "str", required=False, max_len=300)],
        order="received_at", date_field="received_at", sheet="Reclamos",
        help="Reclamos de clientes; el tiempo de respuesta se calcula entre la recepción y la respuesta.",
        computed=[Column(key="response_h", label="Tiempo de respuesta", unit="h", num=True)]),
    "mantenciones": Spec("mantenciones", "Mantenciones y tareas", MaintenanceTask, [
        F("kind", "Tipo", "choice", choices=MAINT_KINDS),
        F("element", "Elemento", "element", required=False, help="ID del elemento (válvula, grifo, estanque, bomba…)",
          element_types=("node", "link", "shutoff", "hydrant", "well"), max_len=31),
        F("description", "Descripción", "str", required=False),
        F("frequency_days", "Frecuencia", "int", required=False, help="Días entre mantenciones (vacío = tarea única)", min=1),
        F("next_date", "Próxima fecha", "date", help="AAAA-MM-DD"),
        F("assignee", "Responsable", "str", required=False, max_len=120),
        F("done_on", "Hecha el", "date", required=False, help="Solo tareas únicas: fecha de cumplimiento"),
        F("last_done", "Última vez", "date", required=False, help="Última vez que se hizo (queda en el registro de cumplimiento)")],
        order="next_date", date_field="next_date", sheet="Mantenciones",
        help="Mantenciones periódicas (ejercitar válvulas, probar grifos, lavar estanque…) y tareas únicas "
             "(reparaciones). Al cumplir una periódica, su próxima fecha avanza según la frecuencia.",
        computed=[Column(key="status", label="Estado"), Column(key="overdue_days", label="Días de atraso", num=True)]),
    "lecturas": Spec("lecturas", "Lecturas de clientes", ClientReading, [
        F("client", "N° cliente", "element", help="ID o N° de cliente", element_types=("client",), max_len=40),
        F("period", "Período", "month", help="Mes facturado AAAA-MM"),
        F("m3", "Consumo", "float", help="m³ del mes")],
        order="period", date_field="period", sheet="Lecturas", unique=("client", "period"),
        help="Consumo mensual facturado por cliente (una fila por cliente y mes; un mes repetido se actualiza)."),
}


# ── Contexto del modelo (IDs conocidos) ──

@dataclass
class Ctx:
    nodes: set[str] = field(default_factory=set)
    links: set[str] = field(default_factory=set)
    shutoffs: set[str] = field(default_factory=set)
    hydrants: set[str] = field(default_factory=set)
    wells: set[str] = field(default_factory=set)
    clients: dict[str, str] = field(default_factory=dict)  # ID o N° cliente (normalizado) → ID
    sectors: dict[str, list[str]] = field(default_factory=dict)  # cuartel → clientes (incluye aguas abajo)
    link_sector: dict[str, list[str]] = field(default_factory=dict)
    who: str | None = None

    def ids(self, types: tuple[str, ...]) -> set[str]:
        pools = {"node": self.nodes, "link": self.links, "shutoff": self.shutoffs, "hydrant": self.hydrants,
                 "well": self.wells, "client": set(self.clients.values())}
        return set().union(*(pools[t] for t in types)) if types else set()

    def affected(self, sector: str | None, link: str | None) -> int:
        secs = [sector] if sector else self.link_sector.get(link or "", [])
        clients: set[str] = set()
        for s in secs:
            clients.update(self.sectors.get(s, []))
        return len(clients)


def context(session: Session, project: Project, who: str | None = None) -> Ctx:
    from app.services.network import get_version_or_404, load_model
    from app.sig.sectors import compute_sectors, sectors_of_link
    from app.services.errors import NotFound

    ctx = Ctx(who=who)
    try:
        model = load_model(session, get_version_or_404(session, project, None))
    except NotFound:
        return ctx
    net = model.network
    ctx.nodes = {n.id for n in net.nodes()}
    ctx.links = {lk.id for lk in net.links()}
    ctx.shutoffs = {s.id for s in net.shutoffs()}
    ctx.hydrants = {h.id for h in net.hydrants()}
    ctx.wells = {w.id for w in net.wells()}
    for c in net.clients():
        ctx.clients[norm(c.id)] = c.id
        if c.properties.client_number:
            ctx.clients.setdefault(norm(c.properties.client_number), c.id)
    try:
        res = compute_sectors(model)
        ctx.sectors = {s.id: sorted(set(s.clients) | set(s.downstream_clients)) for s in res.sectors}
        ctx.link_sector = dict(sectors_of_link(res))
    except Exception:  # noqa: BLE001 — sin cuarteles (red sin válvulas): los clientes afectados se ingresan a mano
        pass
    return ctx


# ── Conversión de valores ──

DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d")
DT_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M",
              "%d/%m/%Y %H:%M")


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def to_date(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", str(v).strip()) else str(v).strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError("fecha no válida (use AAAA-MM-DD)")


def to_datetime(v: Any) -> datetime:
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime(v.year, v.month, v.day)
    else:
        s = str(v).strip().replace("Z", "+00:00")
        dt = None
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for f in DT_FORMATS + DATE_FORMATS:
                try:
                    dt = datetime.strptime(s, f)
                    break
                except ValueError:
                    pass
        if dt is None:
            raise ValueError("fecha y hora no válida (use AAAA-MM-DD HH:MM)")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_month(v: Any) -> str:
    if isinstance(v, (date, datetime)):
        return calc.month_key(v)
    s = str(v).strip()
    m = re.match(r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$", s) or None
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
    else:
        m = re.match(r"^(\d{1,2})[-/](\d{4})$", s)
        if not m:
            raise ValueError("período no válido (use AAAA-MM)")
        y, mo = int(m.group(2)), int(m.group(1))
    if not 1 <= mo <= 12 or not 1900 <= y <= 2200:
        raise ValueError("período no válido (use AAAA-MM)")
    return f"{y:04d}-{mo:02d}"


def to_float(v: Any) -> float:
    if isinstance(v, bool):
        raise ValueError("número no válido")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)


def convert(f: F, v: Any, ctx: Ctx) -> Any:
    if _blank(v):
        if f.required:
            raise ValueError("obligatorio")
        return None
    if f.type == "date":
        return to_date(v)
    if f.type == "datetime":
        return to_datetime(v)
    if f.type == "month":
        return to_month(v)
    if f.type in ("float", "int"):
        try:
            x = to_float(v)
        except ValueError as exc:
            raise ValueError("número no válido") from exc
        if f.min is not None and x < f.min:
            raise ValueError(f"debe ser ≥ {f.min:g}")
        if f.type == "int":
            if abs(x - round(x)) > 1e-9:
                raise ValueError("debe ser un número entero")
            return int(round(x))
        return x
    s = str(v).strip()
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    if f.type == "choice":
        k = norm(s)
        hit = next((c for c in f.choices if norm(c) == k), None)
        if hit is None:
            raise ValueError(f"valor no válido (use: {', '.join(f.choices)})")
        return hit
    if len(s) > f.max_len:
        raise ValueError(f"máximo {f.max_len} caracteres")
    if f.type == "element":
        if "client" in f.element_types:
            cid = ctx.clients.get(norm(s))
            if cid is None:
                raise ValueError(f"cliente «{s}» inexistente en el modelo")
            return cid
        known = ctx.ids(f.element_types)
        if known and s not in known:
            raise ValueError(f"«{s}» no existe en el modelo")
    return s


def validate(spec: Spec, raw: dict[str, Any], ctx: Ctx) -> tuple[dict[str, Any], list[str]]:
    """Valores convertidos y errores (texto «Campo: problema») de una fila."""
    vals: dict[str, Any] = {}
    errors: list[str] = []
    for f in spec.fields:
        try:
            vals[f.key] = convert(f, raw.get(f.key), ctx)
        except ValueError as exc:
            errors.append(f"{f.label}: {exc}")
    if errors:
        return vals, errors
    k = spec.kind
    if k == "cortes":
        if vals["sector"] and ctx.sectors and vals["sector"] not in ctx.sectors:
            errors.append(f"Cuartel: «{vals['sector']}» no existe (use C-01, C-02…)")
        if not vals["sector"] and not vals["link_id"] and vals["clients_affected"] is None:
            errors.append("Cuartel: indique el cuartel, el tramo o los clientes afectados")
        if vals["ended_at"] and vals["ended_at"] < vals["started_at"]:
            errors.append("Fin: es anterior al inicio")
        if vals["clients_affected"] is None:
            vals["clients_affected"] = ctx.affected(vals["sector"], vals["link_id"])
    elif k == "reclamos":
        if vals["responded_at"] and vals["responded_at"] < vals["received_at"]:
            errors.append("Respuesta: es anterior a la recepción")
    elif k == "mantenciones":
        if vals["frequency_days"] is not None and vals["done_on"] is not None:
            errors.append("Hecha el: solo para tareas únicas (las periódicas se cumplen con «Cumplir»)")
    elif k == "cloro":
        if vals["mg_l"] > 20:
            errors.append("Cloro libre: valor fuera de escala (mg/L)")
    return vals, errors


# ── Salida ──

def _json(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    return v


def row_out(spec: Spec, r: Any, today: date | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"id": r.id}
    for f in spec.fields:
        out[f.key] = _json(getattr(r, f.key))
    if spec.kind == "cortes":
        end = r.ended_at or datetime.now(timezone.utc)
        h = max(0.0, (end - r.started_at).total_seconds() / 3600)
        out["duration_h"] = round(h, 2)
        out["client_hours"] = round(h * (r.clients_affected or 0), 2)
    elif spec.kind == "reclamos":
        out["response_h"] = round((r.responded_at - r.received_at).total_seconds() / 3600, 1) if r.responded_at else None
    elif spec.kind == "mantenciones":
        t = today or date.today()
        st = calc.maintenance_status(r.next_date, r.done_on, r.frequency_days, t)
        out["status"] = st
        out["overdue_days"] = (t - r.next_date).days if st == "atrasada" else 0
    return out


def _ftype(spec: Spec, key: str) -> str:
    return next(f.type for f in spec.fields if f.key == key)


def _day(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def list_rows(session: Session, project: Project, kind: str, start: date | None = None, end: date | None = None) -> list:
    """Filas del registro, de la más reciente a la más antigua; con fechas, solo las del rango [start, end]."""
    spec = SPECS[kind]
    col = getattr(spec.model, spec.date_field)
    t = _ftype(spec, spec.date_field)
    q = select(spec.model).where(spec.model.project_id == project.id)
    if start is not None:
        q = q.where(col >= (calc.month_key(start) if t == "month" else _day(start) if t == "datetime" else start))
    if end is not None:
        if t == "month":
            q = q.where(col <= calc.month_key(end))
        elif t == "datetime":
            q = q.where(col < _day(end) + timedelta(days=1))
        else:
            q = q.where(col <= end)
    return list(session.scalars(q.order_by(col.desc(), spec.model.id.desc())))


def create(session: Session, project: Project, kind: str, items: list[dict[str, Any]], who: str | None) -> tuple[int, int, list]:
    """Crea filas ya validadas; en registros con clave única (lecturas) actualiza la existente. → (creadas, actualizadas, filas)."""
    spec = SPECS[kind]
    created = updated = 0
    rows = []
    existing = {}
    if spec.unique:
        for r in session.scalars(select(spec.model).where(spec.model.project_id == project.id)):
            existing[tuple(getattr(r, k) for k in spec.unique)] = r
    for vals in items:
        key = tuple(vals[k] for k in spec.unique) if spec.unique else None
        if key is not None and key in existing:
            r = existing[key]
            for k, v in vals.items():
                setattr(r, k, v)
            updated += 1
        else:
            r = spec.model(project_id=project.id, created_by=who, **vals)
            session.add(r)
            if kind == "mantenciones" and (vals.get("done_on") or vals.get("last_done")):
                done = vals.get("done_on") or vals["last_done"]
                r.last_done = max(done, vals.get("last_done") or done)
                session.flush()
                session.add(MaintenanceLog(task_id=r.id, project_id=project.id, done_on=done, by=vals.get("assignee"),
                                           scheduled_for=None, note="Registrado al cargar la mantención"))
            if key is not None:
                existing[key] = r
            created += 1
        rows.append(r)
    session.flush()
    return created, updated, rows


def update(session: Session, project: Project, kind: str, rid: int, vals: dict[str, Any]):
    spec = SPECS[kind]
    r = session.get(spec.model, rid)
    if r is None or r.project_id != project.id:
        return None
    for k, v in vals.items():
        setattr(r, k, v)
    if kind == "mantenciones" and vals.get("done_on"):
        r.last_done = vals["done_on"]
    session.flush()
    return r


def remove(session: Session, project: Project, kind: str, ids: list[int]) -> int:
    spec = SPECS[kind]
    res = session.execute(delete(spec.model).where(spec.model.project_id == project.id, spec.model.id.in_(ids)))
    return res.rowcount or 0


def complete(session: Session, project: Project, rid: int, done_on: date, by: str | None, note: str | None):
    """Cumplir una mantención: registra el cumplimiento; la periódica avanza su próxima fecha, la única queda hecha."""
    r = session.get(MaintenanceTask, rid)
    if r is None or r.project_id != project.id:
        return None
    session.add(MaintenanceLog(task_id=r.id, project_id=project.id, done_on=done_on, scheduled_for=r.next_date, by=by,
                               note=note))
    r.last_done = done_on
    if r.frequency_days:
        r.next_date = calc.advance(r.next_date, r.frequency_days, done_on)
    else:
        r.done_on = done_on
    session.flush()
    return r


def logs(session: Session, project: Project, task_id: int | None = None) -> list[MaintenanceLog]:
    q = select(MaintenanceLog).where(MaintenanceLog.project_id == project.id)
    if task_id is not None:
        q = q.where(MaintenanceLog.task_id == task_id)
    return list(session.scalars(q.order_by(MaintenanceLog.done_on.desc(), MaintenanceLog.id.desc())))


# ── Planillas ──

def spec_out(spec: Spec) -> RecordSpec:
    return RecordSpec(kind=spec.kind, title=spec.title, help=spec.help, computed=spec.computed,
                      fields=[FieldSpec(key=f.key, label=f.label, type=f.type, required=f.required,
                                        choices=list(f.choices), help=f.help, element_types=list(f.element_types))
                              for f in spec.fields])


def _help_row(spec: Spec) -> list[str]:
    out = []
    for f in spec.fields:
        h = f.help or {"date": "AAAA-MM-DD", "datetime": "AAAA-MM-DD HH:MM", "month": "AAAA-MM"}.get(f.type, "")
        if f.choices:
            h = (h + " — " if h else "") + " / ".join(f.choices)
        out.append(f"{h}{'' if f.required else ' (opcional)'}" or "(opcional)")
    return out


def write_sheet(ws, spec: Spec, rows: list[dict[str, Any]] | None = None, with_help: bool = True) -> None:
    from openpyxl.styles import Font

    cols = [f.label for f in spec.fields] + ([c.label for c in spec.computed] if rows is not None else [])
    ws.append(cols)
    if with_help:
        ws.append(_help_row(spec) + ([""] * len(spec.computed) if rows is not None else []))
    for r in rows or []:
        ws.append([r.get(f.key) for f in spec.fields] + [r.get(c.key) for c in spec.computed])
    for c in range(1, len(cols) + 1):
        ws.cell(1, c).font = Font(bold=True)
        if with_help:
            ws.cell(2, c).font = Font(italic=True, color="666666")
        ws.column_dimensions[ws.cell(1, c).column_letter].width = max(14, min(40, len(str(cols[c - 1])) + 6))


def template(kind: str) -> bytes:
    from openpyxl import Workbook

    spec = SPECS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = spec.sheet
    write_sheet(ws, spec)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_xlsx(kind: str, rows: list[dict[str, Any]]) -> bytes:
    from openpyxl import Workbook

    spec = SPECS[kind]
    wb = Workbook()
    ws = wb.active
    ws.title = spec.sheet
    write_sheet(ws, spec, rows, with_help=False)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(kind: str, rows: list[dict[str, Any]]) -> bytes:
    spec = SPECS[kind]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([f.label for f in spec.fields] + [c.label for c in spec.computed])
    for r in rows:
        w.writerow([_csv(r.get(f.key)) for f in spec.fields] + [_csv(r.get(c.key)) for c in spec.computed])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _csv(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def read_table(filename: str, content: bytes, sheet: str | None = None) -> list[list[Any]]:
    if filename.lower().endswith(".xlsx") or content[:2] == b"PK":
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("El archivo no es una planilla .xlsx válida.") from exc
        names = {norm(n): n for n in wb.sheetnames}
        ws = wb[names[norm(sheet)]] if sheet and norm(sheet) in names else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return table
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    delim = ";" if text[:2000].count(";") >= text[:2000].count(",") else ","
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]


def parse(spec: Spec, table: list[list[Any]], ctx: Ctx) -> list[tuple[int, dict[str, Any], list[str]]]:
    """Filas de una planilla → (n° de fila en la planilla, valores, errores). Encabezados por etiqueta o clave."""
    table = [r for r in table if r is not None]
    if not table:
        raise ValueError("El archivo está vacío.")
    header = [norm(h) if h is not None else "" for h in table[0]]
    idx: dict[str, int] = {}
    for f in spec.fields:
        for cand in (f.label, f.key):
            if norm(cand) in header:
                idx[f.key] = header.index(norm(cand))
                break
    missing = [f.label for f in spec.fields if f.required and f.key not in idx]
    if missing:
        raise ValueError(f"Faltan columnas: {', '.join(missing)}. Descargue la plantilla de «{spec.title}».")
    start = 1
    help_row = [norm(h) for h in _help_row(spec)]
    if len(table) > 1 and table[1] and any(isinstance(c, str) and norm(c) in help_row and norm(c) for c in table[1]):
        start = 2  # fila de ayuda de la plantilla
    out = []
    for n, raw in enumerate(table[start:], start=start + 1):
        if all(_blank(c) for c in raw):
            continue
        vals = {k: (raw[i] if i < len(raw) else None) for k, i in idx.items()}
        conv, errors = validate(spec, vals, ctx)
        out.append((n, conv, errors))
        if len(out) > MAX_ROWS:
            raise ValueError(f"La planilla supera {MAX_ROWS} filas.")
    return out


def preview(spec: Spec, parsed: list[tuple[int, dict[str, Any], list[str]]]) -> RecordImportPreview:
    rows = [PreviewRow(row=n, values={k: _json(v) for k, v in vals.items()}, errors=err) for n, vals, err in parsed]
    bad = sum(1 for r in rows if r.errors)
    return RecordImportPreview(kind=spec.kind, rows=rows, valid=len(rows) - bad, invalid=bad)

