"""Datos iniciales: catálogo PVC/HDPE y perfil de criterios de diseño (no verificados).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08
"""
import math
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OD_SERIES = [63, 75, 90, 110, 125, 140, 160, 200, 250, 315, 355, 400]
# Clase → SDR (relación diámetro exterior / espesor). Valores típicos; deben verificarse con el fabricante.
PVC_CLASSES = {"C6": 41.0, "C10": 26.0, "C16": 17.0}
HDPE_CLASSES = {"PN10": 17.0, "PN16": 11.0}
SOURCE = ("Valores típicos de referencia calculados con SDR por clase (espesor = DE/SDR redondeado "
          "hacia arriba a 0,1 mm). NO VERIFICADO: contrastar con catálogo del fabricante y norma vigente.")


def _rows():
    rows = []
    for material, standard, classes, c, eps, n, min_wall in (
        ("PVC", "NCh 399 (referencial)", PVC_CLASSES, 150.0, 0.0015, 0.009, 1.8),
        ("HDPE", "NCh 2349 / PE100 (referencial)", HDPE_CLASSES, 150.0, 0.007, 0.009, 2.0),
    ):
        for pipe_class, sdr in classes.items():
            for od in OD_SERIES:
                wall = max(min_wall, math.ceil(od / sdr * 10) / 10)
                rows.append(dict(material=material, standard=standard, dn=od, pipe_class=pipe_class,
                                 od_mm=float(od), wall_mm=wall, inner_diameter_mm=round(od - 2 * wall, 1),
                                 hw_c=c, dw_roughness_mm=eps, manning_n=n, verified=False, source=SOURCE))
    return rows


CRITERIA = [
    {"key": "pressure_min", "label": "Presión mínima de servicio", "min": 15.0, "max": None, "unit": "m"},
    {"key": "pressure_max", "label": "Presión máxima estática", "min": None, "max": 70.0, "unit": "m"},
    {"key": "velocity_min", "label": "Velocidad mínima", "min": 0.3, "max": None, "unit": "m/s"},
    {"key": "velocity_max", "label": "Velocidad máxima", "min": None, "max": 2.0, "unit": "m/s"},
    {"key": "unit_headloss_max", "label": "Pérdida unitaria máxima (cuello de botella)", "min": None, "max": 10.0, "unit": "m/km"},
    {"key": "dn_min", "label": "Diámetro nominal mínimo de red", "min": 75.0, "max": None, "unit": "mm"},
]


def upgrade() -> None:
    catalog = sa.table(
        "catalog_pipe",
        *(sa.column(c) for c in ("material", "standard", "dn", "pipe_class", "od_mm", "wall_mm",
                                 "inner_diameter_mm", "hw_c", "dw_roughness_mm", "manning_n", "verified", "source")),
    )
    op.bulk_insert(catalog, _rows())
    profile = sa.table(
        "design_profile",
        sa.column("name"), sa.column("source"), sa.column("version"), sa.column("valid_from"),
        sa.column("valid_to"), sa.column("verified"), sa.column("status"),
        sa.column("criteria", pg.JSONB), sa.column("notes"),
    )
    op.bulk_insert(profile, [dict(
        name="Criterios referenciales de red de distribución",
        source="Práctica habitual en Chile con base en NCh 691 (referencial). Requiere revisión contra la norma vigente.",
        version="0.1", valid_from=date(2026, 1, 1), valid_to=None, verified=False, status="no verificado",
        criteria=CRITERIA,
        notes="Valores de partida para la etapa 1. Marcado 'no verificado' hasta su revisión por un profesional.",
    )])


def downgrade() -> None:
    op.execute("DELETE FROM design_profile")
    op.execute("DELETE FROM catalog_pipe")
