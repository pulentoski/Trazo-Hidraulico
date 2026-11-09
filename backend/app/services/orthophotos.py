"""Ortofotos: subida y validación, georreferencia (GeoTIFF, archivo world o puntos de control), cola de
procesamiento (worker con GDAL → Cloud Optimized GeoTIFF en EPSG:3857) y teselas servidas por TiTiler.

Archivos en ORTHO_DIR/<id>/: original.<ext>, original.<world> (si corresponde) y cog.tif.
"""
from __future__ import annotations

import math
import os
import shutil
import struct
import uuid
from datetime import date

import numpy as np
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cache import get_redis
from app.core.config import get_settings
from app.models import Orthophoto, Project
from app.schemas.sig import Gcp, GcpFit, OrthophotoOut, OrthophotoUpdate
from app.services.errors import NotFound
from app.services.geometry import to_metric

QUEUE = "trazo:ortho:jobs"
IMAGE_EXT = {"tif": "geotiff", "tiff": "geotiff", "jpg": "image", "jpeg": "image", "png": "image"}
WORLD_EXT = {"jpg": "jgw", "jpeg": "jgw", "png": "pgw"}
MAGIC = {"tif": (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"), "jpg": (b"\xff\xd8\xff",), "png": (b"\x89PNG",)}


class OrthoError(ValueError):
    pass


def ortho_dir(oid: uuid.UUID | str) -> str:
    return os.path.join(get_settings().ortho_dir, str(oid))


def tile_url(o: Orthophoto) -> str | None:
    return f"/tiles/{o.id}/{{z}}/{{x}}/{{y}}.png" if o.status == "ready" else None


def out(o: Orthophoto) -> OrthophotoOut:
    return OrthophotoOut(id=str(o.id), name=o.name, source=o.source, captured_on=o.captured_on, georef=o.georef,
                         status=o.status, error=o.error, original_name=o.original_name, src_crs=o.src_crs,
                         residual_m=o.residual_m, width=o.width, height=o.height, bounds=o.bounds,
                         size_bytes=o.size_bytes, opacity=o.opacity, visible=o.visible, created_at=o.created_at,
                         tile_url=tile_url(o))


def parse_world(text: str) -> list[float]:
    vals = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    if len(vals) != 6:
        raise OrthoError("El archivo world debe tener 6 líneas numéricas (A, D, B, E, C, F).")
    try:
        nums = [float(v.replace(",", ".")) for v in vals]
    except ValueError as exc:
        raise OrthoError("El archivo world contiene valores no numéricos.") from exc
    if not all(math.isfinite(x) for x in nums) or nums[0] == 0 or nums[3] == 0:
        raise OrthoError("El archivo world no es válido (tamaño de píxel nulo).")
    return nums


def image_size(path: str, ext: str) -> tuple[int, int] | None:
    """Ancho y alto de un PNG o JPEG leyendo su cabecera."""
    with open(path, "rb") as fh:
        head = fh.read(32)
        if ext == "png" and head[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", head[16:24])
            return w, h
        if ext in ("jpg", "jpeg"):
            fh.seek(2)
            while True:
                b = fh.read(1)
                while b and b != b"\xff":
                    b = fh.read(1)
                while b == b"\xff":
                    b = fh.read(1)
                if not b:
                    return None
                marker = b[0]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    continue
                seg = fh.read(2)
                if len(seg) < 2:
                    return None
                length = struct.unpack(">H", seg)[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    data = fh.read(5)
                    h, w = struct.unpack(">HH", data[1:5])
                    return w, h
                fh.seek(length - 2, 1)
    return None


def _check_srs(code: str | None, default: int) -> str:
    if not code:
        return f"EPSG:{default}"
    c = code.strip().upper()
    if c.isdigit():
        c = f"EPSG:{c}"
    if not c.startswith("EPSG:") or not c[5:].isdigit():
        raise OrthoError("El sistema de coordenadas debe indicarse como EPSG:xxxx.")
    try:
        to_metric(int(c[5:]))
    except Exception as exc:  # noqa: BLE001
        raise OrthoError(f"{c} no es un sistema de coordenadas conocido.") from exc
    return c


def _save(upload: UploadFile, path: str, limit: int) -> int:
    size = 0
    with open(path, "wb") as fh:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise OrthoError(f"El archivo supera el límite de {limit // (1024 * 1024)} MB.")
            fh.write(chunk)
    return size


def enqueue(o: Orthophoto) -> None:
    try:
        get_redis().lpush(QUEUE, str(o.id))
    except Exception:  # noqa: BLE001 - el worker también revisa la base periódicamente
        pass


def upload(session: Session, project: Project, file: UploadFile, world: UploadFile | None, *, name: str | None,
           source: str | None, captured_on: date | None, src_crs: str | None) -> Orthophoto:
    s = get_settings()
    filename = os.path.basename(file.filename or "ortofoto")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in IMAGE_EXT:
        raise OrthoError("Formato no admitido: use GeoTIFF (.tif), o JPG/PNG (con archivo world o puntos de control).")
    oid = uuid.uuid4()
    folder = ortho_dir(oid)
    os.makedirs(folder, exist_ok=True)
    try:
        path = os.path.join(folder, f"original.{ext}")
        size = _save(file, path, s.max_ortho_mb * 1024 * 1024)
        with open(path, "rb") as fh:
            head = fh.read(8)
        key = "jpg" if ext == "jpeg" else ("tif" if ext == "tiff" else ext)
        if not any(head.startswith(m) for m in MAGIC[key]):
            raise OrthoError("El contenido del archivo no corresponde a su extensión.")
        world_vals = None
        georef = "geotiff"
        crs = None
        width = height = None
        if IMAGE_EXT[ext] == "image":
            dims = image_size(path, ext)
            if dims is None:
                raise OrthoError("No se pudo leer el tamaño de la imagen.")
            width, height = dims
            if world is not None:
                text = world.file.read(4096).decode("latin-1", errors="replace")
                world_vals = parse_world(text)
                with open(os.path.join(folder, f"original.{WORLD_EXT[ext]}"), "w") as fh:
                    fh.write("\n".join(repr(v) for v in world_vals) + "\n")
                georef = "worldfile"
            else:
                georef = "gcp"
            crs = _check_srs(src_crs, project.length_srid)
        o = Orthophoto(id=oid, project_id=project.id, name=(name or filename.rsplit(".", 1)[0])[:200],
                       source=source, captured_on=captured_on, georef=georef,
                       status="uploaded" if georef == "gcp" else "pending", original_name=filename[:255],
                       original_ext=ext, src_crs=crs, world=world_vals, size_bytes=size, width=width, height=height,
                       opacity=1.0, visible=True)
        session.add(o)
        session.commit()
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if o.status == "pending":
        enqueue(o)
    return o


def get(session: Session, project: Project, oid: uuid.UUID) -> Orthophoto:
    o = session.get(Orthophoto, oid)
    if o is None or o.project_id != project.id:
        raise NotFound("Ortofoto no encontrada")
    return o


def list_for(session: Session, project: Project) -> list[Orthophoto]:
    q = select(Orthophoto).where(Orthophoto.project_id == project.id)
    items = list(session.scalars(q))
    items.sort(key=lambda o: (o.captured_on or date.min, o.created_at), reverse=True)
    return items


def update(session: Session, o: Orthophoto, body: OrthophotoUpdate) -> Orthophoto:
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k in ("source", "captured_on"):
            setattr(o, k, v)
    session.commit()
    return o


def delete(session: Session, o: Orthophoto) -> None:
    folder = ortho_dir(o.id)
    session.delete(o)
    session.commit()
    shutil.rmtree(folder, ignore_errors=True)


def fit_gcps(gcps: list[Gcp], srid: int) -> GcpFit:
    """Ajuste imagen → terreno: similitud con 2 puntos, afín con 3 o más. Devuelve el archivo world equivalente
    (coordenadas del centro del píxel superior izquierdo) y los residuos en metros."""
    if len(gcps) < 2:
        raise OrthoError("Se necesitan al menos 2 puntos de control.")
    tr = to_metric(srid)
    xy = np.array([tr.transform(g.lon, g.lat) for g in gcps], dtype=float)
    px = np.array([[g.px, g.py] for g in gcps], dtype=float)
    if len(gcps) == 2 or len(gcps) < 3:
        # X = a·u − b·v + c ; Y = b·u + a·v + f   con v = −py (filas hacia abajo)
        rows, rhs = [], []
        for (u, py), (X, Y) in zip(px, xy):
            v = -py
            rows.append([u, -v, 1, 0]); rhs.append(X)
            rows.append([v, u, 0, 1]); rhs.append(Y)
        sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
        a, b, c, f = sol
        A, B, D, E = a, b, b, -a  # X = A·px + B·py + C ; Y = D·px + E·py + F
        C, F = c, f
        method = "similitud"
    else:
        M = np.column_stack([px, np.ones(len(gcps))])
        sx, *_ = np.linalg.lstsq(M, xy[:, 0], rcond=None)
        sy, *_ = np.linalg.lstsq(M, xy[:, 1], rcond=None)
        A, B, C = sx
        D, E, F = sy
        method = "afín"
    det = A * E - B * D
    if abs(det) < 1e-12:
        raise OrthoError("Los puntos de control no definen una transformación (¿puntos repetidos o alineados?).")
    pred = np.column_stack([A * px[:, 0] + B * px[:, 1] + C, D * px[:, 0] + E * px[:, 1] + F])
    res = np.hypot(*(pred - xy).T)
    world = [A, D, B, E, C + 0.5 * A + 0.5 * B, F + 0.5 * D + 0.5 * E]
    return GcpFit(method=method, world=[float(x) for x in world], srid=srid,
                  residuals_m=[round(float(r), 3) for r in res], rms_m=round(float(np.sqrt((res ** 2).mean())), 3))


def apply_gcps(session: Session, project: Project, o: Orthophoto, gcps: list[Gcp]) -> GcpFit:
    if o.georef == "geotiff":
        raise OrthoError("Un GeoTIFF ya está georreferenciado.")
    fit = fit_gcps(gcps, project.length_srid)
    folder = ortho_dir(o.id)
    ext = o.original_ext
    with open(os.path.join(folder, f"original.{WORLD_EXT[ext]}"), "w") as fh:
        fh.write("\n".join(repr(v) for v in fit.world) + "\n")
    o.world, o.gcps = fit.world, [g.model_dump() for g in gcps]
    o.residual_m, o.src_crs = fit.rms_m, f"EPSG:{fit.srid}"
    o.georef, o.status, o.error = "gcp", "pending", None
    session.commit()
    enqueue(o)
    return fit
