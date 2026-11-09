"""Lectura de archivos .inp con el toolkit de OWA-EPANET.

1. El motor abre el archivo (cualquier sistema de unidades) y valida su sintaxis.
2. Se cambia a L/s y presión en metros: el motor convierte internamente todas las magnitudes.
3. La estructura (nudos, tramos, demandas, coordenadas, vértices) se lee con los getters del
   toolkit (precisión doble). Las secciones complementarias (patrones, curvas, controles, reglas,
   tiempos, energía, calidad) se toman del .inp en SI que escribe el propio motor.
4. Las coordenadas se georreferencian: SRID indicado, UTM detectada o ubicación local escalada.
"""
from __future__ import annotations

import math
import os
import re
import statistics
import uuid
import warnings
from dataclasses import dataclass, field

from epanet import toolkit as en

from app.hydraulic.messages import EngineMessage, parse_report, translate_exception
from app.schemas.network import (DemandCategory, HydraulicOptions, LineStringGeometry, LinkFeature,
                                 LinkProperties, NetworkFeatureCollection, NetworkModel, NodeFeature,
                                 NodeProperties, PointGeometry)
from app.services.geometry import from_metric, to_metric

PASSTHROUGH = {"TIMES", "PATTERNS", "CURVES", "CONTROLS", "RULES", "ENERGY", "QUALITY", "SOURCES",
               "REACTIONS", "MIXING", "LEAKAGE"}
VALVE_TYPES = {en.PRV: "PRV", en.PSV: "PSV", en.PBV: "PBV", en.FCV: "FCV", en.TCV: "TCV", en.GPV: "GPV",
               getattr(en, "PCV", 10): "PCV"}
HEADLOSS = {0: "H-W", 1: "D-W", 2: "C-M"}


class InpImportError(Exception):
    def __init__(self, messages: list[EngineMessage]):
        self.messages = messages
        super().__init__("; ".join(m.message for m in messages))


@dataclass
class ImportResult:
    model: NetworkModel
    georeference: str
    warnings: list[str] = field(default_factory=list)


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^\[(\w+)\]", s)
        if m:
            current = m.group(1).upper()
            sections.setdefault(current, [])
            continue
        if current and s and not s.startswith(";;"):
            sections[current].append(line.rstrip())
    return sections


def _id_or_none(getter, ph, index: int) -> str | None:
    if not index or index <= 0:
        return None
    return getter(ph, int(index))


def _detect_crs(xy: list[tuple[float, float]], length_srid: int,
                pairs: list[tuple[tuple[float, float], tuple[float, float], float]] | None = None) -> str:
    """UTM (rango de coordenadas métricas), lat/lon (rango geográfico y largos coherentes) o locales.

    `pairs` = (punto inicial, punto final, largo del tramo en m): con coordenadas geográficas la distancia
    geodésica entre extremos se parece al largo; con coordenadas locales chicas (p. ej. Net1) no.
    """
    if not xy:
        return "local"
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    if 100_000 <= min(xs) and max(xs) <= 900_000 and 1_000_000 <= min(ys) and max(ys) <= 10_000_000:
        return f"EPSG:{length_srid}"
    if -180 <= min(xs) and max(xs) <= 180 and -90 <= min(ys) and max(ys) <= 90 and pairs:
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
        ratios = []
        for (x1, y1), (x2, y2), length in pairs:
            if length and length > 0:
                _, _, d = geod.inv(x1, y1, x2, y2)
                ratios.append(d / length)
        if ratios and 0.3 <= statistics.median(ratios) <= 1.5:
            return "EPSG:4326"
    return "local"


