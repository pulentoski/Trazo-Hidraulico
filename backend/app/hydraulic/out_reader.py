"""Lector del archivo binario de resultados de EPANET 2.x (.out).

Formato: prólogo (15 enteros + textos + IDs + datos de red), sección de energía,
resultados dinámicos por periodo de reporte y epílogo. Todos los valores son
REAL4/INT4 little-endian y vienen en las unidades declaradas en el .inp.
Este mismo lector se usa para los resultados de la API y para los de runepanet
en las pruebas de referencia, de modo que la comparación es directa.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = 516114521
NODE_VARS = ("demand", "head", "pressure", "quality")
LINK_VARS = ("flow", "velocity", "headloss", "quality", "status", "setting", "reaction", "friction")

# Códigos de unidades de caudal del archivo (EN_CFS..EN_CMS)
FLOW_UNITS = {0: "CFS", 1: "GPM", 2: "MGD", 3: "IMGD", 4: "AFD", 5: "LPS", 6: "LPM", 7: "MLD", 8: "CMH", 9: "CMD", 10: "CMS"}
PRESSURE_UNITS = {0: "PSI", 1: "KPA", 2: "METERS", 3: "BAR", 4: "FEET"}

# Estado de tramos en el archivo de resultados
LINK_STATUS = {
    0: "cerrada (no entrega altura)", 1: "cerrado temporalmente", 2: "cerrado", 3: "abierto",
    4: "activa", 5: "abierta sobre caudal máximo", 6: "abierta sin entregar caudal",
    7: "abierta sin entregar presión", 8: "llenando", 9: "vaciando", 10: "rebalsando",
}


class OutFileError(RuntimeError):
    pass


@dataclass
class OutResults:
    flow_units: str
    pressure_units: str
    report_start: int
    report_step: int
    duration: int
    node_ids: list[str]
    link_ids: list[str]
    times: list[int]
    nodes: dict[str, np.ndarray] = field(default_factory=dict)  # var -> [periodo, nudo]
    links: dict[str, np.ndarray] = field(default_factory=dict)  # var -> [periodo, tramo]
    warning_flag: int = 0

    @property
    def n_periods(self) -> int:
        return len(self.times)


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("latin-1").strip()


def read_out(path: str) -> OutResults:
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 100:
        raise OutFileError("Archivo de resultados vacío o incompleto")

    head = struct.unpack_from("<15i", data, 0)
    magic, _version, n_nodes, n_tanks, n_links, n_pumps, _n_valves = head[:7]
    flow_flag, press_flag, rstart, rstep, duration = head[9], head[10], head[12], head[13], head[14]
    if magic != MAGIC:
        raise OutFileError("Número mágico inválido en el prólogo")

    tail_magic, = struct.unpack_from("<i", data, len(data) - 4)
    n_periods, warn_flag = struct.unpack_from("<2i", data, len(data) - 12)
    if tail_magic != MAGIC:
        raise OutFileError("Número mágico inválido en el epílogo (simulación incompleta)")

    # IDs: tras 15 enteros, 3 títulos de 80, 2 nombres de archivo de 260 y 2 textos de 32.
    off = 15 * 4 + 3 * 80 + 2 * 260 + 2 * 32
    node_ids = [_cstr(data[off + 32 * i: off + 32 * (i + 1)]) for i in range(n_nodes)]
    off += 32 * n_nodes
    link_ids = [_cstr(data[off + 32 * i: off + 32 * (i + 1)]) for i in range(n_links)]

    period_floats = len(NODE_VARS) * n_nodes + len(LINK_VARS) * n_links
    period_bytes = 4 * period_floats
    results_off = len(data) - 28 - n_periods * period_bytes
    # Verificación cruzada con el tamaño esperado del prólogo + energía.
    prolog_end = (off + 32 * n_links + 4 * (3 * n_links + 2 * n_tanks + n_nodes + 2 * n_links))
    energy_bytes = n_pumps * (4 + 6 * 4) + 4
    if results_off != prolog_end + energy_bytes:
        raise OutFileError("Estructura del archivo de resultados no reconocida")

    block = np.frombuffer(data, dtype="<f4", count=n_periods * period_floats, offset=results_off)
    block = block.reshape(n_periods, period_floats).astype(np.float64)
    nodes: dict[str, np.ndarray] = {}
    links: dict[str, np.ndarray] = {}
    col = 0
    for var in NODE_VARS:
        nodes[var] = block[:, col: col + n_nodes]
        col += n_nodes
    for var in LINK_VARS:
        links[var] = block[:, col: col + n_links]
        col += n_links

    times = [rstart + k * rstep for k in range(n_periods)]
    return OutResults(
        flow_units=FLOW_UNITS.get(flow_flag, str(flow_flag)),
        pressure_units=PRESSURE_UNITS.get(press_flag, str(press_flag)),
        report_start=rstart, report_step=rstep, duration=duration,
        node_ids=node_ids, link_ids=link_ids, times=times, nodes=nodes, links=links, warning_flag=warn_flag,
    )
