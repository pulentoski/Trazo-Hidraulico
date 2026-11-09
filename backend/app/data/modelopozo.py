"""Catálogo de diámetros interiores de la planilla del ingeniero (ModeloPozo.xlsx, hoja «D=Interiores»).

La hoja tiene una fila por diámetro nominal (columna B, mm) y una columna por material y clase:
C–H = PN10 (AC, ACERO, FFD, HA, PEAD, PVC) e I–N = PN16 (mismos materiales). Una celda vacía significa
que la combinación no está disponible. Algunas celdas son fórmulas aritméticas, a veces con referencias
estructuradas a la propia fila (`Tabla3[[#This Row],[(mm)]]` = DN): se evalúan aquí sin `eval`.

`read_sheet` requiere openpyxl (dependencia de desarrollo); el resultado se congela en
`catalogo_modelopozo.json`, que es lo que carga la migración.
"""
from __future__ import annotations

import ast
import json
import operator
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SHEET = "D=Interiores"
SOURCE = "Planilla ModeloPozo (ingeniero hidráulico), no verificado"
JSON_PATH = Path(__file__).with_name("catalogo_modelopozo.json")

MATERIALS = {"AC": "AC", "ACERO": "Acero", "FFD": "FFD", "HA": "HA", "PEAD": "PEAD", "PVC": "PVC"}
COLUMNS = {  # columna → (material, clase)
    "C": ("AC", "PN10"), "D": ("Acero", "PN10"), "E": ("FFD", "PN10"), "F": ("HA", "PN10"),
    "G": ("PEAD", "PN10"), "H": ("PVC", "PN10"),
    "I": ("AC", "PN16"), "J": ("Acero", "PN16"), "K": ("FFD", "PN16"), "L": ("HA", "PN16"),
    "M": ("PEAD", "PN16"), "N": ("PVC", "PN16"),
}
# Rugosidad típica por material (valores de partida, NO verificados): C de H-W, ε (mm) de D-W, n de Manning.
ROUGHNESS = {
    "AC": (140.0, 0.025, 0.011), "Acero": (120.0, 0.045, 0.012), "FFD": (130.0, 0.1, 0.012),
    "HA": (120.0, 0.3, 0.013), "PEAD": (150.0, 0.007, 0.009), "PVC": (150.0, 0.0015, 0.009),
}
# SDR típico por clase en plásticos (DN = diámetro exterior) para detectar valores dudosos.
PLASTIC_SDR = {("PVC", "PN10"): 26.0, ("PVC", "PN16"): 17.0, ("PEAD", "PN10"): 17.0, ("PEAD", "PN16"): 11.0}
THIS_ROW = re.compile(r"Tabla\d*\[\[#This Row\],\[\(mm\)\]\]", re.IGNORECASE)
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


@dataclass
class CatalogRow:
    material: str
    pipe_class: str
    dn: int
    inner_diameter_mm: float
    cell: str
    formula: str | None = None
    od_mm: float | None = None
    wall_mm: float | None = None
    review: list[str] = field(default_factory=list)


def eval_formula(formula: str, dn: float) -> float:
    """Evalúa una fórmula aritmética de Excel (`=a-b*c`, con la referencia a la columna DN de la fila)."""
    expr = THIS_ROW.sub(repr(float(dn)), formula.lstrip("="))
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        raise ValueError(f"Fórmula no soportada: {formula}")

    return round(ev(tree), 4)


def _formula_base(formula: str) -> float | None:
    """Diámetro exterior explícito con que empieza la fórmula (p. ej. 90 en «=90-8.2-8.2»)."""
    m = re.match(r"=\s*(\d+(?:\.\d+)?)", formula)
    return float(m.group(1)) if m else None


