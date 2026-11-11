"""Genera examples/apr-demo.xlsx: APR de demostración en la zona de La Serena (UTM 19S).

Red: pozo con bomba que impulsa a un estanque; distribución por gravedad con 15 tramos, 4 válvulas de corte
(4 cuarteles), 1 grifo y 30 clientes con atributos completos. Simulación de 24 h: curva horaria CurvaMod
normalizada, bomba con curva H-Q de 3 puntos y horario de encendido (estilo columna F de SimulaEST1), y demanda
base en los nudos (población sin catastro de clientes) para que se vea la variación de nivel del estanque.

Uso (dentro de la imagen de la API):  python scripts/make_apr_demo.py /ruta/apr-demo.xlsx
"""
from __future__ import annotations

import json
import sys

from pyproj import Transformer

from app.sig import excel
from app.sig.spec import with_materials
from app.schemas.network import HydraulicOptions
from app.sig.tables import Row

CURVA_MOD = [0.3, 0.2, 0.1, 0.1, 0.3, 0.5, 0.9, 1.5, 1.6, 1.5, 1.45, 1.35, 1.4, 1.4, 1.3, 1.1, 1.0, 0.9, 1.0, 1.2, 1.25,
             1.2, 0.9, 0.5]
MOD = [round(c / (sum(CURVA_MOD) / 24), 4) for c in CURVA_MOD]  # normalizada: promedio 1
DEMANDA_NUDO = 0.46  # L/s por nudo de distribución (≈ 6 L/s en total)

SRID = 32719
ORIGIN_LON, ORIGIN_LAT = -71.1450, -29.9420  # sector rural al oriente de La Serena
to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{SRID}", always_xy=True)
to_geo = Transformer.from_crs(f"EPSG:{SRID}", "EPSG:4326", always_xy=True)
E0, N0 = to_utm.transform(ORIGIN_LON, ORIGIN_LAT)


def geo(x: float, y: float) -> dict:
    lon, lat = to_geo.transform(E0 + x, N0 + y)
    return {"_lat": round(lat, 8), "_lon": round(lon, 8)}


# Nudos de consumo: ID → (x, y, cota)
JUNCTIONS = {
    "J-IMP": (10, 0, 210.0), "J-1": (300, 200, 241.0), "J-2": (400, 200, 239.5), "J-3": (500, 200, 238.0),
    "J-4": (600, 200, 237.0), "J-5": (700, 200, 236.0), "J-6": (500, 100, 233.0), "J-7": (500, 0, 228.0),
    "J-8": (700, 100, 232.5), "J-9": (700, 0, 228.5), "J-10": (400, 300, 242.5), "J-11": (400, 400, 245.0),
    "J-12": (600, 300, 241.5), "J-13": (600, 400, 244.5),
}
# Tramos: ID → (inicial, final, material, DN, clase, año, estado, tipo de red, vértices locales)
PIPES = {
    "P-01": ("J-IMP", "E-1", "HDPE", 110, "PN10", 2015, "bueno", "impulsion", [(10, 300), (200, 480)]),
    "P-02": ("E-1", "J-1", "PVC", 110, "C10", 2015, "bueno", "aduccion", [(300, 400)]),
    "P-03": ("J-1", "J-2", "PVC", 110, "C10", 2001, "bueno", "matriz", []),
    "P-04": ("J-2", "J-3", "PVC", 110, "C10", 2001, "regular", "matriz", []),
    "P-05": ("J-3", "J-4", "PVC", 90, "C10", 1996, "regular", "distribucion", []),
    "P-06": ("J-4", "J-5", "PVC", 75, "C10", 1985, "malo", "distribucion", []),
    "P-07": ("J-3", "J-6", "PVC", 75, "C10", 1994, "regular", "distribucion", []),
    "P-08": ("J-6", "J-7", "PVC", 63, "C10", 1972, "malo", "distribucion", []),
    "P-09": ("J-5", "J-8", "PVC", 63, "C10", 1998, "regular", "distribucion", []),
    "P-10": ("J-8", "J-9", "PVC", 63, "C10", 2005, "bueno", "distribucion", []),
    "P-11": ("J-7", "J-9", "PVC", 63, "C10", 2005, "bueno", "distribucion", []),
    "P-12": ("J-2", "J-10", "PVC", 75, "C10", 2010, "bueno", "distribucion", []),
    "P-13": ("J-10", "J-11", "PVC", 63, "C10", 1979, "malo", "distribucion", []),
    "P-14": ("J-4", "J-12", "PVC", 75, "C10", 2012, "bueno", "distribucion", []),
    "P-15": ("J-12", "J-13", "PVC", 63, "C10", 2012, "bueno", "distribucion", []),
}
VALVES = [  # ID, tramo, posición, tipo, diámetro, profundidad, nombre
    ("V-1", "P-04", 0.2, "compuerta", 110, 1.2, "Calle Los Aromos"),
    ("V-2", "P-07", 0.2, "compuerta", 75, 1.1, "Pasaje El Molle"),
    ("V-3", "P-11", 0.5, "compuerta", 63, 1.0, "Camino interior"),
    ("V-4", "P-12", 0.2, "compuerta", 75, 1.1, "Calle La Higuera"),
]
CLIENT_NODES = ["J-1", "J-1", "J-2", "J-2", "J-2", "J-3", "J-3", "J-4", "J-4", "J-4", "J-5", "J-5", "J-6", "J-6",
                "J-6", "J-7", "J-7", "J-8", "J-8", "J-9", "J-9", "J-9", "J-10", "J-10", "J-11", "J-11", "J-12",
                "J-12", "J-13", "J-13"]