def read_inp(path: str, *, crs: str = "auto", length_srid: int = 32719,
             origin: tuple[float, float] = (-70.6693, -33.4489)) -> ImportResult:
    """Lee un .inp y lo convierte al modelo de dominio en SI. `origin` = (lon, lat)."""
    from app.hydraulic.engine import engine_workdir

    path = os.path.abspath(path)
    with engine_workdir("trazo-import-") as tmp:
        rpt = os.path.join(tmp, "import.rpt")
        si_path = os.path.join(tmp, "si.inp")
        ph = en.createproject()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    en.open(ph, path, rpt, "")
                except Exception as exc:  # noqa: BLE001
                    msgs = parse_report(_read(rpt)) or [translate_exception(exc)]
                    raise InpImportError(msgs) from exc
            en.setflowunits(ph, en.LPS)
            en.setoption(ph, en.PRESS_UNITS, en.METERS)
            en.saveinpfile(ph, si_path)
            si_sections = split_sections(_read(si_path))
            model, raw_xy = _extract(ph, si_sections, _nodes_without_elevation(_read(path)))
        finally:
            try:
                en.close(ph)
            except Exception:  # noqa: BLE001
                pass
            en.deleteproject(ph)

    raw_sections = split_sections(_read(path))
    georef, notes, project = _georeference(model, raw_xy, crs, length_srid, origin)
    notes += _labels_and_tags(model, raw_sections, project)
    assumed = sorted(n.id for n in model.network.nodes() if n.properties.elevation_source == "supuesta")
    if assumed:
        shown = ", ".join(assumed[:10]) + ("…" if len(assumed) > 10 else "")
        notes.append(f"{len(assumed)} nudos sin cota en el archivo ({shown}): EPANET asume 0 m. "
                     "Quedan marcados como cota supuesta; ingrese la cota real.")
    return ImportResult(model=model, georeference=georef, warnings=notes)


def _read(path: str) -> str:
    try:
        with open(path, encoding="latin-1") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def _input_min_volume(vmin: float, tank: dict) -> float:
    """Volumen mínimo tal como se escribe en el .inp.

    Si el archivo trae 0 (sin volumen muerto), EPANET calcula internamente área·nivel mínimo y el
    toolkit devuelve ese valor. Se vuelve a 0, que es equivalente para el motor y conserva el dato.
    """
    if tank.get("volume_curve") or not tank.get("tank_diameter"):
        return vmin
    computed = math.pi / 4 * tank["tank_diameter"] ** 2 * tank["min_level"]
    return 0.0 if abs(vmin - computed) <= 1e-6 * max(1.0, computed) else vmin


def _nodes_without_elevation(text: str) -> set[str]:
    """Nudos de [JUNCTIONS] escritos sin la columna de cota (EPANET los acepta y asume 0 m)."""
    out = set()
    for line in split_sections(text).get("JUNCTIONS", []):
        data = line.split(";", 1)[0].split()
        if len(data) == 1:
            out.add(data[0])
    return out