def review(rows: list[CatalogRow]) -> None:
    """Marca filas dudosas para revisión del ingeniero (no las descarta)."""
    by_combo: dict[tuple[str, str], list[CatalogRow]] = {}
    for r in rows:
        by_combo.setdefault((r.material, r.pipe_class), []).append(r)
        if r.formula:
            base = _formula_base(r.formula)
            if base is not None and abs(base - r.dn) > 1e-9:
                r.review.append(f"calculado sobre {base:g} mm, no sobre el DN {r.dn}")
        if r.inner_diameter_mm <= 0:
            r.review.append("diámetro interior no positivo")
        if r.material in ("PEAD", "PVC") and r.inner_diameter_mm >= r.dn:
            r.review.append(f"interior ≥ DN en un plástico (DN = diámetro exterior): {r.inner_diameter_mm:g} mm")
        elif r.material not in ("PEAD", "PVC") and abs(r.inner_diameter_mm - r.dn) < 1e-9:
            r.review.append("interior igual al DN: confirmar que es el diámetro interior real")
        sdr = PLASTIC_SDR.get((r.material, r.pipe_class))
        if sdr and r.inner_diameter_mm < r.dn:
            expected = r.dn * (1 - 2 / sdr)
            if abs(r.inner_diameter_mm - expected) / expected > 0.06:
                r.review.append(f"difiere más de 6 % del típico SDR {sdr:g} ({expected:.1f} mm)")
    for combo_rows in by_combo.values():
        combo_rows.sort(key=lambda x: x.dn)
        # La comparación con el DN anterior solo vale si esa fila no está ya marcada por otro motivo.
        ok = [r for r in combo_rows if not r.review]
        for a, b in zip(ok, ok[1:]):
            if b.inner_diameter_mm <= a.inner_diameter_mm:
                b.review.append(f"interior no crece con el DN (DN {a.dn}: {a.inner_diameter_mm:g} mm)")


def read_sheet(path: str | Path) -> list[CatalogRow]:
    from openpyxl import load_workbook

    ws = load_workbook(path, data_only=False)[SHEET]
    header = {c: str(ws[f"{c}4"].value or "").strip() for c in COLUMNS}
    expected = ["AC", "ACERO", "FFD", "HA", "PEAD", "PVC"]
    got = [re.sub(r"\d+$", "", header[c]).upper() for c in COLUMNS]
    if got != expected * 2:
        raise ValueError(f"Encabezados inesperados en {SHEET}: {header}")
    rows: list[CatalogRow] = []
    for r in range(5, ws.max_row + 1):
        dn = ws[f"B{r}"].value
        if not isinstance(dn, (int, float)):
            continue
        for col, (material, pipe_class) in COLUMNS.items():
            raw = ws[f"{col}{r}"].value
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue  # combinación no disponible
            formula = raw if isinstance(raw, str) and raw.startswith("=") else None
            value = eval_formula(raw, dn) if formula else float(raw)
            row = CatalogRow(material=material, pipe_class=pipe_class, dn=int(dn), inner_diameter_mm=value,
                             cell=f"{col}{r}", formula=formula)
            if material in ("PEAD", "PVC"):
                row.od_mm = float(dn)
                row.wall_mm = round((row.od_mm - value) / 2, 3)
            rows.append(row)
    review(rows)
    return rows


def to_json(rows: list[CatalogRow]) -> str:
    return json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=1)


def load_json() -> list[dict]:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def review_markdown(rows: list[CatalogRow]) -> str:
    flagged = [r for r in rows if r.review]
    lines = ["# Catálogo ModeloPozo: filas para revisión", "",
             f"Fuente: `docs/referencias/ModeloPozo.xlsx`, hoja «{SHEET}». {len(rows)} combinaciones "
             f"material × clase × DN con diámetro interior; {len(flagged)} marcadas para revisión. "
             "Se cargan igual (no verificadas); este reporte se regenera en cada `make test`.", "",
             "| Material | Clase | DN | Interior (mm) | Celda | Fórmula | Observación |", "|---|---|---:|---:|---|---|---|"]
    for r in flagged:
        lines.append(f"| {r.material} | {r.pipe_class} | {r.dn} | {r.inner_diameter_mm:g} | {r.cell} | "
                     f"{('`' + r.formula + '`') if r.formula else ''} | {'; '.join(r.review)} |")
    counts: dict[str, int] = {}
    for r in rows:
        counts[f"{r.material} {r.pipe_class}"] = counts.get(f"{r.material} {r.pipe_class}", 0) + 1
    lines += ["", "## Combinaciones disponibles", "", "| Material y clase | DN disponibles |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(counts.items())]
    return "\n".join(lines) + "\n"
