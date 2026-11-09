"""Ortofotos: GeoTIFF y JPG con archivo world quedan en la posición correcta (tolerancia en metros),
ajuste por puntos de control con error residual y validación del archivo."""
import os
import subprocess
import tempfile
import uuid

import pytest
from pyproj import Transformer

from app.core.db import get_sessionmaker
from app.workers.ortho import process

SRID = 32719
UL_E, UL_N = 281000.0, 6686000.0  # esquina superior izquierda (UTM 19S, La Serena)
PIX = 0.5  # m/píxel
W, H = 400, 300
TOL_M = 1.0  # tolerancia de posición


def _gdal(*args):
    subprocess.run(list(args), check=True, capture_output=True)


def _check_position(oid: str):
    """La envolvente del COG (EPSG:3857) coincide con la de la imagen original reproyectada, en metros de terreno."""
    import json
    import math

    cog = os.path.join(os.environ.get("ORTHO_DIR", "/tmp/ortho"), oid, "cog.tif")
    info = json.loads(subprocess.run(["gdalinfo", "-json", cog], capture_output=True, text=True, check=True).stdout)
    cc = info["cornerCoordinates"]
    gx0, gy1 = cc["upperLeft"]
    gx1, gy0 = cc["lowerRight"]
    tr = Transformer.from_crs(f"EPSG:{SRID}", "EPSG:3857", always_xy=True)
    edge = []
    for k in range(21):
        t = k / 20
        edge += [(UL_E + t * W * PIX, UL_N), (UL_E + t * W * PIX, UL_N - H * PIX),
                 (UL_E, UL_N - t * H * PIX), (UL_E + W * PIX, UL_N - t * H * PIX)]
    pts = [tr.transform(*p) for p in edge]
    ex0, ex1 = min(p[0] for p in pts), max(p[0] for p in pts)
    ey0, ey1 = min(p[1] for p in pts), max(p[1] for p in pts)
    lat = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(gx0, gy0)[1]
    k = math.cos(math.radians(lat))  # metros de terreno por unidad Web Mercator
    for got, want in ((gx0, ex0), (gx1, ex1), (gy0, ey0), (gy1, ey1)):
        assert abs(got - want) * k <= TOL_M, (got, want, abs(got - want) * k)
    assert info["wgs84Extent"]["coordinates"][0]


@pytest.fixture(scope="module")
def project(client):
    return client.post("/api/projects", json={"name": "Ortofotos"}).json()["id"]


def _process(oid: str):
    with get_sessionmaker()() as session:
        o = process(session, uuid.UUID(oid))
        return o.status, o.error, o.bounds


