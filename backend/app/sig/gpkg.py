"""Exportación GeoPackage (OGC GeoPackage 1.2) para QGIS: una capa por hoja, con todos los atributos.

Se escribe directamente con sqlite3 (sin dependencias nativas): tablas gpkg_*, geometrías GeoPackage
binary (cabecera GP + WKB) en el SRID métrico del proyecto.
"""
from __future__ import annotations

import os
import sqlite3
import struct
import tempfile

from pyproj import CRS

from app.schemas.network import NetworkModel
from app.services.geometry import to_metric

from .sectors import compute_sectors
from .spec import SHEETS
from .tables import model_rows

LAYERS = {"nudos": "nudos", "tramos": "tramos", "estanques": "estanques", "reservorios": "reservorios",
          "valvulas": "valvulas", "grifos": "grifos", "pozos": "pozos", "bombas": "bombas", "clientes": "clientes"}


def _gp(srid: int, wkb: bytes, env: tuple[float, float, float, float]) -> bytes:
    # magic 'GP', versión 0, flags: little endian (1) + envolvente xy (código 1 → bits 1-3 = 001)
    flags = 0b00000011
    return b"GP" + bytes([0, flags]) + struct.pack("<i", srid) + struct.pack("<4d", env[0], env[1], env[2], env[3]) + wkb


def _wkb_point(x: float, y: float) -> bytes:
    return struct.pack("<BIdd", 1, 1, x, y)


def _wkb_line(pts: list[tuple[float, float]]) -> bytes:
    return struct.pack("<BII", 1, 2, len(pts)) + b"".join(struct.pack("<dd", x, y) for x, y in pts)


def _col_name(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def write_gpkg(model: NetworkModel, srid: int) -> bytes:
    tr = to_metric(srid)
    rows = model_rows(model, srid)
    sectors = compute_sectors(model)
    with tempfile.TemporaryDirectory(prefix="trazo-gpkg-") as tmp:
        path = os.path.join(tmp, "red.gpkg")
        db = sqlite3.connect(path)
        db.execute("PRAGMA application_id = 1196444487")
        db.execute("PRAGMA user_version = 10200")
        db.executescript("""
        CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
          organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT);
        CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
          description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER);
        CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL,
          geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
          CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
        """)
        crs = CRS.from_epsg(srid)
        db.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)", [
            ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
            ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
            ("WGS 84 geodetic", 4326, "EPSG", 4326, CRS.from_epsg(4326).to_wkt("WKT1_GDAL"), None),
            (crs.name, srid, "EPSG", srid, crs.to_wkt("WKT1_GDAL"), None),
        ])

        def layer(name: str, gtype: str, columns: list[str], feats: list[tuple[bytes, tuple, list]]) -> None:
            cols_sql = ", ".join(f"{_col_name(c)} {t}" for c, t in zip(columns, _types(feats, len(columns))))
            db.execute(f'CREATE TABLE "{name}" (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom {gtype}'
                       + (f", {cols_sql}" if columns else "") + ")")
            minx = min((f[1][0] for f in feats), default=None)
            miny = min((f[1][2] for f in feats), default=None)
            maxx = max((f[1][1] for f in feats), default=None)
            maxy = max((f[1][3] for f in feats), default=None)
            db.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, min_x, min_y, max_x, max_y, srs_id)"
                       " VALUES (?,?,?,?,?,?,?,?)", (name, "features", name, minx, miny, maxx, maxy, srid))
            db.execute("INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,0,0)", (name, "geom", gtype, srid))
            ph = ", ".join("?" * (len(columns) + 1))
            names = ", ".join(["geom"] + [_col_name(c) for c in columns])
            db.executemany(f'INSERT INTO "{name}" ({names}) VALUES ({ph})',
                           [(f[0], *f[2]) for f in feats])

        by_key = {s.key: s for s in SHEETS}
        coords = {}
        for lk in model.network.links():
            coords[lk.id] = lk.geometry.coordinates
        for key, lname in LAYERS.items():
            sheet = by_key[key]
            data = rows[key]
            attr_keys: list[str] = []
            for r in data:
                for k in r.attributes:
                    if k not in attr_keys:
                        attr_keys.append(k)
            cols = [c for c in sheet.cols if c.key not in ("_lat", "_lon", "_vertices", "_east", "_north")]
            header = [c.header if c.key != "id" else "id" for c in cols] + attr_keys
            is_line = key in ("tramos", "bombas")
            feats = []
            for r in data:
                if is_line:
                    pts = [tuple(map(float, tr.transform(*c))) for c in coords[r.id]]
                    wkb = _wkb_line(pts)
                    env = (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
                else:
                    x, y = tr.transform(r.values["_lon"], r.values["_lat"])
                    wkb, env = _wkb_point(x, y), (x, x, y, y)
                vals = [r.id if c.key == "id" else _v(c.label_of(r.values.get(c.key))) for c in cols]
                vals += [_v(r.attributes.get(k)) for k in attr_keys]
                feats.append((_gp(srid, wkb, env), env, vals))
            layer(lname, "LINESTRING" if is_line else "POINT", header, feats)
        # Cuarteles de corta como capa de tramos (un registro por tramo parcial).
        feats = []
        for s in sectors.sectors:
            for pc in s.pieces:
                pts = [tuple(map(float, tr.transform(*c))) for c in coords[pc.link]]
                env = (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
                feats.append((_gp(srid, _wkb_line(pts), env), env,
                              [s.id, pc.link, pc.start, pc.end, ", ".join(s.valves), s.affected_clients]))
        layer("cuarteles", "LINESTRING", ["cuartel", "tramo", "desde", "hasta", "valvulas", "clientes_afectados"], feats)
        db.commit()
        db.close()
        with open(path, "rb") as fh:
            return fh.read()


def _v(v):
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, bool):
        return int(v)
    return str(v)


def _types(feats, n: int) -> list[str]:
    out = []
    for i in range(n):
        vals = [f[2][i] for f in feats if f[2][i] is not None]
        if vals and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            out.append("INTEGER")
        elif vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            out.append("DOUBLE")
        else:
            out.append("TEXT")
    return out
