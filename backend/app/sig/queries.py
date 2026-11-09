"""Consultas por atributos (condiciones combinables con Y/O) y búsqueda rápida global."""
from __future__ import annotations

from typing import Any

from app.schemas.network import NetworkModel
from app.schemas.sig import Condition, ConditionGroup, QueryElement, QueryField, QueryResult, SearchHit

from .sectors import compute_sectors, sector_of_client, sector_of_node, sectors_of_link
from .spec import SHEET_BY_KEY, SHEETS, Col, Sheet, norm
from .tables import Row, model_rows

EXTRA_FIELDS: dict[str, list[QueryField]] = {
    "tramos": [QueryField(key="cuartel", label="Cuartel", type="str")],
    "nudos": [QueryField(key="cuartel", label="Cuartel", type="str")],
    "clientes": [QueryField(key="cuartel", label="Cuartel", type="str"),
                 QueryField(key="_consumption_lps", label="Consumo (L/s)", type="float", unit="L/s")],
}


class QueryError(ValueError):
    pass


def _field(c: Col) -> QueryField:
    t = c.kind if c.kind in ("str", "float", "int", "choice", "bool") else "str"
    return QueryField(key=c.key, label=c.header + (f" ({c.unit})" if c.unit else ""), type=t, unit=c.unit,
                      choices=list(c.choices.items()) if c.choices else None)


def elements() -> list[QueryElement]:
    out = []
    for s in SHEETS:
        fields = [_field(c) for c in s.cols if c.query]
        fields += EXTRA_FIELDS.get(s.key, [])
        out.append(QueryElement(key=s.key, label=s.name, fields=fields, sum_field=s.sum_field))
    return out


def _rows(model: NetworkModel, sheet: Sheet, srid: int, need_sectors: bool) -> list[dict[str, Any]]:
    rows: list[Row] = model_rows(model, srid)[sheet.key]
    sec_link = sec_node = sec_client = None
    if need_sectors:
        res = compute_sectors(model)
        sec_link, sec_node, sec_client = sectors_of_link(res), sector_of_node(res), sector_of_client(res)
    out = []
    for r in rows:
        d: dict[str, Any] = {"id": r.id, **r.values}
        for k, v in r.attributes.items():
            d.setdefault(k, v)
        if sheet.key == "clientes":
            from app.schemas.network import to_lps

            d["_consumption_lps"] = round(to_lps(r.values.get("consumption_value") or 0.0,
                                                 r.values.get("consumption_unit") or "L/s"), 6)
            if sec_client is not None:
                d["cuartel"] = sec_client.get(r.id)
        elif sheet.key == "tramos" and sec_link is not None:
            d["cuartel"] = ", ".join(sec_link.get(r.id, [])) or None
        elif sheet.key == "nudos" and sec_node is not None:
            d["cuartel"] = sec_node.get(r.id)
        out.append(d)
    return out


def _fields_used(group: ConditionGroup) -> set[str]:
    out = set()
    for c in group.conditions:
        out |= _fields_used(c) if isinstance(c, ConditionGroup) else {c.field}
    return out


def _coerce(value: Any, ftype: str, choices: dict[str, str] | None) -> Any:
    if value is None:
        return None
    if ftype in ("float", "int"):
        try:
            return float(str(value).replace(",", ".")) if not isinstance(value, (int, float)) else float(value)
        except ValueError as exc:
            raise QueryError(f"«{value}» no es un número") from exc
    if ftype == "choice" and choices:
        s = norm(value)
        for k, label in choices.items():
            if s in (norm(k), norm(label)):
                return norm(k)
    return norm(value)


