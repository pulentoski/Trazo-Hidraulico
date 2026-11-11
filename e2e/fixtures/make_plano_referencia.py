"""Genera e2e/fixtures/plano-referencia.png y su .json: foto sin coordenadas (600 × 400 píxeles, 0,5 m/píxel,
girada 10°) sobre la red «APR Demo», con puntos de control conocidos (lat/lon) para el asistente de ubicación.

Uso (imagen del worker, con GDAL y pyproj):
  docker run --rm -u $(id -u) -v $PWD/e2e/fixtures:/out -e PYTHONPATH=/app trazo-hidraulico/worker:local \
    python /out/make_plano_referencia.py /out
"""
import json
import math
import subprocess
import sys

import numpy as np
from pyproj import Transformer

out = sys.argv[1] if len(sys.argv) > 1 else "."
W, H, RES, ROT = 600, 400, 0.5, math.radians(10)
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True)
to_geo = Transformer.from_crs("EPSG:32719", "EPSG:4326", always_xy=True)
E0, N0 = to_utm.transform(-71.1450, -29.9420)
UL = (E0 + 250, N0 + 450)  # sobre la red de la demostración


def xy(px, py):
    u, v = px * RES, py * RES
    return UL[0] + u * math.cos(ROT) + v * math.sin(ROT), UL[1] + u * math.sin(ROT) - v * math.cos(ROT)


# Imagen: cuadrícula con marcas en las esquinas de referencia (fáciles de reconocer).
img = np.full((H, W, 3), 225, dtype=np.uint8)
img[::40, :, :] = 160
img[:, ::40, :] = 160
POINTS = [(60, 60), (540, 80), (300, 340)]
for px, py in POINTS:
    img[py - 6:py + 7, px - 6:px + 7] = (200, 40, 40)
ppm = f"{out}/plano.ppm"
with open(ppm, "wb") as fh:
    fh.write(f"P6 {W} {H} 255\n".encode() + img.tobytes())
subprocess.run(["gdal_translate", "-q", "-of", "PNG", ppm, f"{out}/plano-referencia.png"], check=True)
subprocess.run(["rm", "-f", ppm, f"{out}/plano-referencia.png.aux.xml"], check=True)
pts = []
for px, py in POINTS:
    lon, lat = to_geo.transform(*xy(px + 0.5, py + 0.5))
    pts.append({"px": px + 0.5, "py": py + 0.5, "lat": round(lat, 8), "lon": round(lon, 8)})
corners = [to_geo.transform(*xy(u, v)) for u, v in ((0, 0), (W, 0), (W, H), (0, H))]
json.dump({"width": W, "height": H, "res_m": RES, "rotation_deg": 10, "points": pts,
           "corners": [[round(a, 8), round(b, 8)] for a, b in corners]}, open(f"{out}/plano-referencia.json", "w"), indent=1)
print("ok", pts)
