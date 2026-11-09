"""Importación de clientes desde CSV: columnas lat, lon, nombre, consumo (L/s); opcionales tipo, estado y unidad.

Separador «,» o «;» (con «;» se acepta coma decimal). Cada cliente se proyecta sobre la tubería más
cercana y se asigna al nudo de consumo más cercano al punto de conexión. La importación es todo o nada:
si alguna fila es inválida no se guarda nada. Crea una versión nueva del modelo.
"""
from __future__ import annotations

import csv
import io
import unicodedata

from sqlalchemy.orm import Session

from app.models import Project
from app.schemas.analysis import ClientImportResult, ClientImportRow
from app.schemas.network import ClientFeature, ClientProperties, PointGeometry
from app.schemas.project import NetworkSave
from app.services.connection import assign_node, nearest_pipe, unique_id
from app.services.errors import Conflict
from app.services.network import get_version_or_404, load_model, save_network

FAR_M = 100.0
MAX_ROWS = 20000
TYPES = {"residencial", "comercial", "industrial", "publico"}
ALIASES = {"latitud": "lat", "longitud": "lon", "lng": "lon", "name": "nombre", "direccion": "nombre",
           "consumo_lps": "consumo", "consumo (l/s)": "consumo", "type": "tipo", "status": "estado"}


class CsvImportError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]))
        self.errors = errors


def _key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.strip().lower()).encode("ascii", "ignore").decode()
    return ALIASES.get(s, s)


def _num(s: str, comma_decimal: bool) -> float:
    t = (s or "").strip()
    if comma_decimal:
        t = t.replace(".", "").replace(",", ".") if "," in t else t
    return float(t)


def parse(text: str) -> tuple[list[dict], list[str]]:
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    if not reader.fieldnames:
        raise CsvImportError(["El archivo está vacío."])
    fields = {_key(f): f for f in reader.fieldnames if f}
    missing = [c for c in ("lat", "lon", "nombre", "consumo") if c not in fields]
    if missing:
        raise CsvImportError([f"Faltan columnas: {', '.join(missing)} (se requieren lat, lon, nombre, consumo)."])
    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):
        if i - 1 > MAX_ROWS:
            errors.append(f"Más de {MAX_ROWS} filas.")
            break
        get = lambda k: (raw.get(fields[k]) or "").strip() if k in fields else ""  # noqa: E731
        if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
            continue
        try:
            lat, lon = _num(get("lat"), delim == ";"), _num(get("lon"), delim == ";")
            consumo = _num(get("consumo"), delim == ";")
        except ValueError:
            errors.append(f"Línea {i}: lat, lon y consumo deben ser números.")
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            errors.append(f"Línea {i}: coordenadas fuera de rango ({lat}, {lon}).")
            continue
        if consumo < 0:
            errors.append(f"Línea {i}: consumo negativo.")
            continue
        tipo = _key(get("tipo")) or "residencial"
        estado = _key(get("estado")) or "activo"
        unidad = get("unidad").replace("³", "3").lower() or "l/s"
        if tipo not in TYPES:
            errors.append(f"Línea {i}: tipo «{get('tipo')}» no válido (residencial, comercial, industrial, publico).")
            continue
        if estado not in ("activo", "proyectado"):
            errors.append(f"Línea {i}: estado «{get('estado')}» no válido (activo, proyectado).")
            continue
        if unidad not in ("l/s", "m3/mes"):
            errors.append(f"Línea {i}: unidad «{get('unidad')}» no válida (L/s, m3/mes).")
            continue
        rows.append({"line": i, "lat": lat, "lon": lon, "name": get("nombre") or None, "value": consumo,
                     "unit": "L/s" if unidad == "l/s" else "m3/mes", "type": tipo, "status": estado})
    if not rows and not errors:
        errors.append("El archivo no tiene filas de datos.")
    return rows, errors


def import_csv(session: Session, project: Project, content: bytes, base_version: int | None) -> ClientImportResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    rows, errors = parse(text)
    latest = get_version_or_404(session, project, None)
    if base_version is not None and base_version != latest.number:
        raise Conflict(f"La versión base {base_version} no es la última ({latest.number}). Recargue el proyecto.")
    model = load_model(session, latest)
    fc = model.network
    srid = project.length_srid
    used = {c.id for c in fc.clients()}
    out: list[ClientImportRow] = []
    for r in rows:
        pr = nearest_pipe(fc, r["lon"], r["lat"], srid)
        target = assign_node(fc, pr, srid) if pr else None
        if pr is None or target is None:
            errors.append(f"Línea {r['line']}: la red no tiene tuberías con nudos de consumo para conectar el cliente.")
            continue
        cid = unique_id(used, "C")
        used.add(cid)
        props = ClientProperties(name=r["name"], client_type=r["type"], status=r["status"],
                                 consumption_value=r["value"], consumption_unit=r["unit"], node=target[0],
                                 link=pr.link, connection=pr.point, connection_mode="nearest")
        fc.features.append(ClientFeature(id=cid, geometry=PointGeometry(coordinates=(r["lon"], r["lat"])),
                                         properties=props))
        warn = f"a {pr.distance_m:.0f} m de la tubería más cercana" if pr.distance_m > FAR_M else None
        out.append(ClientImportRow(line=r["line"], id=cid, name=r["name"], consumption_lps=round(props.consumption_lps, 6),
                                   node=target[0], link=pr.link, distance_m=round(pr.distance_m, 2), warning=warn))
    if errors:
        raise CsvImportError(errors)
    saved = save_network(session, project, NetworkSave(
        base_version=latest.number, kind="manual", label=f"Importación CSV: {len(out)} clientes",
        options=model.options, aux=model.aux, network=fc, scenarios=model.scenarios))
    return ClientImportResult(version=saved.version, created=len(out), rows=out)