def _extract(ph, si: dict[str, list[str]], no_elevation: set[str] | None = None):
    no_elevation = no_elevation or set()
    title_lines = [ln.strip() for ln in si.get("TITLE", []) if ln.strip()]
    hl = HEADLOSS.get(int(en.getoption(ph, en.HEADLOSSFORM)), "H-W")
    dm_type, pmin, preq, pexp = en.getdemandmodel(ph)

    extra: dict[str, str] = {}
    for line in si.get("OPTIONS", []):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        m = re.match(r"^([A-Za-z]+(?: [A-Za-z]+)*)\s+(.*)$", s)
        if not m:
            continue
        key, value = m.group(1).upper(), m.group(2).strip()
        extra[key] = value
    options = HydraulicOptions(headloss=hl, demand_model="PDA" if dm_type == en.PDA else "DDA",
                               minimum_pressure=float(pmin), required_pressure=float(preq),
                               pressure_exponent=float(pexp) if pexp > 0 else 0.5, extra=extra)

    si["CURVES"] = _precise_curves(ph, si.get("CURVES", []))
    si["CONTROLS"] = _precise_controls(ph, si.get("CONTROLS", []))
    aux = {name.lower(): "\n".join(lines) for name, lines in si.items() if name in PASSTHROUGH and lines}

    status_lines: dict[str, str] = {}
    for line in si.get("STATUS", []):
        parts = line.split()
        if len(parts) >= 2 and not parts[0].startswith(";"):
            status_lines[parts[0]] = parts[1].upper()

    raw_xy: dict[str, list[tuple[float, float]]] = {}
    nodes: list[NodeFeature] = []
    n_nodes = en.getcount(ph, en.NODECOUNT)
    for i in range(1, n_nodes + 1):
        nid = en.getnodeid(ph, i)
        ntype = en.getnodetype(ph, i)
        try:
            x, y = en.getcoord(ph, i)
            raw_xy[nid] = [(float(x), float(y))]
        except Exception:  # noqa: BLE001  (nudo sin coordenadas)
            raw_xy[nid] = []
        elev = float(en.getnodevalue(ph, i, en.ELEVATION))
        props: dict = {"uid": str(uuid.uuid4()), "elevation": elev, "elevation_source": "inp",
                       "elevation_method": "Importada desde archivo .inp"}
        if nid in no_elevation:
            props["elevation_source"] = "supuesta"
            props["elevation_method"] = "El archivo .inp no trae la cota y EPANET asume 0 m"
        if ntype == en.JUNCTION:
            props["kind"] = "junction"
            cats = []
            for k in range(1, en.getnumdemands(ph, i) + 1):
                cats.append(DemandCategory(
                    base=float(en.getbasedemand(ph, i, k)),
                    pattern=_id_or_none(en.getpatternid, ph, en.getdemandpattern(ph, i, k)),
                    name=(en.getdemandname(ph, i, k) or None),
                ))
            if cats:
                props["base_demand"], props["demand_pattern"] = cats[0].base, cats[0].pattern
                props["demands"] = cats[1:]
            emitter = float(en.getnodevalue(ph, i, en.EMITTER))
            props["emitter_coeff"] = emitter if emitter > 0 else None
        elif ntype == en.RESERVOIR:
            props["kind"] = "reservoir"
            props["head"] = elev
            props["head_pattern"] = _id_or_none(en.getpatternid, ph, en.getnodevalue(ph, i, en.PATTERN))
        else:
            props["kind"] = "tank"
            props["init_level"] = float(en.getnodevalue(ph, i, en.TANKLEVEL))
            props["min_level"] = float(en.getnodevalue(ph, i, en.MINLEVEL))
            props["max_level"] = float(en.getnodevalue(ph, i, en.MAXLEVEL))
            props["tank_diameter"] = float(en.getnodevalue(ph, i, en.TANKDIAM))
            props["volume_curve"] = _id_or_none(en.getcurveid, ph, en.getnodevalue(ph, i, en.VOLCURVE))
            props["min_volume"] = _input_min_volume(float(en.getnodevalue(ph, i, en.MINVOLUME)), props)
            props["can_overflow"] = bool(en.getnodevalue(ph, i, en.CANOVERFLOW))
        nodes.append(NodeFeature(id=nid, geometry=PointGeometry(coordinates=(0.0, 0.0)),
                                 properties=NodeProperties(**props)))

    links: list[LinkFeature] = []
    n_links = en.getcount(ph, en.LINKCOUNT)
    for i in range(1, n_links + 1):
        lid = en.getlinkid(ph, i)
        ltype = en.getlinktype(ph, i)
        n1, n2 = en.getlinknodes(ph, i)
        a, b = en.getnodeid(ph, n1), en.getnodeid(ph, n2)
        verts = []
        for k in range(1, en.getvertexcount(ph, i) + 1):
            vx, vy = en.getvertex(ph, i, k)
            verts.append((float(vx), float(vy)))
        raw_xy[f"\0link:{lid}"] = verts
        props = {"uid": str(uuid.uuid4()), "from_node": a, "to_node": b,
                 "minor_loss": float(en.getlinkvalue(ph, i, en.MINORLOSS))}
        init_status = int(en.getlinkvalue(ph, i, en.INITSTATUS))
        if ltype in (en.PIPE, en.CVPIPE):
            length = float(en.getlinkvalue(ph, i, en.LENGTH))
            props.update(kind="pipe", inner_diameter_mm=float(en.getlinkvalue(ph, i, en.DIAMETER)),
                         roughness=float(en.getlinkvalue(ph, i, en.ROUGHNESS)),
                         length_hydraulic_m=length, length_choice="manual", material=None,
                         initial_status="cv" if ltype == en.CVPIPE else ("open" if init_status else "closed"))
        elif ltype == en.PUMP:
            curve = int(en.getlinkvalue(ph, i, en.PUMP_HCURVE))
            power = float(en.getlinkvalue(ph, i, en.PUMP_POWER))
            props.update(kind="pump", pump_curve=_id_or_none(en.getcurveid, ph, curve),
                         pump_power=power if power > 0 and not curve else None,
                         pump_speed=float(en.getlinkvalue(ph, i, en.INITSETTING)),
                         pump_pattern=_id_or_none(en.getpatternid, ph, en.getlinkvalue(ph, i, en.LINKPATTERN)),
                         initial_status="closed" if status_lines.get(lid) == "CLOSED" else "open")
        else:
            vtype = VALVE_TYPES.get(ltype, "TCV")
            setting = float(en.getlinkvalue(ph, i, en.INITSETTING))
            st = status_lines.get(lid)
            props.update(kind="valve", valve_type=vtype, inner_diameter_mm=float(en.getlinkvalue(ph, i, en.DIAMETER)),
                         valve_setting=None if vtype == "GPV" else setting,
                         valve_curve=_id_or_none(en.getcurveid, ph, setting) if vtype == "GPV" else None,
                         initial_status={"OPEN": "open", "CLOSED": "closed"}.get(st or "", "active"))
        links.append(LinkFeature(id=lid, geometry=LineStringGeometry(coordinates=[(0.0, 0.0), (0.0, 0.0)]),
                                 properties=LinkProperties(**props)))

    model = NetworkModel(title="\n".join(title_lines), options=options, aux=aux,
                         network=NetworkFeatureCollection(features=[*nodes, *links]))
    return model, raw_xy