def _match(row: dict[str, Any], c: Condition, ftypes: dict[str, tuple[str, dict | None]]) -> bool:
    ftype, choices = ftypes.get(c.field, ("str", None))
    raw = row.get(c.field)
    if c.op == "empty":
        return raw is None or raw == ""
    if c.op == "not_empty":
        return not (raw is None or raw == "")
    if raw is None:
        return False
    if c.field == "cuartel" and isinstance(raw, str) and c.op == "eq":
        target = norm(c.value) if c.value is not None else None
        return target in [norm(x) for x in raw.split(",")]
    if c.op == "in":
        vals = c.value if isinstance(c.value, list) else str(c.value or "").split(",")
        return _coerce(raw, ftype, choices) in {_coerce(v, ftype, choices) for v in vals if v not in (None, "")}
    a = _coerce(raw, ftype, choices)
    b = _coerce(c.value, ftype, choices)
    if b is None:
        raise QueryError(f"La condición sobre «{c.field}» necesita un valor")
    if c.op == "contains":
        return str(b) in str(a)
    if c.op == "starts":
        return str(a).startswith(str(b))
    if isinstance(a, float) != isinstance(b, float):
        a, b = str(a), str(b)
    return {"eq": a == b, "ne": a != b, "lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[c.op]


def _eval(row: dict, group: ConditionGroup, ftypes) -> bool:
    if not group.conditions:
        return True
    results = (_eval(row, c, ftypes) if isinstance(c, ConditionGroup) else _match(row, c, ftypes)
               for c in group.conditions)
    return all(results) if group.logic == "and" else any(results)


def run_query(model: NetworkModel, element: str, where: ConditionGroup, *, srid: int,
              version: int) -> QueryResult:
    sheet = SHEET_BY_KEY.get(element)
    if sheet is None:
        raise QueryError(f"Tipo de elemento «{element}» desconocido")
    meta = next(e for e in elements() if e.key == element)
    known = {f.key: f for f in meta.fields}
    for f in _fields_used(where):
        if f not in known and not f.startswith("attr:"):
            known[f] = QueryField(key=f, label=f, type="str")  # atributo libre
    ftypes = {k: (f.type, dict(f.choices) if f.choices else None) for k, f in known.items()}
    rows = _rows(model, sheet, srid, need_sectors="cuartel" in known)
    hits = [r for r in rows if _eval(r, where, ftypes)]
    sums: dict[str, float] = {}
    if sheet.sum_field:
        sums[sheet.sum_field] = round(sum(float(r.get(sheet.sum_field) or 0) for r in hits), 4)
    if element == "clientes":
        sums["consumption_m3_mes"] = round(sums.get("_consumption_lps", 0.0) * 30 * 86400 / 1000, 3)
    columns = [QueryField(key="id", label="ID", type="str")] + [f for f in known.values() if f.key != "id"]
    extra = sorted({k for r in hits for k in r if k not in known and not k.startswith("_")} - {"id"})
    columns += [QueryField(key=k, label=k, type="str") for k in extra]
    out_rows = []
    for r in hits:
        out_rows.append({c.key: _display(r.get(c.key), c) for c in columns})
    return QueryResult(element=element, model_version=version, count=len(hits), total=len(rows), sums=sums,
                       columns=columns, rows=out_rows)


def _display(v: Any, f: QueryField) -> Any:
    if v is None:
        return None
    if f.choices:
        return dict(f.choices).get(str(v), v)
    if f.type == "bool":
        return "sí" if v else "no"
    return v if isinstance(v, (str, int, float, bool)) else str(v)


SEARCH_FIELDS = {"name": "nombre", "address": "dirección", "meter_number": "N° medidor",
                 "client_number": "N° cliente", "description": "observaciones", "route": "ruta"}
ETYPE = {"nudos": "node", "estanques": "node", "reservorios": "node", "tramos": "link", "bombas": "link",
         "grifos": "hydrant", "pozos": "well", "clientes": "client"}


def search(model: NetworkModel, q: str, *, srid: int, limit: int = 50) -> list[SearchHit]:
    needle = norm(q)
    if not needle:
        return []
    all_rows = model_rows(model, srid)
    exact, partial = [], []
    for sheet in SHEETS:
        for r in all_rows[sheet.key]:
            etype = ETYPE.get(sheet.key) or ("link" if r.values.get("_class") == "control" else "shutoff")
            text = r.values.get("name") or r.values.get("address") or r.values.get("description") or ""
            if norm(r.id) == needle:
                exact.append(SearchHit(element=sheet.key, element_type=etype, id=r.id, text=str(text), match="ID"))
                continue
            if needle in norm(r.id):
                partial.append(SearchHit(element=sheet.key, element_type=etype, id=r.id, text=str(text), match="ID"))
                continue
            for key, label in SEARCH_FIELDS.items():
                v = r.values.get(key)
                if v and needle in norm(v):
                    partial.append(SearchHit(element=sheet.key, element_type=etype, id=r.id, text=str(v), match=label))
                    break
    return (exact + partial)[:limit]
