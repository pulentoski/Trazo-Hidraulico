"""Genera examples/apr-ejemplo-valle-elqui.trazo: «APR Ejemplo Valle de Elqui», proyecto de ejemplo completo.

APR rural ficticio en el valle de Elqui (Región de Coquimbo, sector de Diaguitas), en EPSG:32719, con cotas
aproximadas del valle: el terreno sube hacia el oriente (aguas arriba) y hacia el sur (ladera); el pozo está junto
al río y el estanque elevado de 150 m³ en la ladera. Tres sectores con macromedidor a la salida del estanque:
Centro (pueblo, escuela y posta), La Vega (aguas abajo, red de PVC antigua con fugas) y El Arrayán (loma, presión
baja en verano). Unos 180 clientes, 3 rutas de lectura, ~6 km de red, 8 llaves (cuarteles de corta), 3 grifos.

Incluye 24 meses de registros hasta el mes de corte (lecturas de clientes con altas y bajas, medidor del pozo y de
los macromedidores, energía, cloro, fugas y reparaciones, cortes, reclamos, mantenciones con algunas atrasadas,
presiones y niveles, factibilidades), parámetros de demanda, curva horaria, horario de bomba, criterios de diseño
(«no verificado»), derecho de agua y metas. Todo es ficticio y determinista (semilla fija).

Se ejecuta dentro de la imagen de la API, con la base de datos arriba (crea el proyecto en una organización
temporal, lo exporta y lo borra). Escribe el .trazo en la salida estándar; los avisos van a stderr:

    docker compose --env-file .env -f infra/compose.yml exec -T api python - --hasta 2026-11-12 \
        < scripts/generar_apr_ejemplo.py > examples/apr-ejemplo-valle-elqui.trazo

o simplemente `make ejemplo` (copia también el archivo a frontend/public/ejemplos/ para «Cargar proyecto de ejemplo»).
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

SEED = 20261112
NAME = "APR Ejemplo Valle de Elqui"
SRID = 32719
ORIGIN_LON, ORIGIN_LAT = -70.6420, -30.0120  # sector de Diaguitas, valle de Elqui (aprox.)
TZ = timezone(timedelta(hours=-3))  # hora de Chile (verano); basta para registros de ejemplo
SECTORS = ("Centro", "La Vega", "El Arrayán")
ROUTE = {"Centro": "1", "La Vega": "2", "El Arrayán": "3"}
STAFF = {"op": "Luis Ardiles (operador)", "elec": "Técnico eléctrico", "dir": "Directiva APR", "cont": "Contratista"}

# Curva horaria normalizada (promedio 1): consumo rural con punta de mañana y de tarde.
CURVA = [0.35, 0.25, 0.2, 0.2, 0.3, 0.55, 0.95, 1.45, 1.6, 1.5, 1.4, 1.35, 1.4, 1.35, 1.25, 1.1, 1.05, 1.1, 1.3,
         1.45, 1.4, 1.15, 0.85, 0.55]
MOD = [round(c / (sum(CURVA) / 24), 4) for c in CURVA]
# Estacionalidad del consumo: alta de diciembre a marzo (riego de patios, turismo), baja en invierno.
SEASON = {1: 1.30, 2: 1.28, 3: 1.15, 4: 0.98, 5: 0.88, 6: 0.80, 7: 0.78, 8: 0.82, 9: 0.90, 10: 1.00, 11: 1.10, 12: 1.24}
PUMP_LPS, PUMP_KW = 7.5, 11.8  # caudal de la bomba en el punto de operación y potencia eléctrica medida

R = random.Random(SEED)
# Puntos con registrador: presión con consumo bajo (m) y caída en la punta (coeficiente sobre el caudal relativo).
PRESSURE_POINTS = {"J-C07": (46.0, 1.2), "J-V05": (58.0, 1.5), "J-A09": (18.0, 1.9)}


def log(*a) -> None:
    print(*a, file=sys.stderr)


# ── Terreno y red ──

def ground(x: float, y: float) -> float:
    """Cota aproximada (m s.n.m.): ~698 m en la plaza, sube 1 % al oriente y 4,5 % hacia la ladera sur."""
    return round(698.0 + 0.010 * x - 0.045 * y + 0.6 * math.sin(x / 140.0) * math.cos(y / 170.0), 2)


NODES: dict[str, tuple[float, float]] = {}  # ID → (x, y) locales en metros (este, norte)
SECTOR_OF: dict[str, str] = {}
PIPES: list[tuple] = []  # (ID, desde, hasta, material, DN, clase, año, estado, tipo, vértices, sector del macro)


def _grid() -> None:
    for j, y in enumerate((0, 110, 220)):  # Centro: 4 × 3 cuadras
        for i, x in enumerate((0, 110, 220, 330)):
            nid = f"J-C{j * 4 + i + 1:02d}"
            NODES[nid], SECTOR_OF[nid] = (x, y), "Centro"
    vega = {"J-V01": (-120, 200), "J-V02": (-230, 200), "J-V03": (-340, 200), "J-V04": (-450, 200),
            "J-V05": (-560, 200), "J-V06": (-230, 310), "J-V07": (-450, 310), "J-V08": (-560, 90), "J-V09": (-340, 90)}
    alto = {}
    for j, y in enumerate((-200, -310, -420)):
        for i, x in enumerate((560, 670, 780)):
            alto[f"J-A{j * 3 + i + 1:02d}"] = (x, y)
    for d, sec in ((vega, "La Vega"), (alto, "El Arrayán")):
        for k, v in d.items():
            NODES[k], SECTOR_OF[k] = v, sec
    NODES["J-IMP"], NODES["J-TR"] = (-55, 305), (420, -380)  # nudo de impulsión y derivación bajo el estanque
    NODES["J-VE"] = (120, -60)  # entrada de La Vega por el camino interior


def _pipes() -> None:
    def add(pid, a, b, mat, dn, year, cond, ntype, verts=(), macro=None, cls=None):
        PIPES.append((pid, a, b, mat, dn, cls or ("PN10" if mat == "HDPE" else "C10"), year, cond, ntype, list(verts), macro))

    add("P-IMP", "J-IMP", "E-1", "HDPE", 110, 2012, "bueno", "impulsion", [(10, 180), (230, -120), (380, -470)])
    add("P-TR", "E-1", "J-TR", "PVC", 160, 2012, "bueno", "aduccion")
    add("P-CEN", "J-TR", "J-C04", "PVC", 125, 2012, "bueno", "matriz", [(360, -180)], macro="Centro")
    add("P-ALT", "J-TR", "J-A01", "PVC", 90, 2016, "bueno", "matriz", [(500, -300)], macro="El Arrayán")
    add("P-VEG", "J-TR", "J-VE", "PVC", 110, 1998, "regular", "matriz", [(260, -250)], macro="La Vega")
    add("P-VE1", "J-VE", "J-V01", "PVC", 110, 1998, "regular", "matriz", [(-60, 40), (-100, 150)])
    # Centro: cuadrícula (calles norte-sur y oriente-poniente)
    n = 1
    for j in range(3):
        for i in range(3):
            a, b = f"J-C{j * 4 + i + 1:02d}", f"J-C{j * 4 + i + 2:02d}"
            year, cond = (2003, "bueno") if j < 2 else (1994, "regular")
            add(f"P-C{n:02d}", a, b, "PVC", 110 if j == 0 else 90 if j == 1 else 75, year, cond, "distribucion")
            n += 1
    for j in range(2):
        for i in range(4):
            a, b = f"J-C{j * 4 + i + 1:02d}", f"J-C{(j + 1) * 4 + i + 1:02d}"
            year, cond = (2003, "bueno") if i % 2 else (1994, "regular")
            add(f"P-C{n:02d}", a, b, "PVC", 75 if i < 3 else 63, year, cond, "distribucion")
            n += 1
    # La Vega: PVC antiguo (1984–1990), con los tramos en mal estado donde se concentran las fugas
    vega = [("P-V01", "J-V01", "J-V02", 90, 1984, "malo"), ("P-V02", "J-V02", "J-V03", 90, 1984, "malo"),
            ("P-V03", "J-V03", "J-V04", 75, 1986, "regular"), ("P-V04", "J-V04", "J-V05", 63, 1986, "malo"),
            ("P-V05", "J-V02", "J-V06", 63, 1990, "regular"), ("P-V06", "J-V04", "J-V07", 63, 1990, "regular"),
            ("P-V07", "J-V05", "J-V08", 63, 1984, "malo"), ("P-V08", "J-V03", "J-V09", 63, 1990, "regular")]
    for pid, a, b, dn, year, cond in vega:
        add(pid, a, b, "PVC", dn, year, cond, "distribucion")
    # El Arrayán: loteo de 2016 en HDPE
    alto = [("P-A01", "J-A01", "J-A02"), ("P-A02", "J-A02", "J-A03"), ("P-A03", "J-A02", "J-A05"),
            ("P-A04", "J-A04", "J-A05"), ("P-A05", "J-A05", "J-A06"), ("P-A06", "J-A05", "J-A08"),
            ("P-A07", "J-A07", "J-A08"), ("P-A08", "J-A08", "J-A09")]
    for k, (pid, a, b) in enumerate(alto):
        add(pid, a, b, "HDPE", 75 if k < 3 else 63, 2016, "bueno", "distribucion")
    # Interconexiones entre sectores: normalmente cerradas (límites de sector con llave)
    add("P-X01", "J-C05", "J-V01", "PVC", 75, 2003, "bueno", "distribucion")
    add("P-X02", "J-C04", "J-A04", "PVC", 63, 2016, "bueno", "distribucion", [(450, -120)])


VALVES = [  # ID, tramo, posición, estado, tipo, DN, profundidad, nombre
    ("V-01", "P-CEN", 0.1, "open", "compuerta", 125, 1.2, "Salida al Centro"),
    ("V-02", "P-ALT", 0.1, "open", "compuerta", 90, 1.1, "Salida a El Arrayán"),
    ("V-03", "P-VEG", 0.1, "open", "compuerta", 110, 1.2, "Salida a La Vega"),
    ("V-04", "P-C09", 0.5, "open", "compuerta", 75, 1.0, "Calle Gabriela Mistral"),
    ("V-05", "P-V02", 0.3, "open", "compuerta", 90, 1.0, "Camino La Vega"),
    ("V-06", "P-A03", 0.3, "open", "compuerta", 75, 1.1, "Pasaje Los Algarrobos"),
    ("V-07", "P-X01", 0.5, "closed", "compuerta", 75, 1.0, "Interconexión Centro–La Vega (cerrada)"),
    ("V-08", "P-X02", 0.5, "closed", "compuerta", 63, 1.0, "Interconexión Centro–El Arrayán (cerrada)"),
]
HYDRANTS = [("G-01", "J-C06", "Frente a la escuela"), ("G-02", "J-V03", "Sede social La Vega"),
            ("G-03", "J-A05", "Plaza El Arrayán")]
STREETS = {"Centro": ["Gabriela Mistral", "Arturo Prat", "Los Pimientos", "Balmaceda"],
           "La Vega": ["Camino La Vega", "Pasaje El Molle", "Los Sauces"],
           "El Arrayán": ["Los Algarrobos", "Las Chilcas", "Pasaje El Arrayán"]}
SURNAMES = ["Rojas", "Araya", "Castillo", "Cortés", "González", "Muñoz", "Pizarro", "Alfaro", "Rivera", "Olivares",
            "Tapia", "Contreras", "Díaz", "Vega", "Carvajal", "Ramírez", "Flores", "Gallardo", "Campillay", "Ogalde",
            "Varela", "Zepeda", "Aguirre", "Barraza", "Galleguillos", "Cáceres", "Torres", "Ahumada"]
SPECIAL = [  # nombre, tipo, nudo, m³/mes
    ("Escuela Básica Diaguitas", "publico", "J-C06", 165.0), ("Posta de Salud Rural", "publico", "J-C07", 48.0),
    ("Almacén Don Pato", "comercial", "J-C02", 28.0), ("Restaurante El Parrón", "comercial", "J-C03", 62.0),
    ("Cabañas Valle Mágico", "comercial", "J-A06", 85.0), ("Pisquera artesanal", "comercial", "J-V06", 70.0),
    ("Sede social La Vega", "publico", "J-V03", 12.0), ("Iglesia San Isidro", "publico", "J-C10", 9.0),
]


def build_clients() -> list[dict]:
    """~180 clientes: 172 residenciales y 8 comerciales o públicos, repartidos por nudo según el sector."""
    per = {"Centro": 82, "La Vega": 52, "El Arrayán": 38}
    out: list[dict] = []
    k = 0
    for sec, n in per.items():
        nodes = [i for i, s in SECTOR_OF.items() if s == sec]
        for j in range(n):
            node = nodes[j % len(nodes)]
            k += 1
            out.append({"node": node, "sector": sec, "type": "residencial", "name": f"Familia {R.choice(SURNAMES)}",
                        "base": round(R.uniform(11.0, 21.0) * (1.15 if sec == "El Arrayán" else 1.0), 1)})
    for name, ctype, node, m3 in SPECIAL:
        out.append({"node": node, "sector": SECTOR_OF[node], "type": ctype, "name": name, "base": m3})
    seen: dict[str, int] = {}
    for i, c in enumerate(out, start=1):
        c["id"] = f"CL-{i:03d}"
        c["number"] = str(2000 + i)
        n = seen[c["node"]] = seen.get(c["node"], 0) + 1
        x, y = NODES[c["node"]]
        ang = n * 2.399963  # ángulo áureo: los arranques no se pisan
        c["x"], c["y"] = x + (14 + 4 * (n % 4)) * math.cos(ang), y + (14 + 4 * (n % 4)) * math.sin(ang)
        c["street"] = STREETS[c["sector"]][n % len(STREETS[c["sector"]])]
        c["address"] = f"{c['street']} {100 + 7 * n}"
        c["route"] = ROUTE[c["sector"]]
        c["status"] = "activo"
        c["start"], c["end"] = None, None
    return out


# ── Registros ──

def months_until(cut: date, n: int = 24) -> list[tuple[int, int]]:
    y, m = cut.year, cut.month
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def ym(t: tuple[int, int]) -> str:
    return f"{t[0]:04d}-{t[1]:02d}"


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def dt(d: date, h: int, mi: int = 0) -> datetime:
    return datetime.combine(d, time(h, mi), tzinfo=TZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasta", default=(date.today() - timedelta(days=1)).isoformat(),
                    help="Último día con registros diarios (AAAA-MM-DD). El mes de corte es el «mes actual».")
    args = ap.parse_args()
    cut = date.fromisoformat(args.hasta)
    months = months_until(cut)
    first = date(months[0][0], months[0][1], 1)
    billed = [t for t in months if (t[0], t[1]) < (cut.year, cut.month)]  # el mes en curso aún no se factura
    log(f"Generando «{NAME}»: {ym(months[0])} a {ym(months[-1])}, datos diarios hasta {cut}.")

    _grid()
    _pipes()
    clients = build_clients()

    from pyproj import Transformer

    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{SRID}", always_xy=True)
    to_geo = Transformer.from_crs(f"EPSG:{SRID}", "EPSG:4326", always_xy=True)
    e0, n0 = to_utm.transform(ORIGIN_LON, ORIGIN_LAT)

    def geo(x: float, y: float) -> dict:
        lon, lat = to_geo.transform(e0 + x, n0 + y)
        return {"_lat": round(lat, 8), "_lon": round(lon, 8)}

    # Altas, bajas y loteo proyectado: algunos clientes entran durante el período y otros se dan de baja.
    res = [c for c in clients if c["type"] == "residencial"]
    for c in R.sample(res, 9):
        c["start"] = months[R.randint(4, 21)]
    for c in R.sample([c for c in res if c["start"] is None], 4):
        c["end"] = months[R.randint(8, 20)]
        c["status"] = "suspendido"
    proj = [c for c in res if c["sector"] == "El Arrayán" and c["start"] is None and c["end"] is None][-3:]
    for c in proj:
        c["status"] = "proyectado"

    rows = network_rows(geo, clients)
    meas, leaks, monthly = measurements_and_leaks(months, cut, clients)
    wb_bytes = workbook(rows, meas, leaks)

    from app.core.db import get_sessionmaker
    from app.models import Organization, Project
    from app.services import auth, sig_io

    Session = get_sessionmaker()
    with Session() as session:
        org = Organization(id=uuid.uuid4(), name=f"Generador de ejemplo {uuid.uuid4().hex[:6]}", plan="ilimitado")
        session.add(org)
        session.commit()
        principal = auth.Principal(user_id=None, email="generador@ejemplo.local", org_id=org.id,
                                   roles={org.id: "admin"}, need="edit")
        tok = auth.current.set(principal)
        try:
            r = sig_io.create_from_excel(session, "apr-ejemplo.xlsx", wb_bytes, name=NAME, zone=19, hemisphere="S")
            if not r.created:
                errs = [e for e in r.preview.errors][:10] if hasattr(r.preview, "errors") else r.preview
                raise SystemExit(f"La planilla no se pudo importar: {errs}")
            for nt in r.preview.notes:
                log("  ·", nt)
            project = session.get(Project, uuid.UUID(r.project_id))
            project.description = ("Proyecto de ejemplo con datos ficticios: APR rural del valle de Elqui con 24 meses de "
                                   "registros de gestión. Generado por scripts/generar_apr_ejemplo.py (semilla fija).")
            configure(session, project, clients)
            records(session, project, months, billed, cut, clients, leaks, monthly)
            feasibilities(session, project, geo, months)
            session.commit()
            check(session, project)
            from app.services import trazo

            data, _ = trazo.export(session, project, None, include_orthos=False)
            session.delete(project)
            session.commit()
        finally:
            auth.current.reset(tok)
            session.rollback()
            o = session.get(Organization, org.id)
            if o is not None:
                session.delete(o)
                session.commit()
    sys.stdout.buffer.write(data)
    log(f"Listo: {len(data) / 1024:.0f} KB.")


def network_rows(geo, clients) -> dict:
    from app.sig.tables import Row

    out: dict[str, list] = {}
    out["nudos"] = [Row(i, {**geo(x, y), "elevation": ground(x, y), "base_demand": 0.0, "demand_pattern": None,
                            "description": {"J-IMP": "Nudo de impulsión (salida del pozo)",
                                            "J-TR": "Derivación de sectores bajo el estanque",
                                            "J-VE": "Entrada a La Vega por el camino interior"}.get(i)},
                        {"Sector": SECTOR_OF[i]} if i in SECTOR_OF else {})
                    for i, (x, y) in NODES.items()]
    tx, ty = 470, -520
    out["estanques"] = [Row("E-1", {**geo(tx, ty), "elevation": round(ground(tx, ty) + 10.0, 2), "init_level": 2.6,
                                    "min_level": 0.3, "max_level": 3.9, "tank_diameter": 7.1, "min_volume": None,
                                    "volume_curve": None, "can_overflow": False,
                                    "description": "Estanque elevado de 150 m³ en la ladera (torre de 10 m)"})]
    wx, wy = -60, 330
    out["reservorios"] = [Row("R-POZO", {**geo(wx, wy), "elevation": None, "head": None, "head_pattern": None,
                                         "description": "Nivel dinámico del pozo"})]
    out["pozos"] = [Row("PZ-1", {**geo(wx, wy), "node": "R-POZO", "ground_elevation": ground(wx, wy), "depth_m": 60.0,
                                 "static_level_m": 11.0, "dynamic_level_m": 19.5, "authorized_flow_lps": 4.0,
                                 "condition": "bueno", "description": "Pozo profundo junto al río Elqui (sondaje 2011)"},
                        {"Derecho DGA": "ND-0402-0815 (ficticio)", "Sector": "Total"})]
    out["bombas"] = [Row("B-1", {"from_node": "R-POZO", "to_node": "J-IMP", "_vertices": None, "pump_curve": None,
                                 "pump_power": None, "pump_speed": 1.0, "pump_pattern": None, "initial_status": "open",
                                 "_curve": "0 132; 7.5 100; 11 72",
                                 # Fuera del horario punta (18 a 22 h); control por nivel del estanque.
                                 "_schedule": "0-17; 23", "_lc_tank": "E-1", "_lc_on": 1.6, "_lc_off": 3.7,
                                 "description": "Bomba sumergible 15 HP (curva de catálogo, 3 puntos)"})]
    tramos = []
    for pid, a, b, mat, dn, cls, year, cond, ntype, verts, macro in PIPES:
        vtxt = "; ".join("{_lat!r} {_lon!r}".format(**geo(x, y)) for x, y in verts) or None
        attrs = {"Sector": macro} if macro else {}
        if macro:
            attrs["Macromedidor"] = f"MM-{pid[2:]}"
        tramos.append(Row(pid, {"from_node": a, "to_node": b, "_vertices": vtxt, "dn": dn, "inner_diameter_mm": None,
                                "material": mat, "pipe_class": cls, "roughness": None, "minor_loss": 0.0,
                                "initial_status": "open", "length_choice": "slope", "_length_manual": None,
                                "condition": cond, "install_year": year, "network_type": ntype,
                                "description": "Macromedidor del sector" if macro else None}, attrs))
    out["tramos"] = tramos
    out["valvulas"] = [Row(v, {"_class": "corte", "_type": t, "_state": st, "condition": "regular" if v == "V-05" else "bueno",
                               "_diameter": d, "_depth": dep, "link": lk, "position": p, "name": nm})
                       for v, lk, p, st, t, d, dep, nm in VALVES]
    out["grifos"] = []
    for g, node, desc in HYDRANTS:
        x, y = NODES[node]
        out["grifos"].append(Row(g, {**geo(x + 6, y + 5), "node": node, "hydrant_type": "columna",
                                     "condition": "malo" if g == "G-02" else "bueno", "diameter_mm": 100.0,
                                     "fire_flow_lps": 16.0, "min_pressure_m": 5.0, "description": desc}))
    out["clientes"] = [Row(c["id"], {
        **geo(c["x"], c["y"]), "client_number": c["number"], "name": c["name"], "address": c["address"],
        "route": c["route"], "meter_number": f"MED-{5100 + int(c['number']) - 2000}", "client_type": c["type"],
        "status": c["status"], "consumption_value": c["base"], "consumption_unit": "m3/mes", "node": c["node"],
        "link": None, "elevation": ground(c["x"], c["y"])},
        {"Sector": c["sector"], "Viviendas": 1 if c["type"] == "residencial" else 0}) for c in clients]
    return out


def measurements_and_leaks(months, cut, clients):
    """Lecturas acumuladas del pozo y los macromedidores (con agua no contabilizada según las fugas), presiones,
    niveles y el registro de fugas, roturas y reparaciones (concentradas en los tramos antiguos de La Vega)."""
    first = date(months[0][0], months[0][1], 1)
    # Fugas: mayormente en La Vega (PVC 1984–1990) y en verano; 2 meses con varias roturas.
    old = ["P-V01", "P-V02", "P-V04", "P-V07", "P-V03", "P-VE1", "P-C11", "P-C13", "P-A06"]
    weights = [6, 5, 5, 4, 2, 2, 2, 3, 1]
    leaks = []
    for (y, m) in months:
        n = R.choice([0, 1, 1, 2]) + (1 if m in (1, 2, 12) else 0)
        if (y, m) == months[13]:
            n += 3  # el mes «malo»: varias roturas seguidas en La Vega
        for _ in range(n):
            last = (cut.day if (y, m) == (cut.year, cut.month) else 28)
            d = date(y, m, R.randint(1, max(1, last - 1)))
            link = R.choices(old, weights)[0]
            kind = "rotura" if R.random() < 0.3 else "fuga"
            q = round(R.uniform(0.25, 0.6) if kind == "rotura" else R.uniform(0.03, 0.15), 2)
            leaks.append((d, link, kind, q, R.choice(["Afloramiento en la vereda", "Filtración en unión",
                                                      "Rotura por tránsito de camión", "Fuga en arranque",
                                                      "Aviso de vecinos"])))
            rep = d + timedelta(days=R.choice([0, 1, 1, 2, 4]))
            if rep <= cut:
                leaks.append((rep, link, "reparacion", None, R.choice(["Cambio de copla", "Abrazadera de reparación",
                                                                         "Reemplazo de 6 m de tubería"])))
    # El Arrayán: arranques dañados dos veces por la maquinaria del loteo vecino (tramo crítico del sector).
    for t, day in ((months[-5], 9), (months[-3], 21)):
        d = date(t[0], t[1], day)
        leaks += [(d, "P-A06", "fuga", 0.08, "Arranque dañado por maquinaria del loteo"),
                  (d + timedelta(days=1), "P-A06", "reparacion", None, "Cambio de collar de arranque")]
    leaks.sort()
    # Pérdidas físicas por mes y sector: base + fugas activas del mes.
    leak_by = {}
    for d, link, kind, q, _ in leaks:
        if kind == "reparacion":
            continue
        sec = "La Vega" if link.startswith("P-V") else "El Arrayán" if link.startswith("P-A") else "Centro"
        leak_by[(ym((d.year, d.month)), sec)] = leak_by.get((ym((d.year, d.month)), sec), 0) + (3 if kind == "rotura" else 1)
    # Consumo diario por sector (m³) según los clientes activos ese mes y la temporada.
    def active(c, t):
        return c["status"] != "proyectado" and (c["start"] is None or t >= c["start"]) and (c["end"] is None or t < c["end"])
    monthly = {}  # (mes, sector) → consumo facturado (m³)
    for t in months:
        for sec in SECTORS:
            monthly[(ym(t), sec)] = sum(c["base"] for c in clients if c["sector"] == sec and active(c, t)) * SEASON[t[1]]
    base_nrw = {"Centro": 0.15, "La Vega": 0.22, "El Arrayán": 0.12}
    meas = []
    acc = {"PZ-1": 812450.0, "P-CEN": 214380.0, "P-VEG": 156210.0, "P-ALT": 61840.0}
    macro_of = {"Centro": "P-CEN", "La Vega": "P-VEG", "El Arrayán": "P-ALT"}
    nrw_month = {}
    # Medidores de producción: lectura diaria hasta el 1 del mes en curso (cierra el último mes facturado): así el
    # agua no contabilizada compara meses completos de producción y de consumo.
    for k, d in enumerate(days(first, date(cut.year, cut.month, 1))):
        mk = ym((d.year, d.month))
        dim = (date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)).day
        t8 = f"{d.isoformat()} 00:00"
        meas.append(["pozo", "PZ-1", "medidor", t8, round(acc["PZ-1"], 1), "Lectura inicial" if k == 0 else None])
        for sec, pid in macro_of.items():
            meas.append(["tramo", pid, "medidor", t8, round(acc[pid], 1), f"Macromedidor {sec}" if k == 0 else None])
        total = 0.0
        for sec in SECTORS:
            loss = min(0.36, base_nrw[sec] + 0.035 * leak_by.get((mk, sec), 0))
            nrw_month[(mk, sec)] = loss
            v = monthly[(mk, sec)] / dim / (1 - loss) * (1 + 0.05 * math.sin(k * 1.7) + (0.06 if d.weekday() >= 5 else -0.02))
            acc[macro_of[sec]] += v
            total += v
        acc["PZ-1"] += total * 1.012  # lavado de filtros y purgas a la salida del pozo
    # Presión y nivel horarios: 3 días por mes con registrador portátil (El Arrayán baja en verano)
    pts = PRESSURE_POINTS
    for (y, m) in months:
        for day in (6, 16, 26):
            dd = date(y, m, day)
            if dd > cut:
                continue
            for h in range(24):
                q = MOD[h] * SEASON[m]
                kk = y * 1000 + m * 40 + day + h
                wav = math.sin(kk * 12.9898) * 0.6 + math.sin(kk * 4.1414) * 0.4
                for node, (p0, kq) in pts.items():
                    drop = kq * q ** 1.6
                    meas.append(["nudo", node, "presión", f"{dd.isoformat()} {h:02d}:00", round(p0 - drop + 0.4 * wav, 2), None])
                level = 2.6 + 0.9 * math.cos((h - 5) / 24 * 2 * math.pi) - 0.55 * (SEASON[m] - 1) * 3 + 0.07 * wav
                meas.append(["nudo", "E-1", "nivel", f"{dd.isoformat()} {h:02d}:00", round(min(3.85, max(0.35, level)), 2), None])
    return meas, leaks, {"consumo": monthly, "nrw": nrw_month}


def _sheet(wb, title, header, rows):
    ws = wb.create_sheet(title)
    ws.append(header)
    for r in rows:
        ws.append(r)


def workbook(rows, meas, leaks) -> bytes:
    from openpyxl import load_workbook

    from app.schemas.network import HydraulicOptions
    from app.sig import excel
    from app.sig.spec import with_materials

    with_materials(["AC", "Acero", "FFD", "HA", "HDPE", "PEAD", "PVC"])
    options = HydraulicOptions(duration_h=24, hydraulic_step_min=5, pattern_step_min=60, report_step_min=60,
                               extra={"PATTERN": "CURVA"})
    model_rows = [("Opciones", json.dumps(options.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)),
                  ("Sección patterns", " CURVA\t" + "\t".join(str(v) for v in MOD[:12]) + "\n CURVA\t"
                   + "\t".join(str(v) for v in MOD[12:]))]
    data = excel.write_workbook(rows, zone_label="UTM 19S (EPSG:32719)", model_rows=model_rows)
    wb = load_workbook(io.BytesIO(data))
    _sheet(wb, "Mediciones", ["Elemento", "ID", "Medición", "Fecha y hora", "Valor", "Nota"], meas)
    _sheet(wb, "Pérdidas", ["Tramo", "Fecha", "Tipo", "Caudal estimado", "Observación"],
           [[lk, d.isoformat(), k, q, note] for d, lk, k, q, note in leaks])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Configuración del proyecto ──

def configure(session, project, clients) -> None:
    from app.schemas.demand import Addition, DemandInputs, GrowthStep
    from app.schemas.design import DesignParamUpdate
    from app.schemas.gestion import GestionSettings
    from app.services import demand, design

    src = "Valor típico de APR rural (ejemplo, no verificado)"
    eff = {p.key: p for p in design.effective(session, project)}
    changes = []
    for key, val in (("dotacion", 140.0), ("densidad", 3.2), ("perdidas", 25.0), ("coef_max_diario", 1.5),
                     ("coef_max_horario", 1.6), ("pressure_min", 15.0)):
        if key in eff:
            changes.append(DesignParamUpdate(key=key, value=val, verified=False, source=src))
    for key, p in eff.items():  # curva horaria del proyecto (si el perfil la expone como parámetro)
        if p.group == "curva" and isinstance(p.value, list) and len(p.value) == 24:
            changes.append(DesignParamUpdate(key=key, value=MOD, verified=False, source=src))
    design.update(session, project, changes)
    active = sum(1 for c in clients if c["status"] == "activo" and c["start"] is None)
    year = date.today().year
    demand.save_inputs(session, project, DemandInputs(
        base_year=year, model_year=year, current_year=year, base_mode="arranques", base_connections=active,
        persons_per_dwelling=3.2, extra_population=180.0, growth=[GrowthStep(from_year=year + 1, rate_pct=1.6),
                                                                   GrowthStep(from_year=year + 11, rate_pct=1.0)],
        additions=[Addition(year=year + 2, dwellings=24)], horizon_years=20, dotation_lphd=140.0, losses_pct=25.0,
        coef_day=1.5, coef_hour=1.6, pump_hours=12.0, regulation_pct=25.0, scenario_peak_day=False))
    gs = GestionSettings(water_right_lps=4.0, water_right_m3_year=70000.0, chlorine_min=0.2, chlorine_max=1.5,
                         chlorine_verified=False, typical_client_m3_month=17.0)
    project.gestion_settings = gs.model_dump(mode="json")
    session.flush()


def records(session, project, months, billed, cut, clients, leaks, monthly) -> None:
    from app.models import MaintenanceLog
    from app.services import gestion_records as rec

    ctx = rec.context(session, project)
    first = date(months[0][0], months[0][1], 1)

    def put(kind: str, items: list[dict]) -> list:
        spec = rec.SPECS[kind]
        good = []
        for raw in items:
            vals, err = rec.validate(spec, raw, ctx)
            if err:
                raise SystemExit(f"Registro {kind} no válido: {raw} → {err}")
            good.append(vals)
        _, _, rows = rec.create(session, project, kind, good, None)
        log(f"  · {spec.title}: {len(rows)}")
        return rows

    def active(c, t):
        return c["status"] != "proyectado" and (c["start"] is None or t >= c["start"]) and (c["end"] is None or t < c["end"])

    # Lecturas de clientes: consumo del catastro con temporada y variación por cliente.
    reads = []
    for c in clients:
        for i, t in enumerate(billed):
            if not active(c, t):
                continue
            v = c["base"] * SEASON[t[1]] * R.uniform(0.86, 1.14)
            if c["id"] == "CL-097" and t == billed[-3]:
                v *= 3.4  # medidor con fuga intradomiciliaria (aparece entre los mayores consumidores)
            reads.append({"client": c["number"], "period": ym(t), "m3": round(v, 1)})
    put("lecturas", reads)

    # Energía diaria de la bomba: horas para producir el volumen del día; kWh según la potencia medida.
    energy = []
    for k, d in enumerate(days(first, cut)):
        mk = ym((d.year, d.month))
        dim = (date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)).day
        vol = sum(monthly["consumo"][(mk, s)] / (1 - monthly["nrw"][(mk, s)]) for s in SECTORS) / dim
        hours = round(min(20.0, vol / (PUMP_LPS * 3.6) * R.uniform(0.95, 1.06)), 1)
        kw = PUMP_KW * (1.06 if d >= date(cut.year, 6, 1) else 1.0)  # desgaste: sube el consumo específico
        energy.append({"record_date": d.isoformat(), "equipment": "B-1", "kwh": round(hours * kw * R.uniform(0.97, 1.03), 1),
                       "hours": hours, "note": "Corte de luz de 3 h" if R.random() < 0.01 else None})
    put("energia", energy)

    # Cloro residual libre: semanal en 4 puntos, con fallas del dosificador (bajo 0,2) y sobredosis puntuales.
    chlorine, d, k = [], first + timedelta(days=(7 - first.weekday()) % 7), 0
    points = [("E-1", 1.05), ("J-C07", 0.8), ("J-V05", 0.55), ("J-A09", 0.5)]
    while d <= cut:
        bad = R.random() < 0.06
        for i, (pt, v0) in enumerate(points):
            k += 1
            v = v0 + R.uniform(-0.15, 0.15)
            note = None
            if bad and i >= 2:
                v, note = R.uniform(0.08, 0.18), "Falla del dosificador: se reajustó"
            elif R.random() < 0.015 and i == 0:
                v, note = R.uniform(1.6, 1.9), "Sobredosis al cambiar el bidón"
            chlorine.append({"measured_at": dt(d, 9 + i, 30).isoformat(), "point": pt, "mg_l": round(max(0.05, v), 2), "note": note})
        d += timedelta(days=7)
    put("cloro", chlorine)

    # Cortes: programados (cuartel) cada 1–2 meses y de emergencia por las roturas (tramo).
    cuts = []
    sectors = sorted(ctx.sectors)
    for i, t in enumerate(months):
        if i % 2 == 0 or t[1] in (3, 9):
            day = date(t[0], t[1], min(10 + i % 9, 28))
            if day > cut:
                continue
            st = dt(day, 9)
            cuts.append({"kind": "programado", "started_at": st.isoformat(), "ended_at": (st + timedelta(hours=2 + i % 4)).isoformat(),
                         "sector": sectors[i % len(sectors)], "note": R.choice(["Mantención de válvulas", "Lavado de red",
                                                                               "Cambio de medidores", "Empalme de arranques nuevos"])})
    for d, link, kind, _q, note in leaks:
        if kind == "rotura":
            st = dt(d, R.randint(6, 18), 15)
            open_ = d >= cut - timedelta(days=1)
            cuts.append({"kind": "emergencia", "started_at": st.isoformat(),
                         "ended_at": None if open_ else (st + timedelta(hours=R.choice([3, 4, 6, 9, 14]))).isoformat(),
                         "link_id": link, "note": note})
    put("cortes", cuts)

    # Reclamos: 3 a 7 por mes; el mes de las roturas, muchos más; El Arrayán reclama presión en verano.
    kinds = ["presion", "calidad", "corte", "fuga", "facturacion", "medidor", "otro"]
    detail = {"presion": "Poca presión en la tarde", "calidad": "Agua turbia después del corte", "corte": "Sin agua sin aviso",
              "fuga": "Agua corriendo por la calle", "facturacion": "Consumo alto en la boleta", "medidor": "Medidor empañado",
              "otro": "Consulta por factibilidad"}
    comp = []
    by_sector = {s: [c for c in clients if c["sector"] == s and c["status"] != "proyectado"] for s in SECTORS}
    for i, t in enumerate(months):
        n = R.randint(3, 7) + (12 if t == months[13] else 0) + (3 if t[1] in (1, 2) else 0)
        last = cut.day if (t[0], t[1]) == (cut.year, cut.month) else 28
        for j in range(n):
            d = date(t[0], t[1], R.randint(1, last))
            if t[1] in (12, 1, 2, 3) and R.random() < 0.5:
                kind, sec = "presion", "El Arrayán"
            elif t == months[13] and R.random() < 0.6:
                kind, sec = R.choice(["corte", "fuga", "calidad"]), "La Vega"
            else:
                kind, sec = R.choice(kinds), R.choice(SECTORS)
            c = R.choice(by_sector[sec])
            at = dt(d, R.randint(8, 19), R.choice([0, 15, 30, 45]))
            recent = (cut - d).days < 6
            status = R.choice(["abierto", "en proceso"]) if recent and R.random() < 0.6 else "cerrado"
            hours = R.choice([2, 3, 5, 8, 20, 26, 30, 48, 70, 96, 140]) * (1.6 if t == months[13] else 1)
            comp.append({"received_at": at.isoformat(), "client": c["number"], "kind": kind, "status": status,
                         "responded_at": None if status == "abierto" else (at + timedelta(hours=hours)).isoformat(),
                         "note": detail[kind]})
    put("reclamos", comp)

    # Mantenciones periódicas (algunas atrasadas) y reparaciones únicas.
    def nxt(days_from_cut: int) -> str:
        return (cut + timedelta(days=days_from_cut)).isoformat()

    periodic = [
        *[("ejercitar valvulas", v[0], f"Abrir y cerrar 3 vueltas · {v[7]}", 180, {"V-05": -47, "V-07": -12}.get(v[0], 15 + 20 * i), STAFF["op"])
          for i, v in enumerate(VALVES)],
        *[("probar grifos", g, f"Prueba de caudal y presión · {desc}", 90, {"G-02": -33}.get(g, 25 + 15 * i), "Bomberos de Diaguitas")
          for i, (g, _n, desc) in enumerate(HYDRANTS)],
        ("lavar estanque", "E-1", "Vaciado, lavado y desinfección del estanque", 180, -9, STAFF["cont"]),
        ("revisar bomba", "B-1", "Corriente, vibración, aislación y empaquetadura", 30, 8, STAFF["elec"]),
        ("cloracion", "E-1", "Revisar dosificador y stock de hipoclorito", 7, 3, STAFF["op"]),
        ("otra", "PZ-1", "Medir niveles estático y dinámico del pozo", 90, 40, STAFF["op"]),
        ("otra", "P-CEN", "Verificar macromedidores (Centro, La Vega y El Arrayán)", 365, 120, STAFF["dir"]),
    ]
    items = [{"kind": k, "element": e, "description": desc, "frequency_days": f, "next_date": nxt(o), "assignee": who}
             for k, e, desc, f, o, who in periodic]
    items += [
        {"kind": "reparacion", "element": "P-V04", "description": "Reemplazar 110 m de PVC 63 de 1986 (fugas recurrentes)",
         "next_date": nxt(-20), "assignee": STAFF["cont"]},
        {"kind": "reparacion", "element": "G-02", "description": "Cambiar empaquetadura del grifo (no cierra bien)",
         "next_date": nxt(10), "assignee": STAFF["op"]},
    ]
    for d, link, kind, _q, note in leaks:
        if kind == "reparacion":
            items.append({"kind": "reparacion", "element": link, "description": note, "next_date": d.isoformat(),
                          "assignee": STAFF["op"], "done_on": d.isoformat()})
    tasks = put("mantenciones", items)
    # Registro de cumplimiento de las periódicas: hacia atrás desde su próxima fecha (con algunos atrasos).
    session.flush()
    for t in tasks:
        if not t.frequency_days:
            continue
        due = t.next_date - timedelta(days=t.frequency_days)
        n = 0
        while due >= first and n < 40:
            late = R.choice([0, 0, 0, 1, 2, 5, 12]) if t.frequency_days >= 30 else R.choice([0, 0, 1])
            done = min(due + timedelta(days=late), cut)
            session.add(MaintenanceLog(task_id=t.id, project_id=project.id, done_on=done, scheduled_for=due,
                                       by=t.assignee, note="Sin observaciones" if late == 0 else f"Hecha con {late} días de atraso"))
            due -= timedelta(days=t.frequency_days)
            n += 1
        t.last_done = t.next_date - timedelta(days=t.frequency_days)
    session.flush()


def feasibilities(session, project, geo, months) -> None:
    """Factibilidades evaluadas con el modelo (simulaciones reales), repartidas en el período."""
    from app.models import FeasibilityRecord
    from app.schemas.analysis import FeasibilityRequest
    from app.services import feasibility

    session.commit()
    reqs = [  # tramo, fracción del tramo, consumo (L/s), solicitante, mes
        ("P-C02", 0.5, 0.02, "Vivienda familia Rojas", 3),
        ("P-V03", 0.4, 0.06, "Ampliación pisquera artesanal", 9),
        ("P-A08", 0.7, 0.75, "Loteo El Arrayán Alto (24 viviendas)", 15),
        ("P-C15", 0.5, 0.03, "Local comercial calle Balmaceda", 20),
    ]
    from app.services.network import get_version_or_404, load_model

    model = load_model(session, get_version_or_404(session, project, None))
    links = {lk.id: lk for lk in model.network.links()}
    for link, f, q, who, mi in reqs:
        coords = links[link].geometry.coordinates
        (x0, y0), (x1, y1) = coords[0], coords[-1]
        pt = (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
        req = FeasibilityRequest(model_version=1, link=link, point=pt, consumption_lps=q,
                                 elevation=_elev_at(link, f), name=who)
        res, _ = feasibility.assess(session, project, req)
        feasibility.record(session, project, req, res)
        rec = session.query(FeasibilityRecord).filter_by(project_id=project.id, name=who).one()
        t = months[mi]
        rec.created_at = datetime(t[0], t[1], 12, 15, 30, tzinfo=TZ)
        rec.created_by = "secretaria@apr-ejemplo.cl"
        log(f"  · Factibilidad {who}: {res.verdict} (presión {res.pressure_new} m)")
    session.flush()


def _elev_at(link: str, f: float) -> float:
    p = next(x for x in PIPES if x[0] == link)
    a, b = NODES.get(p[1]), NODES.get(p[2])
    return ground(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def check(session, project) -> None:
    """Simulación de 24 h (la misma de la interfaz): debe correr sin errores; informa presiones mínimas por sector."""
    from app.services.network import get_version_or_404, load_model
    from app.services.simulation import simulate_version

    res = simulate_version(session, project, 1)
    if res.status == "error" or not res.times:
        raise SystemExit(f"La simulación de 24 h falló: {[m.message for m in res.messages][:5]}")
    model = load_model(session, get_version_or_404(session, project, 1))
    length = sum((lk.properties.length_hydraulic_m or 0) for lk in model.network.links() if lk.properties.kind == "pipe")
    log(f"Red: {length / 1000:.2f} km de tuberías, {len(model.network.clients())} clientes; simulación «{res.status}», "
        f"{len(res.messages)} mensajes: {sorted({m.code for m in res.messages})}")
    for sec in SECTORS:
        ps = [min(s.pressure) for nid, s in res.nodes.items() if SECTOR_OF.get(nid) == sec]
        log(f"  · Presión mínima {sec}: {min(ps):.1f} m (máx. de las mínimas {max(ps):.1f} m)")
    for nid in PRESSURE_POINTS:
        s = res.nodes[nid].pressure
        log(f"  · {nid}: modelo {min(s):.1f} a {max(s):.1f} m (promedio {sum(s) / len(s):.1f})")
    tank = res.nodes.get("E-1")
    if tank:
        log(f"  · Estanque E-1: carga {min(tank.head):.1f} a {max(tank.head):.1f} m")
    res.messages and log("  · " + " | ".join(m.message for m in res.messages[:4]))


if __name__ == "__main__":
    main()
