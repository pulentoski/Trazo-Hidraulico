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
from app.schemas.sig import Gcp, GcpFit, OrthophotoOut, OrthophotoUpdate, UploadInit, UploadState
from app.services.errors import NotFound
from app.services.geometry import to_metric

QUEUE = "trazo:ortho:jobs"
IMAGE_EXT = {"tif": "geotiff", "tiff": "geotiff", "jpg": "image", "jpeg": "image", "png": "image"}
WORLD_EXT = {"jpg": "jgw", "jpeg": "jgw", "png": "pgw"}
MAGIC = {"tif": (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"), "jpg": (b"\xff\xd8\xff",), "png": (b"\x89PNG",)}


class OrthoError(ValueError):
    pass


class DiskFull(OrthoError):
    """No hay espacio en disco suficiente para guardar y procesar la ortofoto."""


class OffsetMismatch(OrthoError):
    """La parte no empieza donde terminó la anterior (el cliente debe retomar desde `offset`)."""

    def __init__(self, offset: int):
        super().__init__(f"La parte debe empezar en el byte {offset}.")
        self.offset = offset


def ortho_dir(oid: uuid.UUID | str) -> str:
    return os.path.join(get_settings().ortho_dir, str(oid))


def tile_url(o: Orthophoto) -> str | None:
    return f"/tiles/{o.id}/{{z}}/{{x}}/{{y}}.png" if o.status == "ready" else None


def out(o: Orthophoto) -> OrthophotoOut:
    return OrthophotoOut(id=str(o.id), name=o.name, source=o.source, captured_on=o.captured_on, georef=o.georef,
                         status=o.status, error=o.error, original_name=o.original_name, src_crs=o.src_crs,
                         residual_m=o.residual_m, width=o.width, height=o.height, bounds=o.bounds,
                         size_bytes=o.size_bytes, opacity=o.opacity, visible=o.visible, created_at=o.created_at,
                         tile_url=tile_url(o), upload_offset=o.upload_offset if o.status == "uploading" else None,
                         target_res_m=o.target_res_m, gcps=[Gcp.model_validate(g) for g in o.gcps] if o.gcps else None)


def _mb(n: float) -> str:
    return f"{n / 1024 / 1024:,.0f} MB".replace(",", ".")


def check_disk(size: int, factor: float | None = None, path: str | None = None) -> None:
    """Exige espacio libre ≥ tamaño × factor (original, intermedios y COG) antes de recibir o procesar."""
    s = get_settings()
    factor = s.ortho_disk_factor if factor is None else factor
    folder = path or s.ortho_dir
    os.makedirs(folder, exist_ok=True)
    free = shutil.disk_usage(folder).free
    need = int(size * factor)
    if free < need:
        raise DiskFull(f"No hay espacio en disco suficiente para esta ortofoto: se necesitan unos {_mb(need)} "
                       f"(≈ {factor:g} veces el archivo) y hay {_mb(free)} libres. Libere espacio (elimine "
                       "ortofotos que no use) o pida ampliar el disco del servidor.")


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
    from app.services.auth import check_limit

    oid = uuid.uuid4()
    folder = ortho_dir(oid)
    os.makedirs(folder, exist_ok=True)
    try:
        path = os.path.join(folder, f"original.{ext}")
        size = _save(file, path, s.max_ortho_mb * 1024 * 1024)
        check_limit(session, project.org_id, "ortho", extra=size)
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


def _ext_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in IMAGE_EXT:
        raise OrthoError("Formato no admitido: use GeoTIFF (.tif), o JPG/PNG (con archivo world o puntos de control).")
    return ext


def init_upload(session: Session, project: Project, body: UploadInit) -> UploadState:
    """Crea la ortofoto en estado «uploading» y su carpeta; las partes se agregan con append_chunk."""
    s = get_settings()
    filename = os.path.basename(body.filename)
    ext = _ext_of(filename)
    limit = s.max_ortho_mb * 1024 * 1024
    if body.size > limit:
        raise OrthoError(f"El archivo ({_mb(body.size)}) supera el límite de {s.max_ortho_mb} MB (ORTHO_MAX_MB).")
    check_disk(body.size)
    from app.services.auth import check_limit

    check_limit(session, project.org_id, "ortho", extra=body.size)
    world_vals = parse_world(body.world) if body.world else None
    if world_vals is not None and IMAGE_EXT[ext] != "image":
        raise OrthoError("El archivo world solo se usa con imágenes JPG o PNG.")
    crs = _check_srs(body.src_crs, project.length_srid) if IMAGE_EXT[ext] == "image" else None
    oid = uuid.uuid4()
    folder = ortho_dir(oid)
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, f"original.{ext}"), "wb").close()
    if world_vals is not None:
        with open(os.path.join(folder, f"original.{WORLD_EXT[ext]}"), "w") as fh:
            fh.write("\n".join(repr(v) for v in world_vals) + "\n")
    georef = "geotiff" if IMAGE_EXT[ext] == "geotiff" else ("worldfile" if world_vals else "gcp")
    o = Orthophoto(id=oid, project_id=project.id, name=(body.name or filename.rsplit(".", 1)[0])[:200],
                   source=body.source, captured_on=body.captured_on, georef=georef, status="uploading",
                   original_name=filename[:255], original_ext=ext, src_crs=crs, world=world_vals,
                   size_bytes=body.size, upload_offset=0, opacity=1.0, visible=True,
                   target_res_m=body.target_res_cm / 100 if body.target_res_cm else None)
    session.add(o)
    session.commit()
    return upload_state(o)