STREETS = {"J-1": "Los Aromos", "J-2": "Los Aromos", "J-3": "Los Aromos", "J-4": "Los Aromos", "J-5": "Los Aromos",
           "J-6": "El Molle", "J-7": "El Molle", "J-8": "Los Pimientos", "J-9": "Camino Interior",
           "J-10": "La Higuera", "J-11": "La Higuera", "J-12": "Las Palmas", "J-13": "Las Palmas"}
# Sector (atributo libre «Sector»): la zona alta (calle La Higuera) tiene macromedidor en P-12.
ALTO_NODES = {"J-10", "J-11"}
MACRO_PIPE = "P-12"  # macromedidor de la zona alta: su atributo «Sector» asigna la producción
PROJECTED = {27, 30}  # loteo en Las Palmas
CLIENT_ELEVATION = {24: 244.0, 25: 257.0}  # C-025 está en la loma: queda sobre la cota piezométrica disponible
# Registro de pérdidas por tramo: fecha, tramo, tipo, caudal estimado (L/s), observación.
LEAKS = [
    ("2025-11-03", "P-06", "fuga", 0.05, "Filtración en unión, calle Los Aromos"),
    ("2025-11-04", "P-06", "reparacion", None, "Cambio de copla"),
    ("2026-02-18", "P-06", "rotura", 0.4, "Rotura por tránsito de camión"),
    ("2026-02-19", "P-06", "reparacion", None, "Reparación con abrazadera"),
    ("2026-05-10", "P-08", "fuga", 0.08, "Afloramiento en vereda"),
    ("2026-08-22", "P-08", "fuga", 0.06, None),
    ("2026-09-30", "P-13", "rotura", 0.3, "Rotura en cruce de calle"),
    ("2026-10-12", "P-04", "fuga", 0.03, "Filtración en arranque"),
]
NAMES = ["Rojas", "Araya", "Castillo", "Cortés", "González", "Muñoz", "Pizarro", "Alfaro", "Rivera", "Olivares",
         "Tapia", "Contreras", "Díaz", "Vega", "Carvajal"]