def _num(x: float) -> str:
    return f"{float(x):.12g}"


def _precise_curves(ph, lines: list[str]) -> list[str]:
    """Reemplaza los valores X/Y de [CURVES] (4 decimales en el .inp SI) por los de doble precisión del toolkit."""
    points: dict[str, list[tuple[float, float]]] = {}
    for c in range(1, en.getcount(ph, en.CURVECOUNT) + 1):
        cid = en.getcurveid(ph, c)
        points[cid] = [tuple(en.getcurvevalue(ph, c, k)) for k in range(1, en.getcurvelen(ph, c) + 1)]
    used: dict[str, int] = {}
    out = []
    for line in lines:
        toks = line.split()
        if line.strip().startswith(";") or len(toks) < 3 or toks[0] not in points:
            out.append(line)
            continue
        k = used.get(toks[0], 0)
        used[toks[0]] = k + 1
        if k < len(points[toks[0]]):
            x, y = points[toks[0]][k]
            toks[1], toks[2] = _num(x), _num(y)
        out.append(" " + "\t".join(toks))
    return out


def _precise_controls(ph, lines: list[str]) -> list[str]:
    """Reemplaza consigna y nivel de cada control simple por los valores de doble precisión del toolkit."""
    data = [en.getcontrol(ph, i) for i in range(1, en.getcount(ph, en.CONTROLCOUNT) + 1)]
    out, k = [], 0
    for line in lines:
        s = line.strip()
        if not s or s.startswith(";") or not s.upper().startswith("LINK"):
            out.append(line)
            continue
        if k < len(data):
            ctype, _link, setting, _node, level = data[k]
            toks = s.split()
            if len(toks) > 2 and re.match(r"^-?[\d.]+$", toks[2]):
                toks[2] = _num(setting)
            up = [t.upper() for t in toks]
            for kw in ("ABOVE", "BELOW"):
                if kw in up and up.index(kw) + 1 < len(toks):
                    toks[up.index(kw) + 1] = _num(level)
            line = " " + " ".join(toks)
        k += 1
        out.append(line)
    return out