def upload_state(o: Orthophoto) -> UploadState:
    off = (o.upload_offset or 0) if o.status == "uploading" else o.size_bytes
    return UploadState(ortho=out(o), offset=off, size=o.size_bytes, chunk_size=get_settings().ortho_part_mb * 1024 * 1024,
                       complete=o.status != "uploading")


def append_chunk(session: Session, project: Project, o: Orthophoto, offset: int, data: bytes) -> UploadState:
    """Agrega una parte en `offset` (debe coincidir con lo ya recibido). Al completar, valida y encola."""
    if o.status != "uploading":
        return upload_state(o)
    path = os.path.join(ortho_dir(o.id), f"original.{o.original_ext}")
    current = os.path.getsize(path) if os.path.exists(path) else 0
    if offset != current:
        if o.upload_offset != current:
            o.upload_offset = current
            session.commit()
        raise OffsetMismatch(current)
    if current + len(data) > o.size_bytes:
        raise OrthoError("La parte excede el tamaño declarado del archivo.")
    max_part = 2 * get_settings().ortho_part_mb * 1024 * 1024
    if len(data) > max_part:
        raise OrthoError(f"Cada parte puede tener hasta {_mb(max_part)}.")
    with open(path, "ab") as fh:
        fh.write(data)
    o.upload_offset = current + len(data)
    session.commit()
    if o.upload_offset == o.size_bytes:
        _finalize(session, o, path)
    return upload_state(o)


def _finalize(session: Session, o: Orthophoto, path: str) -> None:
    """Archivo completo: verifica el contenido y deja la ortofoto en cola (o lista para puntos de control)."""
    ext = o.original_ext
    with open(path, "rb") as fh:
        head = fh.read(8)
    key = "jpg" if ext == "jpeg" else ("tif" if ext == "tiff" else ext)
    if not any(head.startswith(m) for m in MAGIC[key]):
        o.status, o.error, o.upload_offset = "error", "El contenido del archivo no corresponde a su extensión.", None
        session.commit()
        return
    if IMAGE_EXT[ext] == "image":
        dims = image_size(path, ext)
        if dims is None:
            o.status, o.error, o.upload_offset = "error", "No se pudo leer el tamaño de la imagen.", None
            session.commit()
            return
        o.width, o.height = dims
    o.upload_offset = None
    o.status = "uploaded" if o.georef == "gcp" else "pending"
    session.commit()
    if o.status == "pending":
        enqueue(o)


def purge_stale_uploads(session: Session, hours: float = 48) -> int:
    """Elimina subidas abandonadas (sin partes nuevas en `hours` horas)."""
    from datetime import datetime, timedelta, timezone

    limit = datetime.now(timezone.utc) - timedelta(hours=hours)
    n = 0
    for o in session.scalars(select(Orthophoto).where(Orthophoto.status == "uploading")):
        if (o.updated_at or o.created_at) < limit:
            delete(session, o)
            n += 1
    return n


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