def rows() -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {}
    out["nudos"] = [Row(i, {**geo(x, y), "elevation": z, "base_demand": 0.0 if i == "J-IMP" else DEMANDA_NUDO,
                            "demand_pattern": None,
                            "description": "Nudo de impulsión" if i == "J-IMP" else None})
                    for i, (x, y, z) in JUNCTIONS.items()]
    out["estanques"] = [Row("E-1", {**geo(250, 500), "elevation": 268.0, "init_level": 2.5, "min_level": 0.5,
                                    "max_level": 4.0, "tank_diameter": 8.0, "min_volume": None, "volume_curve": None,
                                    "can_overflow": False, "description": "Estanque semienterrado 200 m³"})]
    # Bomba: curva H-Q de 3 puntos y horario: apagada de 2 a 6 h y de 17 a 21 h (14 h encendida).
    out["reservorios"] = [Row("R-POZO", {**geo(0, 0), "elevation": None, "head": None, "head_pattern": None,
                                         "description": "Nivel dinámico del pozo"})]
    out["pozos"] = [Row("PZ-1", {**geo(0, 0), "node": "R-POZO", "ground_elevation": 210.0, "depth_m": 80.0,
                                 "static_level_m": 22.0, "dynamic_level_m": 35.0, "authorized_flow_lps": 6.0,
                                 "condition": "bueno", "description": "Pozo profundo, sondaje 2014"},
                        {"Derecho DGA": "ND-0401-1234"})]
    out["bombas"] = [Row("B-1", {"from_node": "R-POZO", "to_node": "J-IMP", "_vertices": None, "pump_curve": None,
                                 "pump_power": None, "pump_speed": 1.0, "pump_pattern": None, "initial_status": "open",
                                 "_curve": "0 130; 10 110; 16 80", "_schedule": "0-1; 7-16; 22-23",
                                 "_lc_tank": None, "_lc_on": None, "_lc_off": None,
                                 "description": "Bomba sumergible 15 HP"})]
    tramos = []
    for i, (a, b, mat, dn, cls, year, cond, ntype, verts) in PIPES.items():
        vtxt = "; ".join("{_lat!r} {_lon!r}".format(**geo(x, y)) for x, y in verts) or None
        tramos.append(Row(i, {"from_node": a, "to_node": b, "_vertices": vtxt, "dn": dn, "inner_diameter_mm": None,
                              "material": mat, "pipe_class": cls, "roughness": None, "minor_loss": 0.0,
                              "initial_status": "open", "length_choice": "slope", "_length_manual": None,
                              "condition": cond, "install_year": year, "network_type": ntype,
                              "description": None}, {"Sector": "Alto"} if i == MACRO_PIPE else {}))
    out["tramos"] = tramos
    pos = {i: (x, y) for i, (x, y, _z) in JUNCTIONS.items()}
    valves = []
    for vid, link, p, vtype, d, depth, name in VALVES:
        valves.append(Row(vid, {"_class": "corte", "_type": vtype, "_state": "open", "condition": "bueno",
                                "_diameter": d, "_depth": depth, "link": link, "position": p, "name": name}))
    out["valvulas"] = valves
    hx, hy = pos["J-5"]
    out["grifos"] = [Row("G-1", {**geo(hx + 4, hy + 3), "node": "J-5", "hydrant_type": "columna",
                                 "condition": "bueno", "diameter_mm": 100.0, "fire_flow_lps": 16.0,
                                 "min_pressure_m": 5.0, "description": "Frente a la sede social"})]
    clients = []
    count: dict[str, int] = {}
    for k, node in enumerate(CLIENT_NODES, start=1):
        n = count[node] = count.get(node, 0) + 1
        x, y = pos[node]
        dx, dy = (-18 + 12 * n, 14 if k % 2 else -14)
        route = 1 if node in ("J-1", "J-2", "J-10", "J-11") else 2 if node in ("J-3", "J-4", "J-5", "J-12", "J-13") else 3
        ctype = "comercial" if k == 5 else "industrial" if k == 17 else "publico" if k == 11 else "residencial"
        volume = 120.0 if ctype == "industrial" else 18.0 if ctype == "residencial" else 45.0
        status = "suspendido" if k == 29 else "proyectado" if k in PROJECTED else "activo"
        clients.append(Row(f"C-{k:03d}", {
            **geo(x + dx, y + dy), "client_number": f"{1000 + k}", "name": f"Familia {NAMES[k % len(NAMES)]}",
            "address": f"{STREETS[node]} {100 + 10 * k}", "route": str(route), "meter_number": f"MED-{2400 + k}",
            "client_type": ctype, "status": status, "consumption_value": volume, "consumption_unit": "m3/mes",
            "node": node, "link": None, "elevation": CLIENT_ELEVATION.get(k)},
            {"Sector social": "A" if k <= 15 else "B", "Sector": "Alto" if node in ALTO_NODES else "Bajo"}))
    out["clientes"] = clients
    return out