def _georeference(model: NetworkModel, raw_xy: dict, crs: str, length_srid: int,
                  origin: tuple[float, float]):
    notes: list[str] = []
    nodes = model.network.nodes()
    links = model.network.links()
    node_xy = {n.id: raw_xy[n.id][0] for n in nodes if raw_xy.get(n.id)}

    missing = [n.id for n in nodes if n.id not in node_xy]
    if missing:
        # Nudos sin coordenadas: se ubican en una grilla al costado de la red.
        xs = [p[0] for p in node_xy.values()] or [0.0]
        ys = [p[1] for p in node_xy.values()] or [0.0]
        step = max((max(xs) - min(xs)) / 20, (max(ys) - min(ys)) / 20, 10.0)
        for k, nid in enumerate(missing):
            node_xy[nid] = (max(xs) + step * (2 + k % 10), min(ys) + step * (k // 10))
        notes.append(f"{len(missing)} nudos sin coordenadas se ubicaron en una grilla auxiliar.")

    all_xy = list(node_xy.values()) + [v for lk in links for v in raw_xy.get(f"\0link:{lk.id}", [])]
    pairs = []
    for lk in links:
        p = lk.properties
        if p.kind == "pipe" and p.from_node in node_xy and p.to_node in node_xy:
            pts = [node_xy[p.from_node], *raw_xy.get(f"\0link:{lk.id}", []), node_xy[p.to_node]]
            for k in range(len(pts) - 1):
                pairs.append((pts[k], pts[k + 1], (p.length_hydraulic_m or 0) / (len(pts) - 1)))
    mode = _detect_crs(all_xy, length_srid, pairs) if crs == "auto" else crs

    if mode.upper().startswith("EPSG:"):
        srid = int(mode.split(":")[1])
        if srid == 4326:
            def project(x: float, y: float) -> tuple[float, float]:
                return (x, y)
        else:
            tr = from_metric(srid)

            def project(x: float, y: float) -> tuple[float, float]:
                lon, lat = tr.transform(x, y)
                return (lon, lat)
        georef = f"EPSG:{srid}"
    else:
        # Coordenadas locales: se escalan para que la distancia en planta se parezca al largo del .inp
        # y se ubican alrededor del origen configurado.
        ratios = []
        for lk in links:
            p = lk.properties
            if p.kind != "pipe" or not p.length_hydraulic_m:
                continue
            pts = [node_xy[p.from_node], *raw_xy.get(f"\0link:{lk.id}", []), node_xy[p.to_node]]
            d = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
            if d > 0:
                ratios.append(p.length_hydraulic_m / d)
        scale = statistics.median(ratios) if ratios else 1.0
        xs = [p[0] for p in all_xy]
        ys = [p[1] for p in all_xy]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        ox, oy = to_metric(length_srid).transform(*origin)
        tr = from_metric(length_srid)

        def project(x: float, y: float) -> tuple[float, float]:
            lon, lat = tr.transform(ox + (x - cx) * scale, oy + (y - cy) * scale)
            return (lon, lat)
        georef = "local"
        notes.append(f"Coordenadas locales escaladas (factor {scale:.3f}) y ubicadas en el origen configurado.")

    for n in nodes:
        n.geometry = PointGeometry(coordinates=project(*node_xy[n.id]))
    for lk in links:
        p = lk.properties
        pts = [node_xy[p.from_node], *raw_xy.get(f"\0link:{lk.id}", []), node_xy[p.to_node]]
        lk.geometry = LineStringGeometry(coordinates=[project(x, y) for x, y in pts])
    return georef, notes, project


def _labels_and_tags(model: NetworkModel, sections: dict[str, list[str]], project) -> list[str]:
    """Conserva [TAGS] (atributo reservado «__tag») y [LABELS] (aux «labels», en EPSG:4326)."""
    import shlex

    from app.hydraulic.inp_writer import TAG_KEY

    notes = []
    nodes = {n.id: n for n in model.network.nodes()}
    links = {lk.id: lk for lk in model.network.links()}
    count = 0
    for line in sections.get("TAGS", []):
        toks = line.split(";")[0].split()
        if len(toks) >= 3:
            pool = nodes if toks[0].upper() == "NODE" else links if toks[0].upper() == "LINK" else {}
            f = pool.get(toks[1])
            if f is not None:
                f.properties.attributes = {**f.properties.attributes, TAG_KEY: " ".join(toks[2:])}
                count += 1
    labels = []
    for line in sections.get("LABELS", []):
        body = line.split(";")[0].strip()
        try:
            toks = shlex.split(body)
        except ValueError:
            continue
        if len(toks) < 3:
            continue
        try:
            lon, lat = project(float(toks[0]), float(toks[1]))
        except ValueError:
            continue
        text = toks[2].replace('"', "'")
        anchor = f" {toks[3]}" if len(toks) > 3 else ""
        labels.append(f'{lon!r} {lat!r} "{text}"{anchor}')
    if labels:
        model.aux["labels"] = "\n".join(labels)
    if count or labels:
        notes.append(f"Se conservaron {count} etiquetas [TAGS] y {len(labels)} rótulos [LABELS].")
    return notes