def gcp_lonlat(g: Gcp) -> tuple[float, float]:
    """Coordenadas geográficas del punto (convierte UTM E/N + huso si no trae lat/lon)."""
    if g.lon is not None and g.lat is not None:
        return g.lon, g.lat
    epsg = (32700 if g.south else 32600) + int(g.zone)
    from app.services.geometry import from_metric

    lon, lat = from_metric(epsg).transform(g.e, g.n)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise OrthoError("Coordenadas UTM fuera de rango.")
    return lon, lat


def fit_gcps(gcps: list[Gcp], srid: int, size: tuple[int, int] | None = None) -> GcpFit:
    """Ajuste imagen → terreno: similitud con 2 puntos, afín con 3 o más. Devuelve el archivo world equivalente
    (coordenadas del centro del píxel superior izquierdo), los residuos en metros, el peor punto y las esquinas
    de la imagen en lon/lat (vista previa)."""
    if len(gcps) < 2:
        raise OrthoError("Se necesitan al menos 2 puntos de control.")
    tr = to_metric(srid)
    ll = [gcp_lonlat(g) for g in gcps]
    xy = np.array([tr.transform(lon, lat) for lon, lat in ll], dtype=float)
    px = np.array([[g.px, g.py] for g in gcps], dtype=float)
    BAD_POINTS = ("Los puntos de control no definen una transformación: use puntos distintos y separados entre sí "
                  "(no todos en una misma línea).")
    for i in range(len(gcps)):
        for j in range(i):
            if np.hypot(*(px[i] - px[j])) < 1 or np.hypot(*(xy[i] - xy[j])) < 0.01:
                raise OrthoError(f"Los puntos {j + 1} y {i + 1} están repetidos. " + BAD_POINTS)
    if len(gcps) >= 3 and np.linalg.matrix_rank(np.column_stack([px, np.ones(len(gcps))]), tol=1e-6) < 3:
        raise OrthoError(BAD_POINTS)
    if len(gcps) < 3:
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
    if abs(det) < 1e-12 or not np.isfinite(det):
        raise OrthoError(BAD_POINTS)
    pred = np.column_stack([A * px[:, 0] + B * px[:, 1] + C, D * px[:, 0] + E * px[:, 1] + F])
    res = np.hypot(*(pred - xy).T)
    world = [A, D, B, E, C + 0.5 * A + 0.5 * B, F + 0.5 * D + 0.5 * E]
    corners = None
    if size and size[0] and size[1]:
        from app.services.geometry import from_metric

        back = from_metric(srid)
        w, h = size
        corners = [tuple(float(v) for v in back.transform(A * u + B * v + C, D * u + E * v + F))
                   for u, v in ((0, 0), (w, 0), (w, h), (0, h))]
    worst = int(np.argmax(res)) if len(gcps) >= 3 else None
    return GcpFit(method=method, world=[float(x) for x in world], srid=srid,
                  residuals_m=[round(float(r), 3) for r in res], rms_m=round(float(np.sqrt((res ** 2).mean())), 3),
                  worst=worst, points=[(float(lon), float(lat)) for lon, lat in ll], corners=corners)


def _size_of(o: Orthophoto) -> tuple[int, int] | None:
    return (o.width, o.height) if o.width and o.height else None


def save_gcps(session: Session, project: Project, o: Orthophoto, gcps: list[Gcp]) -> GcpFit:
    """Guarda los puntos (sin procesar) para retomar el ajuste después."""
    fit = fit_gcps(gcps, project.length_srid, _size_of(o))
    o.gcps = [g.model_dump() for g in gcps]
    session.commit()
    return fit


def apply_gcps(session: Session, project: Project, o: Orthophoto, gcps: list[Gcp]) -> GcpFit:
    if o.georef == "geotiff":
        raise OrthoError("Un GeoTIFF ya está georreferenciado.")
    if o.status in ("uploading", "processing"):
        raise OrthoError("La imagen todavía se está subiendo o procesando.")
    fit = fit_gcps(gcps, project.length_srid, _size_of(o))
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
