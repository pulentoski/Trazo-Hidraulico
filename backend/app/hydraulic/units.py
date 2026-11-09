"""Conversión de resultados del motor a SI usando las mismas constantes internas de EPANET."""
from __future__ import annotations

import numpy as np

from app.hydraulic.out_reader import OutResults

# Constantes de EPANET (src/types.h): factores respecto de pie y pie³/s.
M_PER_FT = 0.3048
PSI_PER_FT = 0.4333
KPA_PER_PSI = 6.895
FLOW_PER_CFS = {"CFS": 1.0, "GPM": 448.831, "MGD": 0.64632, "IMGD": 0.5382, "AFD": 1.9837,
                "LPS": 28.317, "LPM": 1699.0, "MLD": 2.4466, "CMH": 101.94, "CMD": 2446.6, "CMS": 0.028317}
US_FLOW = {"CFS", "GPM", "MGD", "IMGD", "AFD"}


def to_si(res: OutResults, link_kinds: dict[str, str], specific_gravity: float = 1.0) -> dict[str, np.ndarray]:
    """Devuelve presión (m), cota piezométrica (m), demanda (L/s), caudal (L/s), velocidad (m/s) y pérdida.

    La pérdida queda en m/km para tuberías y en m para bombas y válvulas.
    """
    us = res.flow_units in US_FLOW
    q = FLOW_PER_CFS["LPS"] / FLOW_PER_CFS[res.flow_units]
    length = M_PER_FT if us else 1.0
    head = res.nodes["head"] * length
    p = res.nodes["pressure"]
    if res.pressure_units == "PSI":
        pressure = p / (PSI_PER_FT * specific_gravity) * M_PER_FT * specific_gravity
    elif res.pressure_units == "KPA":
        pressure = p / (KPA_PER_PSI * PSI_PER_FT * specific_gravity) * M_PER_FT * specific_gravity
    elif res.pressure_units == "BAR":
        pressure = p * 100 / (KPA_PER_PSI * PSI_PER_FT * specific_gravity) * M_PER_FT * specific_gravity
    elif res.pressure_units == "FEET":
        pressure = p * M_PER_FT
    else:
        pressure = p
    hl = res.links["headloss"].copy()
    if us:
        for j, lid in enumerate(res.link_ids):
            if link_kinds.get(lid) != "pipe":
                hl[:, j] = hl[:, j] * M_PER_FT
    return {
        "pressure": pressure, "head": head, "demand": res.nodes["demand"] * q,
        "flow": res.links["flow"] * q, "velocity": res.links["velocity"] * length, "headloss": hl,
        "status": res.links["status"],
    }
