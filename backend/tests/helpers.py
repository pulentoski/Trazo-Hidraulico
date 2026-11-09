"""Utilidades de prueba: construcción de redes, comparación con tolerancias y reporte de validación."""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.hydraulic.out_reader import OutResults, read_out

RUNEPANET = os.environ.get("RUNEPANET", "/usr/local/bin/runepanet")

# Tolerancias de comparación: |a − b| ≤ atol + rtol·|referencia|  (documentadas en docs/validation/tolerancias.md)
TOLERANCES: dict[str, tuple[float, float, str]] = {
    "pressure": (1e-3, 1e-5, "m"),
    "head": (1e-3, 1e-6, "m"),
    "demand": (1e-3, 1e-5, "L/s"),
    "flow": (1e-3, 1e-5, "L/s"),
    "velocity": (1e-4, 1e-5, "m/s"),
    "headloss": (1e-4, 1e-4, "m"),
}
LABELS = {"pressure": "Presión", "head": "Cota piezométrica", "demand": "Demanda", "flow": "Caudal",
          "velocity": "Velocidad", "headloss": "Pérdida de carga del tramo"}


def total_headloss(hl: np.ndarray, link_ids: list[str], kinds: dict[str, str], lengths: dict[str, float]) -> np.ndarray:
    """Convierte la pérdida unitaria de tuberías (m/km) en pérdida del tramo (m); bombas y válvulas ya están en m.

    En tramos muy cortos la pérdida unitaria amplifica por 1000/L la resolución float32 de las cotas del .out,
    por eso la comparación se hace sobre la pérdida total del tramo.
    """
    out = np.array(hl, dtype=float, copy=True)
    for j, lid in enumerate(link_ids):
        if kinds.get(lid) == "pipe":
            out[:, j] = out[:, j] * lengths[lid] / 1000.0
    return out


def run_runepanet(inp: Path | str) -> OutResults:
    with tempfile.TemporaryDirectory() as tmp:
        rpt, out = os.path.join(tmp, "r.rpt"), os.path.join(tmp, "r.out")
        proc = subprocess.run([RUNEPANET, str(inp), rpt, out], capture_output=True, text=True, timeout=300,
                              cwd=tmp)
        assert os.path.exists(out), f"runepanet falló: {proc.stdout}\n{proc.stderr}"
        return read_out(out)


@dataclass
class Comparison:
    case: str
    variable: str
    n_values: int
    max_abs: float
    max_rel: float
    worst_ratio: float  # max(|Δ| / (atol + rtol·|ref|)); ≤ 1 cumple
    ok: bool


@dataclass
class Collector:
    rows: list[Comparison] = field(default_factory=list)

    def compare(self, case: str, variable: str, ref: np.ndarray, got: np.ndarray) -> Comparison:
        atol, rtol, _ = TOLERANCES[variable]
        ref = np.asarray(ref, dtype=float)
        got = np.asarray(got, dtype=float)
        assert ref.shape == got.shape, f"{case}/{variable}: dimensiones {ref.shape} vs {got.shape}"
        diff = np.abs(ref - got)
        allowed = atol + rtol * np.abs(ref)
        rel = diff / np.maximum(np.abs(ref), 1e-9)
        row = Comparison(case=case, variable=variable, n_values=int(ref.size), max_abs=float(diff.max(initial=0)),
                         max_rel=float(rel[np.abs(ref) > 10 * atol].max(initial=0)),
                         worst_ratio=float((diff / allowed).max(initial=0)), ok=bool((diff <= allowed).all()))
        self.rows.append(row)
        return row

    def write_markdown(self, path: Path, title: str, intro: str) -> None:
        lines = [f"# {title}", "", intro, "",
                 "| Caso | Variable | Valores comparados | Máx. diferencia absoluta | Máx. dif. relativa (ref > 10·atol) "
                 "| Uso de la tolerancia | Resultado |",
                 "|---|---|---:|---:|---:|---:|---|"]
        for r in self.rows:
            unit = TOLERANCES[r.variable][2]
            lines.append(f"| {r.case} | {LABELS[r.variable]} ({unit}) | {r.n_values} | {r.max_abs:.3e} | "
                         f"{r.max_rel:.3e} | {100 * r.worst_ratio:.1f} % | {'cumple' if r.ok else 'NO CUMPLE'} |")
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


def node(i: str, kind: str = "junction", lon: float = -70.65, lat: float = -33.45, **props) -> dict:
    return {"type": "Feature", "id": i, "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"element": "node", "kind": kind, **props}}


def pipe(i: str, a: str, b: str, coords: list[list[float]] | None = None, **props) -> dict:
    base = {"element": "link", "kind": "pipe", "from_node": a, "to_node": b, "roughness": 150.0,
            "inner_diameter_mm": 101.6, "length_choice": "slope"}
    base.update(props)
    return {"type": "Feature", "id": i,
            "geometry": {"type": "LineString", "coordinates": coords or [[-70.65, -33.45], [-70.649, -33.45]]},
            "properties": base}


def fc(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}
