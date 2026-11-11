"""Worker de ortofotos: valida con GDAL, reproyecta a EPSG:3857 y genera un Cloud Optimized GeoTIFF.

Uso: python -m app.workers.ortho   (espera trabajos en Redis y revisa la base cada 30 s por pendientes).
"""
from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import time
import uuid

from sqlalchemy import select

import redis

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import Orthophoto
from app.services.orthophotos import QUEUE, DiskFull, check_disk, ortho_dir, purge_stale_uploads

log = logging.getLogger("trazo.ortho")
# Sin acceso a red desde GDAL (los .jgw/.pgw se leen del mismo directorio que la imagen).
# Memoria acotada: caché de bloques (GDAL_CACHEMAX) y memoria de trabajo de gdalwarp (-wm) configurables.
GDAL_ENV = {**os.environ, "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".none", "GDAL_HTTP_TIMEOUT": "1",
            "GDAL_NUM_THREADS": "ALL_CPUS", "GDAL_CACHEMAX": str(get_settings().ortho_gdal_cachemax_mb)}
TIMEOUT_S = 4 * 3600
QUALITY = "85"


class ProcessError(RuntimeError):
    pass


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S, env=GDAL_ENV)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        raise ProcessError(msg[-1] if msg else f"{args[0]} falló")
    return proc.stdout


def info(path: str) -> dict:
    return json.loads(_run(["gdalinfo", "-json", path]))


def build_cog(o: Orthophoto) -> tuple[list[float], int, int]:
    """Genera cog.tif y devuelve (límites WGS84 [oeste, sur, este, norte], ancho, alto del original)."""
    folder = ortho_dir(o.id)
    src = os.path.join(folder, f"original.{o.original_ext}")
    tmp = os.path.join(folder, "georef.vrt")
    cog = os.path.join(folder, "cog.tif")
    part = os.path.join(folder, "cog.part.tif")
    meta = info(src)
    width, height = meta["size"]
    if o.georef == "geotiff":
        if not meta.get("coordinateSystem", {}).get("wkt"):
            raise ProcessError("El GeoTIFF no tiene sistema de coordenadas (no está georreferenciado).")
        if "geoTransform" not in meta and not meta.get("gcps"):
            raise ProcessError("El GeoTIFF no tiene georreferencia.")
        warp_src = src
    else:
        if not o.src_crs:
            raise ProcessError("Falta el sistema de coordenadas del archivo world.")
        _run(["gdal_translate", "-q", "-of", "VRT", "-a_srs", o.src_crs, src, tmp])
        if "geoTransform" not in info(tmp):
            raise ProcessError("No se encontró el archivo world de la imagen.")
        warp_src = tmp
    bands = meta.get("bands", [])
    byte = bool(bands) and all(b.get("type") == "Byte" for b in bands)
    has_alpha = any(b.get("colorInterpretation") == "Alpha" for b in bands)
    color = len(bands) - (1 if has_alpha else 0)
    args = ["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:3857", "-r", "bilinear", "-of", "COG",
            "-wm", str(get_settings().ortho_warp_mem_mb), "-wo", "NUM_THREADS=ALL_CPUS",
            "-co", "BIGTIFF=IF_SAFER", "-co", "OVERVIEWS=AUTO", "-co", "NUM_THREADS=ALL_CPUS"]
    if byte and color == 3:
        # Color de 8 bits: WEBP calidad 85 (con transparencia fuera de la imagen) y overviews.
        args += ["-co", "COMPRESS=WEBP", "-co", f"QUALITY={QUALITY}"]
    else:
        args += ["-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2"]
    if not has_alpha and len(bands) in (1, 3):
        args.append("-dstalpha")
    tr = target_res(o, info(warp_src) if warp_src != src else meta)
    if tr:
        args += ["-tr", str(tr), str(tr)]
    _run(args + [warp_src, part])
    os.replace(part, cog)
    if os.path.exists(tmp):
        os.remove(tmp)
    m = info(cog)
    ring = m["wgs84Extent"]["coordinates"][0]
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    return [min(lons), min(lats), max(lons), max(lats)], width, height


def target_res(o: Orthophoto, meta: dict) -> float | None:
    """Tamaño de celda en EPSG:3857 para la resolución reducida pedida (m de terreno / cos(latitud)).
    None si no se pidió o si la imagen ya es más gruesa que eso."""
    if not o.target_res_m:
        return None
    try:
        ring = meta["wgs84Extent"]["coordinates"][0]
        lat = sum(p[1] for p in ring) / len(ring)
    except (KeyError, IndexError, ZeroDivisionError):
        return None
    wkt = meta.get("coordinateSystem", {}).get("wkt", "")
    gt = meta.get("geoTransform")
    if gt and "PROJCRS" in wkt and "metre" in wkt:
        native = (abs(gt[1]) * abs(gt[5])) ** 0.5
        if native >= o.target_res_m * 0.98:
            return None
    return o.target_res_m / max(math.cos(math.radians(lat)), 1e-6)


def process(session, oid: uuid.UUID) -> Orthophoto | None:
    o = session.get(Orthophoto, oid)
    if o is None or o.status not in ("pending", "processing"):
        return o
    o.status, o.error = "processing", None
    session.commit()
    try:
        try:
            check_disk(o.size_bytes, factor=2.0, path=ortho_dir(o.id))  # el original ya está en disco
        except DiskFull as exc:
            raise ProcessError(str(exc)) from exc
        bounds, w, h = build_cog(o)
        o.bounds, o.width, o.height, o.status = bounds, w, h, "ready"
    except (ProcessError, subprocess.TimeoutExpired, KeyError, ValueError, OSError) as exc:
        o.status, o.error = "error", f"No se pudo procesar la ortofoto: {exc}"[:2000]
        log.warning("ortofoto %s: %s", oid, exc)
    session.commit()
    return o


def main() -> None:  # pragma: no cover - bucle del servicio
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("worker de ortofotos iniciado")
    maker = get_sessionmaker()
    queue = redis.Redis.from_url(get_settings().redis_url, socket_timeout=30, socket_connect_timeout=5)
    last_scan = 0.0
    while True:
        oid = None
        try:
            queue.set("trazo:worker:heartbeat", str(time.time()), ex=600)  # latido (Ajustes → Sistema)
            item = queue.brpop(QUEUE, timeout=10)
            oid = uuid.UUID(item[1].decode() if isinstance(item[1], bytes) else item[1]) if item else None
        except Exception as exc:  # noqa: BLE001
            log.warning("cola no disponible: %s", exc)
            time.sleep(5)
        with maker() as session:
            ids = [oid] if oid else []
            if time.time() - last_scan > 30:
                last_scan = time.time()
                try:
                    purge_stale_uploads(session)
                except Exception as exc:  # noqa: BLE001
                    log.warning("limpieza de subidas abandonadas: %s", exc)
                ids += list(session.scalars(select(Orthophoto.id).where(Orthophoto.status.in_(("pending",
                                                                                                "processing")))))
            for x in dict.fromkeys(ids):
                process(session, x)


if __name__ == "__main__":
    main()