def test_geotiff_en_posicion_correcta(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "orto.tif")
        _gdal("gdal_create", "-of", "GTiff", "-outsize", str(W), str(H), "-bands", "3", "-burn", "120", "-burn", "160",
              "-burn", "90", "-a_srs", f"EPSG:{SRID}", "-a_ullr", str(UL_E), str(UL_N), str(UL_E + W * PIX),
              str(UL_N - H * PIX), "-ot", "Byte", tif)
        r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("orto.tif", open(tif, "rb"), "image/tiff")},
                        data={"name": "Vuelo 2024", "source": "Dron municipal", "captured_on": "2024-03-01"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["georef"] == "geotiff" and o["status"] == "pending" and o["tile_url"] is None
    status, error, bounds = _process(o["id"])
    assert status == "ready", error
    assert len(bounds) == 4
    _check_position(o["id"])
    lst = client.get(f"/api/projects/{project}/orthophotos").json()
    item = next(x for x in lst if x["id"] == o["id"])
    assert item["tile_url"] == f"/tiles/{o['id']}/{{z}}/{{x}}/{{y}}.png"
    upd = client.patch(f"/api/projects/{project}/orthophotos/{o['id']}", json={"opacity": 0.4, "visible": False})
    assert upd.json()["opacity"] == 0.4 and upd.json()["visible"] is False
    cog = os.path.join(os.environ.get("ORTHO_DIR", "/tmp/ortho"), o["id"], "cog.tif")
    info = subprocess.run(["gdalinfo", cog], capture_output=True, text=True, check=True).stdout
    assert "LAYOUT=COG" in info and "3857" in info


def test_jpg_con_archivo_world_en_posicion_correcta(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "a.tif")
        jpg = os.path.join(tmp, "foto.jpg")
        _gdal("gdal_create", "-of", "GTiff", "-outsize", str(W), str(H), "-bands", "3", "-burn", "200", "-ot", "Byte", tif)
        _gdal("gdal_translate", "-q", "-of", "JPEG", tif, jpg)
        for side in os.listdir(tmp):
            if side.endswith(".aux.xml"):
                os.remove(os.path.join(tmp, side))
        world = "\n".join(map(str, [PIX, 0.0, 0.0, -PIX, UL_E + PIX / 2, UL_N - PIX / 2])) + "\n"
        r = client.post(f"/api/projects/{project}/orthophotos",
                        files={"file": ("foto.jpg", open(jpg, "rb"), "image/jpeg"),
                               "world": ("foto.jgw", world.encode(), "text/plain")},
                        data={"src_crs": f"EPSG:{SRID}"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["georef"] == "worldfile" and o["width"] == W and o["height"] == H
    status, error, bounds = _process(o["id"])
    assert status == "ready", error
    assert len(bounds) == 4
    _check_position(o["id"])


def test_puntos_de_control_error_residual_y_proceso(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "a.tif")
        png = os.path.join(tmp, "plano.png")
        _gdal("gdal_create", "-of", "GTiff", "-outsize", str(W), str(H), "-bands", "3", "-burn", "50", "-ot", "Byte", tif)
        _gdal("gdal_translate", "-q", "-of", "PNG", tif, png)
        r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("plano.png", open(png, "rb"), "image/png")})
    assert r.status_code == 201
    o = r.json()
    assert o["georef"] == "gcp" and o["status"] == "uploaded"
    tr = Transformer.from_crs(f"EPSG:{SRID}", "EPSG:4326", always_xy=True)

    def gcp(px, py, de=0.0):
        lon, lat = tr.transform(UL_E + px * PIX + de, UL_N - py * PIX)
        return {"px": px, "py": py, "lon": lon, "lat": lat}

    two = client.post(f"/api/projects/{project}/orthophotos/{o['id']}/gcps", json={"gcps": [gcp(0, 0), gcp(400, 300)]})
    assert two.status_code == 200 and two.json()["method"] == "similitud" and two.json()["rms_m"] < 0.01
    # Tres puntos con un error de 3 m en uno: el residuo lo refleja.
    three = client.post(f"/api/projects/{project}/orthophotos/{o['id']}/gcps",
                        json={"gcps": [gcp(0, 0), gcp(400, 0), gcp(0, 300), gcp(400, 300, de=3.0)]})
    fit = three.json()
    assert fit["method"] == "afín" and 0.3 < fit["rms_m"] < 3.0 and len(fit["residuals_m"]) == 4
    ok = client.post(f"/api/projects/{project}/orthophotos/{o['id']}/gcps",
                     json={"gcps": [gcp(0, 0), gcp(400, 0), gcp(0, 300)], "apply": True})
    assert ok.status_code == 200
    status, error, bounds = _process(o["id"])
    assert status == "ready", error
    assert len(bounds) == 4
    _check_position(o["id"])


def test_archivo_invalido_o_falso_se_rechaza(client, project):
    r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("x.exe", b"MZ....", "application/octet-stream")})
    assert r.status_code == 422
    r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("x.tif", b"no es un tiff", "image/tiff")})
    assert r.status_code == 422 and "no corresponde" in r.json()["detail"]
    # Un TIFF sin georreferencia queda en error al procesarlo.
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "plain.tif")
        _gdal("gdal_create", "-of", "GTiff", "-outsize", "10", "10", "-bands", "1", "-ot", "Byte", tif)
        r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("plain.tif", open(tif, "rb"), "image/tiff")})
    status, error, _ = _process(r.json()["id"])
    assert status == "error" and "georreferen" in error
    assert client.delete(f"/api/projects/{project}/orthophotos/{r.json()['id']}").status_code == 204
