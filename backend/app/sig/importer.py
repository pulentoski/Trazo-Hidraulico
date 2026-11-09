"""Importación desde la planilla: vista previa (cambios agrupados y errores por fila) y modelo resultante.

La aplicación (en `app.services.sig`) guarda el modelo resultante como una versión nueva, en una sola
transacción: si hay errores no se guarda nada.

Reglas:
- Si el ID existe en el proyecto se actualizan solo las columnas presentes en la hoja (una celda vacía en
  una columna presente borra el valor, salvo en columnas obligatorias).
- Sin ID, el sistema genera uno único (prefijo de la hoja + número).
- Columnas no reconocidas = atributos libres.
- Eliminar elementos ausentes es opcional y solo afecta a las hojas presentes en el archivo.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from pydantic import ValidationError

from app.schemas.network import (ClientFeature, ClientProperties, HydrantFeature, HydrantProperties,
                                 HydraulicOptions, LineStringGeometry, LinkFeature, LinkProperties, NetworkModel,
                                 NodeFeature, NodeProperties, PointGeometry, ShutoffFeature, ShutoffProperties,
                                 WellFeature, WellProperties)
from app.schemas.sig import ChangeItem, FieldChange, ImportPreview, RowError, SheetSummary
from app.services.connection import unique_id
from app.services.geometry import from_metric, place_shutoffs, recompute_lengths, to_metric
from app.validators.network_validator import validate_model

from .excel import RawRow, RawSheet
from .spec import NODE_SHEETS, SHEET_BY_KEY, SHEETS, SHUTOFF_TYPES, Col, Sheet, norm
from .tables import RESERVED_PREFIX, Row, model_rows, model_sheet_rows

NS_OF_SHEET = {"nudos": "node", "estanques": "node", "reservorios": "node", "tramos": "link", "bombas": "link",
               "grifos": "hydrant", "pozos": "well", "clientes": "client"}
ETYPE_SHEET = {"hydrant": "grifos", "well": "pozos", "client": "clientes", "shutoff": "valvulas"}
CONTROL_TYPES = {"PRV", "PSV", "PBV", "FCV", "TCV", "GPV", "PCV"}


class CellError(ValueError):
    pass


@dataclass
class CatalogItem:
    id: int
    material: str
    dn: int
    pipe_class: str
    inner_diameter_mm: float
    hw_c: float
    dw_roughness_mm: float
    manning_n: float


@dataclass
class ImportOptions:
    coord_srid: int
    delete_missing: bool = False


@dataclass
class Outcome:
    preview: ImportPreview
    model: NetworkModel | None  # None si hay errores


# ── Conversión de celdas ─────────────────────────────────────────────────

def _num(raw: Any) -> float:
    if isinstance(raw, bool):
        raise CellError("debe ser un número")
    if isinstance(raw, (int, float)):
        v = float(raw)
    else:
        s = str(raw).strip().replace(" ", "")
        if s.count(",") == 1 and "." not in s:
            s = s.replace(",", ".")
        elif s.count(",") >= 1 and s.count(".") >= 1 and s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234,5
        try:
            v = float(s)
        except ValueError as exc:
            raise CellError(f"«{raw}» no es un número") from exc
    if not math.isfinite(v):
        raise CellError("debe ser un número finito")
    return v


def convert(col: Col, raw: Any) -> Any:
    """Valor crudo → valor interno de la columna. None = vacío."""
    if raw is None:
        return None
    k = col.kind
    if k in ("float", "lat", "lon", "east", "north"):
        return _num(raw)
    if k == "int":
        v = _num(raw)
        if not float(v).is_integer():
            raise CellError(f"«{raw}» debe ser un número entero")
        return int(v)
    if k == "bool":
        s = norm(raw)
        if s in ("si", "s", "yes", "true", "1", "x", "verdadero"):
            return True
        if s in ("no", "n", "false", "0", "falso"):
            return False
        raise CellError(f"«{raw}» debe ser sí o no")
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    text = str(raw).strip()
    if k == "choice" and col.choices is not None:
        s = norm(text)
        for internal, label in col.choices.items():
            if s in (norm(internal), norm(label)):
                return internal
        if col.strict:
            raise CellError(f"«{text}» no es válido (valores: {', '.join(col.choices.values())})")
        return text
    return text


def parse_vertices(text: str, tr_utm) -> list[tuple[float, float]]:
    """«lat lon; lat lon» (o «E N; E N» en UTM) → [(lon, lat), ...]."""
    out: list[tuple[float, float]] = []
    for part in str(text).replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        nums = part.replace(",", " ").split()
        if len(nums) != 2:
            raise CellError(f"vértice «{part}»: se esperan dos números («lat lon» o «E N»)")
        a, b = _num(nums[0]), _num(nums[1])
        if abs(a) <= 90 and abs(b) <= 180:
            out.append((b, a))
        else:
            lon, lat = tr_utm.transform(a, b)
            out.append((float(lon), float(lat)))
    return out


# ── Índice espacial simple (vectorizado) para conectar puntos a tuberías ──

class PipeIndex:
    def __init__(self, links: list[LinkFeature], srid: int):
        tr = to_metric(srid)
        self.srid = srid
        self.tr = tr
        segs_a, segs_b, owner, start, total = [], [], [], [], {}
        self.links = {lk.id: lk for lk in links}
        for lk in links:
            if lk.properties.kind != "pipe":
                continue
            xs, ys = tr.transform([c[0] for c in lk.geometry.coordinates], [c[1] for c in lk.geometry.coordinates])
            acc = 0.0
            for i in range(len(xs) - 1):
                segs_a.append((xs[i], ys[i]))
                segs_b.append((xs[i + 1], ys[i + 1]))
                owner.append(lk.id)
                start.append(acc)
                acc += math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i])
            total[lk.id] = acc
        self.a = np.array(segs_a, dtype=float).reshape(-1, 2)
        self.b = np.array(segs_b, dtype=float).reshape(-1, 2)
        self.owner = owner
        self.start = np.array(start, dtype=float)
        self.total = total

    def nearest(self, lon: float, lat: float, only: str | None = None):
        """(link, punto de conexión lon/lat, fracción, distancia m) a la tubería más cercana (u `only`)."""
        if not len(self.owner):
            return None
        px, py = self.tr.transform(lon, lat)
        p = np.array([px, py])
        d = self.b - self.a
        L2 = (d ** 2).sum(axis=1)
        t = np.where(L2 > 0, ((p - self.a) * d).sum(axis=1) / np.where(L2 > 0, L2, 1), 0.0).clip(0, 1)
        q = self.a + d * t[:, None]
        dist = np.hypot(*(q - p).T)
        if only is not None:
            mask = np.array([o == only for o in self.owner])
            if not mask.any():
                return None
            dist = np.where(mask, dist, np.inf)
        i = int(dist.argmin())
        link = self.owner[i]
        along = self.start[i] + t[i] * math.sqrt(L2[i])
        tot = self.total[link]
        lon2, lat2 = from_metric(self.srid).transform(*q[i])
        return link, (float(lon2), float(lat2)), (along / tot if tot > 0 else 0.0), float(dist[i])


# ── Importador ───────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    model: NetworkModel
    srid: int
    opts: ImportOptions
    catalog: list[CatalogItem]
    errors: list[RowError] = field(default_factory=list)
    rowref: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    touched: set[tuple[str, str]] = field(default_factory=set)  # (hoja, id) presentes en el archivo
    file_ids: dict[str, set[str]] = field(default_factory=dict)

    def err(self, sheet: Sheet | None, row: int | None, ident: str | None, msg: str) -> None:
        self.errors.append(RowError(sheet=sheet.name if sheet else None, row=row, id=ident, message=msg))


class Importer:
    def __init__(self, base: NetworkModel, srid: int, opts: ImportOptions, catalog: list[CatalogItem]):
        self.base = base
        self.ctx = _Ctx(model=base.model_copy(deep=True), srid=srid, opts=opts, catalog=catalog)
        self.fc = self.ctx.model.network
        self.tr_utm = from_metric(opts.coord_srid)
        self._pipe_index: PipeIndex | None = None

    # Índices sobre el modelo en construcción
    def nodes(self) -> dict[str, NodeFeature]:
        return {n.id: n for n in self.fc.nodes()}

    def links(self) -> dict[str, LinkFeature]:
        return {lk.id: lk for lk in self.fc.links()}

    def pipe_index(self) -> PipeIndex:
        if self._pipe_index is None:
            recompute_lengths(self.fc, self.ctx.srid)
            self._pipe_index = PipeIndex(self.fc.links(), self.ctx.srid)
        return self._pipe_index

    # ── utilidades de fila ──
    def typed(self, sheet: Sheet, row: RawRow) -> dict[str, Any] | None:
        out: dict[str, Any] = {}
        ok = True
        for key, raw in row.cells.items():
            col = sheet.col(key)
            if col is None:
                continue
            try:
                out[key] = convert(col, raw)
            except CellError as exc:
                ok = False
                self.ctx.err(sheet, row.number, _rid(row), f"Columna «{col.header}»: {exc}.")
        return out if ok else None

    def point(self, sheet: Sheet, row: RawRow, vals: dict[str, Any]) -> tuple[float, float] | None:
        """Coordenadas de la fila (lon, lat) o None si no tiene. Lanza CellError si son inválidas."""
        lat, lon = vals.get("_lat"), vals.get("_lon")
        e, n = vals.get("_east"), vals.get("_north")
        if lat is not None or lon is not None:
            if lat is None or lon is None:
                raise CellError("indique Latitud y Longitud (ambas)")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise CellError(f"Latitud/Longitud fuera de rango ({lat}, {lon}); ¿son coordenadas UTM? "
                                "Use las columnas Este y Norte")
            return float(lon), float(lat)
        if e is not None or n is not None:
            if e is None or n is None:
                raise CellError("indique Este y Norte (ambas)")
            lon2, lat2 = self.tr_utm.transform(e, n)
            if not (math.isfinite(lon2) and math.isfinite(lat2)):
                raise CellError("Este/Norte no se pudieron transformar con el huso indicado")
            return float(lon2), float(lat2)
        return None

    def new_id(self, sheet: Sheet, namespace_ids: set[str]) -> str:
        used = namespace_ids | self.ctx.file_ids.get(sheet.key, set())
        return unique_id(used, sheet.prefix)

    def apply_attrs(self, props, row: RawRow) -> None:
        attrs = dict(props.attributes or {})
        for k, v in row.attributes.items():
            if k.startswith(RESERVED_PREFIX):
                continue
            if v is None:
                attrs.pop(k, None)
            else:
                attrs[k] = v if isinstance(v, (str, int, float)) else str(v)
        props.attributes = attrs

    def check_required(self, sheet: Sheet, row: RawRow, ident: str, merged: dict[str, Any], is_new: bool) -> bool:
        ok = True
        for c in sheet.cols:
            if not c.required:
                continue
            present = c.key in row.cells
            if (is_new and merged.get(c.key) is None) or (present and row.cells.get(c.key) is None and not is_new):
                if is_new or present:
                    self.ctx.err(sheet, row.number, ident, f"Falta «{c.header}» (obligatoria).")
                    ok = False
        return ok

    def rebuild(self, cls, props, sheet: Sheet, row: RawRow, ident: str):
        try:
            return cls.model_validate(props)
        except ValidationError as exc:
            for e in exc.errors():
                key = str(e["loc"][0]) if e.get("loc") else ""
                col = sheet.col(key)
                name = col.header if col else key
                self.ctx.err(sheet, row.number, ident, f"Columna «{name}»: valor no válido ({e['msg']}).")
            return None

    # ── hojas ──
    def ids_for(self, sheet: RawSheet) -> None:
        ids: set[str] = set()
        seen: dict[str, int] = {}
        for r in sheet.rows:
            rid = _rid(r)
            if rid is None:
                continue
            if rid in seen:
                self.ctx.err(sheet.sheet, r.number, rid, f"ID repetido en la hoja (también en la fila {seen[rid]}).")
            seen[rid] = r.number
            ids.add(rid)
        self.ctx.file_ids[sheet.sheet.key] = ids

    def run_nodes(self, raw: RawSheet) -> None:
        sheet = raw.sheet
        other_sheets = {k for k in NODE_SHEETS if k != sheet.key}
        for r in raw.rows:
            vals = self.typed(sheet, r)
            if vals is None:
                continue
            nodes = self.nodes()
            ident = vals.get("id") or self.new_id(sheet, set(nodes))
            if any(ident in self.ctx.file_ids.get(o, set()) for o in other_sheets):
                self.ctx.err(sheet, r.number, ident, "El ID está repetido en otra hoja de nudos (nudos, estanques y "
                                                     "reservorios comparten IDs).")
                continue
            existing = nodes.get(ident)
            if existing is not None and existing.properties.kind != sheet.kind:
                self.ctx.err(sheet, r.number, ident, f"El ID ya existe como otro tipo de nudo "
                                                     f"({existing.properties.kind}); no se puede cambiar el tipo.")
                continue
            try:
                pt = self.point(sheet, r, vals)
            except CellError as exc:
                self.ctx.err(sheet, r.number, ident, f"Coordenadas: {exc}.")
                continue
            if existing is None and pt is None:
                self.ctx.err(sheet, r.number, ident, "Faltan las coordenadas (Latitud/Longitud o Este/Norte).")
                continue
            base = existing.properties.model_dump() if existing else {"kind": sheet.kind}
            fields = {k: v for k, v in vals.items() if not k.startswith("_") and k != "id"}
            merged = {**base, **fields}
            if not self.check_required(sheet, r, ident, merged, existing is None):
                continue
            if "can_overflow" in merged and merged["can_overflow"] is None:
                merged["can_overflow"] = False
            if "base_demand" in merged and merged["base_demand"] is None:
                merged["base_demand"] = 0.0
            if existing is None and merged.get("elevation") is not None:
                merged.setdefault("elevation_method", "Planilla Excel")
            props = self.rebuild(NodeProperties, merged, sheet, r, ident)
            if props is None:
                continue
            self.apply_attrs(props, r)
            geom = PointGeometry(coordinates=pt) if pt else existing.geometry
            feat = NodeFeature(id=ident, geometry=geom, properties=props)
            self._put(feat, existing)
            self._mark(sheet, ident, r.number)

    def run_links(self, raw: RawSheet) -> None:
        sheet = raw.sheet
        for r in raw.rows:
            vals = self.typed(sheet, r)
            if vals is None:
                continue
            links = self.links()
            ident = vals.get("id") or self.new_id(sheet, set(links))
            other = "bombas" if sheet.key == "tramos" else "tramos"
            if ident in self.ctx.file_ids.get(other, set()) or ident in self.ctx.file_ids.get("_control", set()):
                self.ctx.err(sheet, r.number, ident, "El ID está repetido en otra hoja de tramos (tramos, bombas y "
                                                     "válvulas de control comparten IDs).")
                continue
            existing = links.get(ident)
            if existing is not None and existing.properties.kind != sheet.kind:
                self.ctx.err(sheet, r.number, ident, "El ID ya existe como otro tipo de tramo; no se puede cambiar.")
                continue
            base = existing.properties.model_dump() if existing else {"kind": sheet.kind}
            fields = {k: v for k, v in vals.items() if not k.startswith("_") and k != "id"}
            merged = {**base, **fields}
            if not self.check_required(sheet, r, ident, merged, existing is None):
                continue
            for k, default in (("minor_loss", 0.0), ("initial_status", "open"), ("length_choice", "slope")):
                if merged.get(k) is None:
                    merged[k] = default
            if "_length_manual" in vals:
                if merged["length_choice"] == "manual":
                    if vals["_length_manual"] is None:
                        self.ctx.err(sheet, r.number, ident, "«Largo de cálculo» manual requiere «Largo manual».")
                        continue
                    merged["length_hydraulic_m"] = vals["_length_manual"]
            elif merged["length_choice"] == "manual" and existing is None:
                self.ctx.err(sheet, r.number, ident, "«Largo de cálculo» manual requiere la columna «Largo manual».")
                continue
            if sheet.kind == "pipe":
                self.fill_catalog(merged, fields, existing)
            nodes = self.nodes()
            bad = [merged[k] for k in ("from_node", "to_node") if merged.get(k) not in nodes]
            if bad:
                self.ctx.err(sheet, r.number, ident, f"Nudo inexistente: {', '.join(map(str, bad))}.")
                continue
            if merged["from_node"] == merged["to_node"]:
                self.ctx.err(sheet, r.number, ident, "Nudo inicial y final son el mismo.")
                continue
            props = self.rebuild(LinkProperties, merged, sheet, r, ident)
            if props is None:
                continue
            self.apply_attrs(props, r)
            try:
                if vals.get("_vertices") is not None:
                    verts = parse_vertices(vals["_vertices"], self.tr_utm)
                elif existing is not None and "_vertices" not in vals:
                    verts = [tuple(c) for c in existing.geometry.coordinates[1:-1]]
                else:
                    verts = []
            except CellError as exc:
                self.ctx.err(sheet, r.number, ident, f"Columna «Vértices»: {exc}.")
                continue
            a, b = nodes[props.from_node], nodes[props.to_node]
            coords = [a.geometry.coordinates, *verts, b.geometry.coordinates]
            feat = LinkFeature(id=ident, geometry=LineStringGeometry(coordinates=coords), properties=props)
            self._put(feat, existing)
            self._mark(sheet, ident, r.number)

    def fill_catalog(self, merged: dict[str, Any], fields: dict[str, Any], existing: LinkFeature | None) -> None:
        """Diámetro interior y rugosidad desde el catálogo cuando faltan (material + DN + clase)."""
        mat, dn, cls = merged.get("material"), merged.get("dn"), merged.get("pipe_class")
        item = next((c for c in self.ctx.catalog if norm(c.material) == norm(mat or "") and c.dn == dn
                     and norm(c.pipe_class) == norm(cls or "")), None) if mat and dn else None
        if item is not None:
            merged["material"], merged["pipe_class"] = item.material, item.pipe_class
        catalog_keys = {"material", "dn", "pipe_class"}
        if item is not None and merged.get("inner_diameter_mm") is None:
            merged["inner_diameter_mm"] = item.inner_diameter_mm
            merged["inner_diameter_source"] = "catalogo"
            merged["catalog_pipe_id"] = item.id
        elif "inner_diameter_mm" in fields and fields["inner_diameter_mm"] is not None:
            same = item is not None and abs(item.inner_diameter_mm - fields["inner_diameter_mm"]) < 1e-9
            if existing is None or existing.properties.inner_diameter_mm != fields["inner_diameter_mm"]:
                merged["inner_diameter_source"] = "catalogo" if same else "manual"
                merged["catalog_pipe_id"] = item.id if same else (item.id if item else None)
        elif catalog_keys & set(fields):
            merged["catalog_pipe_id"] = item.id if item else None
        if item is not None and merged.get("roughness") is None:
            f = self.ctx.model.options.headloss
            merged["roughness"] = {"D-W": item.dw_roughness_mm, "C-M": item.manning_n}.get(f, item.hw_c)

    def run_valves(self, raw: RawSheet, phase: str) -> None:
        """phase «control»: válvulas entre nudos (tramos). phase «corte»: llaves sobre tuberías."""
        sheet = raw.sheet
        shut_by_id = {s.id: s for s in self.fc.shutoffs()}
        for r in raw.rows:
            vals = self.typed(sheet, r)
            if vals is None:
                continue
            links = self.links()
            ident = vals.get("id")
            existing_sh = shut_by_id.get(ident) if ident else None
            existing_lk = links.get(ident) if ident else None
            if existing_lk is not None and existing_lk.properties.kind != "valve":
                existing_lk = None if existing_sh else existing_lk
            klass = vals.get("_class") or ("corte" if existing_sh else "control" if existing_lk else None)
            if klass is None:
                t = vals.get("_type")
                klass = "control" if (t in CONTROL_TYPES or vals.get("from_node")) else "corte"
            if existing_sh and klass == "control" or existing_lk and klass == "corte":
                if phase == "corte":
                    self.ctx.err(sheet, r.number, ident, "No se puede cambiar la clase de una válvula existente.")
                continue
            if klass != phase:
                continue
            if existing_lk is not None and existing_lk.properties.kind != "valve":
                self.ctx.err(sheet, r.number, ident, "El ID ya existe como tramo o bomba.")
                continue
            if ident is None:
                ident = unique_id(set(links) | set(shut_by_id) | self.ctx.file_ids.get("valvulas", set()),
                                  "V" if klass == "control" else "LL")
                self.ctx.file_ids.setdefault("valvulas", set()).add(ident)
            if klass == "control":
                self._control_valve(sheet, r, vals, ident, existing_lk)
            else:
                self._shutoff(sheet, r, vals, ident, existing_sh)
                shut_by_id = {s.id: s for s in self.fc.shutoffs()}

    def _control_valve(self, sheet: Sheet, r: RawRow, vals: dict, ident: str, existing: LinkFeature | None) -> None:
        if ident in self.ctx.file_ids.get("tramos", set()) | self.ctx.file_ids.get("bombas", set()):
            self.ctx.err(sheet, r.number, ident, "El ID está repetido en Tramos o Bombas.")
            return
        base = existing.properties.model_dump() if existing else {"kind": "valve", "initial_status": "active",
                                                                  "minor_loss": 0.0, "length_choice": "plan"}
        merged = dict(base)
        for k in ("from_node", "to_node", "valve_setting", "valve_curve"):
            if k in vals:
                merged[k] = vals[k]
        if "_type" in vals:
            if vals["_type"] is not None and vals["_type"] not in CONTROL_TYPES:
                self.ctx.err(sheet, r.number, ident, f"Tipo «{vals['_type']}» no es de control (PRV, PSV, PBV, FCV, "
                                                     "TCV, GPV, PCV).")
                return
            merged["valve_type"] = vals["_type"]
        if "_state" in vals and vals["_state"] is not None:
            merged["initial_status"] = vals["_state"]
        if "_diameter" in vals:
            merged["inner_diameter_mm"] = vals["_diameter"]
        if "name" in vals:
            merged["description"] = vals["name"]
        attrs = dict(merged.get("attributes") or {})
        for key, attr in (("condition", "__condition"), ("_depth", "__depth_m")):
            if key in vals:
                if vals[key] is None:
                    attrs.pop(attr, None)
                else:
                    attrs[attr] = vals[key]
        merged["attributes"] = attrs
        missing = [h for k, h in (("from_node", "Nudo inicial"), ("to_node", "Nudo final"), ("valve_type", "Tipo"))
                   if merged.get(k) is None]
        if missing:
            self.ctx.err(sheet, r.number, ident, f"Válvula de control: falta {', '.join(missing)}.")
            return
        nodes = self.nodes()
        bad = [merged[k] for k in ("from_node", "to_node") if merged[k] not in nodes]
        if bad:
            self.ctx.err(sheet, r.number, ident, f"Nudo inexistente: {', '.join(bad)}.")
            return
        props = self.rebuild(LinkProperties, merged, sheet, r, ident)
        if props is None:
            return
        self.apply_attrs(props, r)
        coords = [nodes[props.from_node].geometry.coordinates, nodes[props.to_node].geometry.coordinates]
        self._put(LinkFeature(id=ident, geometry=LineStringGeometry(coordinates=coords), properties=props), existing)
        self._mark(sheet, ident, r.number, ns="link")

    def _shutoff(self, sheet: Sheet, r: RawRow, vals: dict, ident: str, existing: ShutoffFeature | None) -> None:
        base = existing.properties.model_dump() if existing else {}
        merged = dict(base)
        for src, dst in (("_type", "valve_type"), ("_state", "state"), ("_diameter", "diameter_mm"),
                         ("_depth", "depth_m"), ("condition", "condition"), ("name", "name"), ("link", "link"),
                         ("position", "position")):
            if src in vals:
                merged[dst] = vals[src]
        if merged.get("valve_type") is not None and merged["valve_type"] not in SHUTOFF_TYPES:
            self.ctx.err(sheet, r.number, ident, f"Tipo «{merged['valve_type']}» no es de corte (compuerta, mariposa, "
                                                 "bola, otra).")
            return
        if merged.get("state") is None:
            merged["state"] = "open"
        if merged["state"] not in ("open", "closed"):
            self.ctx.err(sheet, r.number, ident, "Una válvula de corte solo puede estar abierta o cerrada.")
            return
        try:
            pt = self.point(sheet, r, vals)
        except CellError as exc:
            self.ctx.err(sheet, r.number, ident, f"Coordenadas: {exc}.")
            return
        links = self.links()
        link_given = vals.get("link") is not None
        if link_given and (vals["link"] not in links or links[vals["link"]].properties.kind != "pipe"):
            self.ctx.err(sheet, r.number, ident, f"El tramo «{vals['link']}» no existe o no es una tubería.")
            return
        coords_changed = pt is not None and (existing is None or _moved(existing.geometry.coordinates, pt))
        if merged.get("link") is None or (coords_changed and not link_given):
            if pt is None:
                self.ctx.err(sheet, r.number, ident, "Indique el Tramo o las coordenadas de la válvula.")
                return
            hit = self.pipe_index().nearest(*pt)
            if hit is None:
                self.ctx.err(sheet, r.number, ident, "No hay tuberías donde ubicar la válvula.")
                return
            merged["link"], merged["position"] = hit[0], round(hit[2], 6)
        elif merged.get("position") is None or ("position" not in vals and coords_changed):
            hit = self.pipe_index().nearest(*pt, only=merged["link"]) if pt else None
            merged["position"] = round(hit[2], 6) if hit else 0.5
        props = self.rebuild(ShutoffProperties, merged, sheet, r, ident)
        if props is None:
            return
        self.apply_attrs(props, r)
        geom = existing.geometry if existing else PointGeometry(coordinates=pt or (0.0, 0.0))
        self._put(ShutoffFeature(id=ident, geometry=geom, properties=props), existing)
        self._mark(sheet, ident, r.number, ns="shutoff")

    def run_points(self, raw: RawSheet) -> None:
        """Grifos, pozos y clientes."""
        sheet = raw.sheet
        cls_f = {"grifos": HydrantFeature, "pozos": WellFeature, "clientes": ClientFeature}[sheet.key]
        cls_p = {"grifos": HydrantProperties, "pozos": WellProperties, "clientes": ClientProperties}[sheet.key]
        getter = {"grifos": self.fc.hydrants, "pozos": self.fc.wells, "clientes": self.fc.clients}[sheet.key]
        for r in raw.rows:
            vals = self.typed(sheet, r)
            if vals is None:
                continue
            current = {f.id: f for f in getter()}
            ident = vals.get("id") or self.new_id(sheet, set(current))
            existing = current.get(ident)
            try:
                pt = self.point(sheet, r, vals)
            except CellError as exc:
                self.ctx.err(sheet, r.number, ident, f"Coordenadas: {exc}.")
                continue
            base = existing.properties.model_dump() if existing else {}
            fields = {k: v for k, v in vals.items() if not k.startswith("_") and k != "id"}
            merged = {**base, **fields}
            if not self.check_required(sheet, r, ident, merged, existing is None):
                continue
            nodes = self.nodes()
            coords_changed = pt is not None and (existing is None or _moved(existing.geometry.coordinates, pt))
            if sheet.key == "grifos":
                for k, d in (("fire_flow_lps", 16.0), ("min_pressure_m", 5.0)):
                    if merged.get(k) is None:
                        merged[k] = d
                if merged.get("node") is None or (coords_changed and "node" not in vals):
                    if pt is None:
                        self.ctx.err(sheet, r.number, ident, "Indique el Nudo o las coordenadas del grifo.")
                        continue
                    merged["node"] = _nearest_node(nodes, pt, {"junction"}, self.ctx.srid)
                    if merged["node"] is None:
                        self.ctx.err(sheet, r.number, ident, "No hay nudos de consumo donde conectar el grifo.")
                        continue
                if merged["node"] not in nodes or nodes[merged["node"]].properties.kind != "junction":
                    self.ctx.err(sheet, r.number, ident, f"El nudo «{merged['node']}» no existe o no es de consumo.")
                    continue
                if pt is None and existing is None:
                    pt = tuple(nodes[merged["node"]].geometry.coordinates)
            elif sheet.key == "pozos":
                if merged.get("node") is not None and (merged["node"] not in nodes
                                                       or nodes[merged["node"]].properties.kind != "reservoir"):
                    self.ctx.err(sheet, r.number, ident, f"El reservorio «{merged['node']}» no existe.")
                    continue
                if pt is None and existing is None:
                    if merged.get("node") is None:
                        self.ctx.err(sheet, r.number, ident, "Faltan las coordenadas del pozo.")
                        continue
                    pt = tuple(nodes[merged["node"]].geometry.coordinates)
            else:
                if not self._connect_client(sheet, r, vals, merged, existing, pt, coords_changed, nodes):
                    continue
                if pt is None and existing is None:
                    pt = merged.pop("_pos")
                merged.pop("_pos", None)
                for k, d in (("client_type", "residencial"), ("status", "activo"), ("consumption_unit", "L/s")):
                    if merged.get(k) is None:
                        merged[k] = d
                merged.setdefault("connection_mode", "nearest")
            props = self.rebuild(cls_p, merged, sheet, r, ident)
            if props is None:
                continue
            self.apply_attrs(props, r)
            geom = PointGeometry(coordinates=pt) if pt else existing.geometry
            self._put(cls_f(id=ident, geometry=geom, properties=props), existing)
            self._mark(sheet, ident, r.number)

    def _connect_client(self, sheet, r, vals, merged, existing, pt, coords_changed, nodes) -> bool:
        links = self.links()
        node_given, link_given = vals.get("node") is not None, vals.get("link") is not None
        if link_given and (vals["link"] not in links or links[vals["link"]].properties.kind != "pipe"):
            self.ctx.err(sheet, r.number, merged.get("id") or _rid(r), f"El tramo «{vals['link']}» no existe o no "
                                                                       "es una tubería.")
            return False
        ident = _rid(r)
        if node_given:
            n = nodes.get(vals["node"])
            if n is None or n.properties.kind != "junction":
                self.ctx.err(sheet, r.number, ident, f"El nudo «{vals['node']}» no existe o no es un nudo de consumo.")
                return False
            if link_given:
                hit = self.pipe_index().nearest(*(pt or n.geometry.coordinates), only=vals["link"])
                merged["connection"] = hit[1] if hit else None
            elif coords_changed or existing is None:
                merged["link"], merged["connection"] = None, None
            merged["_pos"] = n.geometry.coordinates
            return True
        if link_given:
            lk = links[vals["link"]]
            ref = pt or _midpoint(lk)
            hit = self.pipe_index().nearest(*ref, only=lk.id)
            merged["connection"] = hit[1] if hit else None
            ends = [nodes[x] for x in (lk.properties.from_node, lk.properties.to_node)
                    if x in nodes and nodes[x].properties.kind == "junction"]
            if not ends:
                self.ctx.err(sheet, r.number, ident, f"El tramo «{lk.id}» no tiene nudos de consumo en sus extremos.")
                return False
            merged["node"] = _nearest_node({n.id: n for n in ends}, merged["connection"] or ref, {"junction"},
                                           self.ctx.srid)
            merged["_pos"] = ref
            return True
        if existing is not None and not coords_changed and merged.get("node") in nodes and "node" not in vals:
            return True
        if "node" in vals and existing is not None and not coords_changed:
            # Columna Nudo presente pero vacía: se reconecta al más cercano.
            pt = pt or tuple(existing.geometry.coordinates)
        if pt is None:
            self.ctx.err(sheet, r.number, ident, "Indique coordenadas, Nudo o Tramo del cliente.")
            return False
        hit = self.pipe_index().nearest(*pt)
        if hit is None:
            target = _nearest_node(nodes, pt, {"junction"}, self.ctx.srid)
            if target is None:
                self.ctx.err(sheet, r.number, ident, "La red no tiene nudos de consumo para conectar el cliente.")
                return False
            merged["node"], merged["link"], merged["connection"] = target, None, None
            return True
        link_id, conn = hit[0], hit[1]
        lk = links[link_id]
        ends = {x: nodes[x] for x in (lk.properties.from_node, lk.properties.to_node)
                if x in nodes and nodes[x].properties.kind == "junction"}
        target = _nearest_node(ends or nodes, conn, {"junction"}, self.ctx.srid)
        if target is None:
            self.ctx.err(sheet, r.number, ident, "La red no tiene nudos de consumo para conectar el cliente.")
            return False
        merged["node"], merged["link"], merged["connection"] = target, link_id, conn
        return True

    def run_model_sheet(self, rows: list[tuple[str, str]]) -> None:
        for key, value in rows:
            k = norm(key)
            if k.startswith("opciones"):
                try:
                    self.ctx.model.options = HydraulicOptions.model_validate(json.loads(value))
                except (ValueError, ValidationError) as exc:
                    self.ctx.errors.append(RowError(sheet="Modelo", message=f"Opciones hidráulicas no válidas: {exc}"))
            elif k.startswith("seccion "):
                name = key.split(" ", 1)[1].strip()
                if value.strip():
                    self.ctx.model.aux[name] = value
                else:
                    self.ctx.model.aux.pop(name, None)

    # ── internos ──
    def _put(self, feat, existing) -> None:
        feats = self.fc.features
        if existing is not None:
            idx = next(i for i, f in enumerate(feats) if f is existing)
            feats[idx] = feat
        else:
            feats.append(feat)
        if isinstance(feat, (LinkFeature, NodeFeature)):
            self._pipe_index = None

    def _mark(self, sheet: Sheet, ident: str, row: int, ns: str | None = None) -> None:
        self.ctx.rowref[(ns or NS_OF_SHEET[sheet.key], ident)] = (sheet.name, row)
        self.ctx.touched.add((sheet.key, ident))

    def delete_missing(self, present: set[str]) -> None:
        """Quita los elementos de las hojas presentes que no aparecen en el archivo."""
        kind_sheet = {"junction": "nudos", "tank": "estanques", "reservoir": "reservorios", "pipe": "tramos",
                      "pump": "bombas", "valve": "valvulas"}
        elem_sheet = {"shutoff": "valvulas", "hydrant": "grifos", "well": "pozos", "client": "clientes"}
        out = []
        for f in self.fc.features:
            p = f.properties
            sk = kind_sheet[p.kind] if p.element in ("node", "link") else elem_sheet[p.element]
            if sk in present and (sk, f.id) not in self.ctx.touched:
                continue
            out.append(f)
        self.fc.features = out

    def infer_well_heads(self) -> None:
        nodes = self.nodes()
        for w in self.fc.wells():
            p = w.properties
            n = nodes.get(p.node or "")
            if n is None or n.properties.head is not None:
                continue
            if p.ground_elevation is not None and p.dynamic_level_m is not None:
                n.properties.head = round(p.ground_elevation - p.dynamic_level_m, 4)


def _rid(r: RawRow) -> str | None:
    v = r.cells.get("id")
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip() or None


def _moved(old, new, tol: float = 1e-9) -> bool:
    return abs(old[0] - new[0]) > tol or abs(old[1] - new[1]) > tol


def _midpoint(lk: LinkFeature) -> tuple[float, float]:
    c = lk.geometry.coordinates
    return ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)


def _nearest_node(nodes: dict[str, NodeFeature], pt, kinds: set[str], srid: int) -> str | None:
    tr = to_metric(srid)
    px, py = tr.transform(*pt)
    best, bd = None, math.inf
    for n in nodes.values():
        if n.properties.kind not in kinds:
            continue
        x, y = tr.transform(*n.geometry.coordinates)
        d = math.hypot(x - px, y - py)
        if d < bd:
            best, bd = n.id, d
    return best


# ── Comparación ──────────────────────────────────────────────────────────

def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    return a == b


def diff_rows(sheet: Sheet, old: Row, new: Row) -> list[FieldChange]:
    out: list[FieldChange] = []
    for c in sheet.cols:
        if c.key == "id" or c.computed or c.key in old.derived or c.key in new.derived:
            continue
        a, b = old.values.get(c.key), new.values.get(c.key)
        if not _same(a, b):
            out.append(FieldChange(field=c.header, old=_scalar(c.label_of(a)), new=_scalar(c.label_of(b))))
    for k in sorted(set(old.attributes) | set(new.attributes)):
        a, b = old.attributes.get(k), new.attributes.get(k)
        if not _same(a, b):
            out.append(FieldChange(field=k, old=_scalar(a), new=_scalar(b)))
    return out


def _scalar(v: Any) -> Any:
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


# ── Punto de entrada ─────────────────────────────────────────────────────

def run_import(base: NetworkModel, sheets: dict[str, RawSheet], model_sheet: list[tuple[str, str]] | None,
               *, srid: int, opts: ImportOptions, catalog: list[CatalogItem], notes: list[str] | None = None,
               base_version: int | None = None) -> Outcome:
    imp = Importer(base, srid, opts, catalog)
    ctx = imp.ctx
    for raw in sheets.values():
        for row, msg in raw.errors:
            ctx.err(raw.sheet, row, None, msg)
        imp.ids_for(raw)
    if model_sheet is not None:
        imp.run_model_sheet(model_sheet)
    # Dependencias: nudos → tramos/bombas/válvulas de control → llaves, grifos, pozos, clientes.
    for key in NODE_SHEETS:
        if key in sheets:
            imp.run_nodes(sheets[key])
    if "valvulas" in sheets:
        ctx.file_ids["_control"] = set()
        for r in sheets["valvulas"].rows:
            if norm(r.cells.get("_class") or "") == "control" and _rid(r):
                ctx.file_ids["_control"].add(_rid(r))
    for key in ("tramos", "bombas"):
        if key in sheets:
            imp.run_links(sheets[key])
    if "valvulas" in sheets:
        imp.run_valves(sheets["valvulas"], "control")
        imp.run_valves(sheets["valvulas"], "corte")
    for key in ("pozos", "grifos", "clientes"):
        if key in sheets:
            imp.run_points(sheets[key])
    if opts.delete_missing:
        imp.delete_missing(set(sheets))
    imp.infer_well_heads()

    model = ctx.model
    if not ctx.errors:
        report = validate_model(model, structural_only=True)
        for issue in report.errors:
            ns = {"node": "node", "link": "link"}.get(issue.element_type or "", issue.element_type or "")
            ref = ctx.rowref.get((ns, issue.element_id or ""))
            if ref is None and issue.element_type in ETYPE_SHEET:
                ref = ctx.rowref.get((issue.element_type, issue.element_id or ""))
            ctx.errors.append(RowError(sheet=ref[0] if ref else None, row=ref[1] if ref else None,
                                       id=issue.element_id, message=issue.message))
    if not ctx.errors:
        recompute_lengths(model.network, srid)
        place_shutoffs(model.network, srid)

    preview = ImportPreview(ok=not ctx.errors, base_version=base_version, coord_srid=opts.coord_srid,
                            delete_missing=opts.delete_missing, errors=ctx.errors, notes=list(notes or []))
    if ctx.errors:
        preview.summary = _summary(preview, sheets)
        return Outcome(preview, None)

    before = model_rows(base, srid)
    after = model_rows(model, srid)
    for sheet in SHEETS:
        old = {r.id: r for r in before[sheet.key]}
        new = {r.id: r for r in after[sheet.key]}
        for ident, row in new.items():
            ref = ctx.rowref.get((_ns_for(sheet, row), ident))
            rownum = ref[1] if ref else None
            if ident not in old:
                preview.new.append(ChangeItem(sheet=sheet.name, id=ident, row=rownum))
                continue
            changes = diff_rows(sheet, old[ident], row)
            if changes:
                preview.modified.append(ChangeItem(sheet=sheet.name, id=ident, row=rownum, changes=changes))
            elif (sheet.key, ident) in ctx.touched:
                preview.unchanged.append(ChangeItem(sheet=sheet.name, id=ident, row=rownum))
        for ident in old:
            if ident not in new:
                preview.deleted.append(ChangeItem(sheet=sheet.name, id=ident))
    if model_sheet is not None:
        old_m, new_m = dict(model_sheet_rows(base)), dict(model_sheet_rows(model))
        changes = [FieldChange(field=k, old=_short(old_m.get(k)), new=_short(new_m.get(k)))
                   for k in sorted(set(old_m) | set(new_m)) if old_m.get(k) != new_m.get(k)]
        if changes:
            preview.modified.append(ChangeItem(sheet="Modelo", id="modelo", changes=changes))
    preview.summary = _summary(preview, sheets)
    return Outcome(preview, model)


def _ns_for(sheet: Sheet, row: Row) -> str:
    if sheet.key == "valvulas":
        return "link" if row.values.get("_class") == "control" else "shutoff"
    return NS_OF_SHEET[sheet.key]


def _short(v: str | None) -> str | None:
    if v is None:
        return None
    return v if len(v) <= 120 else v[:117] + "…"


def _summary(p: ImportPreview, sheets: dict[str, RawSheet]) -> list[SheetSummary]:
    out: dict[str, SheetSummary] = {}
    order = [s.name for s in SHEETS] + ["Modelo"]
    for attr in ("new", "modified", "unchanged", "deleted"):
        for item in getattr(p, attr):
            s = out.setdefault(item.sheet, SheetSummary(sheet=item.sheet))
            setattr(s, attr, getattr(s, attr) + 1)
    for e in p.errors:
        s = out.setdefault(e.sheet or "General", SheetSummary(sheet=e.sheet or "General"))
        s.errors += 1
    for key in sheets:
        name = SHEET_BY_KEY[key].name
        out.setdefault(name, SheetSummary(sheet=name))
    return sorted(out.values(), key=lambda s: order.index(s.sheet) if s.sheet in order else 99)