def records(data: bytes) -> bytes:
    """Agrega las hojas de registros del proyecto: lecturas de producción (pozo y macromedidor) y pérdidas."""
    import io
    from datetime import datetime, timedelta

    from openpyxl import load_workbook
    from openpyxl.styles import Font

    wb = load_workbook(io.BytesIO(data))
    ws = wb.create_sheet("Mediciones")
    ws.append(["Elemento", "ID", "Medición", "Fecha y hora", "Valor", "Nota"])
    ws.append(["nudo, tramo, cliente o pozo", "ID del elemento", "medidor (m³), presión (m) o nivel (m)",
               "AAAA-MM-DD HH:MM", "lectura", "opcional"])
    t0 = datetime(2026, 10, 1, 8, 0)
    well, macro = 1373232.8, 48211.0
    for d in range(31):  # lecturas diarias de octubre: producción ≈ 26,9 m³/día (pozo) y 3,1 m³/día (zona alta)
        t = (t0 + timedelta(days=d)).strftime("%Y-%m-%d %H:%M")
        ws.append(["pozo", "PZ-1", "medidor", t, round(well, 1), "lectura inicial" if d == 0 else None])
        ws.append(["tramo", "P-12", "medidor", t, round(macro, 2), "macromedidor zona alta" if d == 0 else None])
        well += 26.9 + (1.4 if d % 7 in (5, 6) else -0.6)
        macro += 3.1 + (0.2 if d % 7 in (5, 6) else -0.08)
    lk = wb.create_sheet("Pérdidas")
    lk.append(["Tramo", "Fecha", "Tipo", "Caudal estimado", "Observación"])
    lk.append(["ID del tramo", "AAAA-MM-DD", "fuga, rotura o reparación", "L/s (opcional)", "texto libre"])
    for day, link, kind, q, note in LEAKS:
        lk.append([link, day, kind, q, note])
    for sh in (ws, lk):
        for c in range(1, sh.max_column + 1):
            sh.cell(1, c).font = Font(bold=True)
            sh.cell(2, c).font = Font(italic=True, color="666666")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main(path: str) -> None:
    with_materials(["AC", "Acero", "FFD", "HA", "HDPE", "PEAD", "PVC"])
    options = HydraulicOptions(duration_h=24, hydraulic_step_min=5, pattern_step_min=60, report_step_min=60,
                               extra={"PATTERN": "MOD"})
    model_rows = [("Opciones", json.dumps(options.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)),
                  ("Sección patterns", " MOD\t" + "\t".join(str(v) for v in MOD[:12]) + "\n MOD\t"
                   + "\t".join(str(v) for v in MOD[12:]))]
    data = excel.write_workbook(rows(), zone_label="UTM 19S (EPSG:32719)", model_rows=model_rows)
    with open(path, "wb") as fh:
        fh.write(records(data))
    print(f"Planilla escrita en {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "apr-demo.xlsx")
