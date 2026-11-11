"""Ortofotos grandes y georreferenciación: subida por partes reanudable, verificación de espacio en disco,
COG comprimido (WEBP calidad 85) con overviews, reducción de resolución, asistente de puntos de control con una
imagen de referencia (2 y 3 puntos, lat/lon o UTM) y .trazo con ortofotos, pérdidas y configuración del Resumen."""
import io
import json
import math
import os
import subprocess
import tempfile
import uuid
import zipfile
from collections import namedtuple

import numpy as np
import pytest
from pyproj import Transformer

from app.core.db import get_sessionmaker
from app.workers.ortho import process

SRID = 32719
UL_E, UL_N = 281000.0, 6686000.0
PIX = 0.5
W, H = 400, 300
ORTHO_DIR = os.environ.get("ORTHO_DIR", "/tmp/ortho")
to_geo = Transformer.from_crs(f"EPSG:{SRID}", "EPSG:4326", always_xy=True)
to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{SRID}", always_xy=True)


def _gdal(*args):
    subprocess.run(list(args), check=True, capture_output=True)


def _info(path):
    return json.loads(subprocess.run(["gdalinfo", "-json", path], capture_output=True, text=True, check=True).stdout)


def _process(oid):
    with get_sessionmaker()() as session:
        o = process(session, uuid.UUID(oid))
        return o.status, o.error


@pytest.fixture(scope="module")
def project(client):
    return client.post("/api/projects", json={"name": "Ortofotos grandes"}).json()["id"]


def _geotiff(path, w=W, h=H, pix=PIX):
    _gdal("gdal_create", "-of", "GTiff", "-outsize", str(w), str(h), "-bands", "3", "-burn", "120", "-burn", "160",
          "-burn", "90", "-a_srs", f"EPSG:{SRID}", "-a_ullr", str(UL_E), str(UL_N), str(UL_E + w * pix),
          str(UL_N - h * pix), "-ot", "Byte", path)


def _upload_parts(client, project, data: bytes, filename: str, part: int, **meta):
    r = client.post(f"/api/projects/{project}/orthophotos/uploads", json={"filename": filename, "size": len(data), **meta})
    assert r.status_code == 201, r.text
    st = r.json()
    oid = st["ortho"]["id"]
    assert st["ortho"]["status"] == "uploading" and st["offset"] == 0 and st["chunk_size"] > 0
    off = 0
    while off < len(data):
        r = client.put(f"/api/projects/{project}/orthophotos/{oid}/upload", params={"offset": off},
                       content=data[off:off + part], headers={"content-type": "application/octet-stream"})
        assert r.status_code == 200, r.text
        off = r.json()["offset"]
    return oid, r.json()


# ── Subida por partes ──


def test_subida_por_partes_reanudable_y_cog_webp(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "grande.tif")
        _geotiff(tif)
        data = open(tif, "rb").read()
    third = len(data) // 3 + 1
    r = client.post(f"/api/projects/{project}/orthophotos/uploads",
                    json={"filename": "grande.tif", "size": len(data), "name": "Vuelo grande", "source": "Dron"})
    oid = r.json()["ortho"]["id"]
    url = f"/api/projects/{project}/orthophotos/{oid}/upload"
    # Primera parte; luego se «corta» la conexión y el cliente consulta desde dónde retomar.
    assert client.put(url, params={"offset": 0}, content=data[:third]).json()["offset"] == third
    lst = client.get(f"/api/projects/{project}/orthophotos").json()
    item = next(x for x in lst if x["id"] == oid)
    assert item["status"] == "uploading" and item["upload_offset"] == third
    # Repetir la misma parte (reintento tras un corte) responde 409 con el byte desde el que seguir.
    dup = client.put(url, params={"offset": 0}, content=data[:third])
    assert dup.status_code == 409 and dup.json()["offset"] == third
    assert client.get(url).json()["offset"] == third
    assert client.put(url, params={"offset": third}, content=data[third:2 * third]).json()["offset"] == 2 * third
    done = client.put(url, params={"offset": 2 * third}, content=data[2 * third:]).json()
    assert done["complete"] and done["offset"] == len(data) and done["ortho"]["status"] == "pending"
    assert open(os.path.join(ORTHO_DIR, oid, "original.tif"), "rb").read() == data
    status, error = _process(oid)
    assert status == "ready", error
    meta = _info(os.path.join(ORTHO_DIR, oid, "cog.tif"))
    md = meta["metadata"]["IMAGE_STRUCTURE"]
    assert md["COMPRESSION"] == "WEBP" and md["LAYOUT"] == "COG"
    assert len(meta["bands"]) == 4  # RGB + transparencia fuera de la imagen


def test_limite_total_y_espacio_en_disco(client, project, monkeypatch):
    from app.core.config import get_settings
    from app.services import orthophotos

    big = get_settings().max_ortho_mb * 1024 * 1024 + 1
    r = client.post(f"/api/projects/{project}/orthophotos/uploads", json={"filename": "x.tif", "size": big})
    assert r.status_code == 413 and "ORTHO_MAX_MB" in r.json()["detail"]
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(orthophotos.shutil, "disk_usage", lambda p: Usage(10**10, 10**10 - 10**8, 10**8))
    r = client.post(f"/api/projects/{project}/orthophotos/uploads", json={"filename": "x.tif", "size": 50 * 1024 * 1024})
    assert r.status_code == 507
    assert "espacio en disco" in r.json()["detail"] and "150 MB" in r.json()["detail"]
    r = client.post(f"/api/projects/{project}/orthophotos/uploads", json={"filename": "x.exe", "size": 10})
    assert r.status_code == 422


def test_parte_excedida_o_contenido_falso(client, project):
    r = client.post(f"/api/projects/{project}/orthophotos/uploads", json={"filename": "f.tif", "size": 10})
    oid = r.json()["ortho"]["id"]
    url = f"/api/projects/{project}/orthophotos/{oid}/upload"
    assert client.put(url, params={"offset": 0}, content=b"x" * 11).status_code == 422
    st = client.put(url, params={"offset": 0}, content=b"no es tif!").json()
    assert st["ortho"]["status"] == "error" and "no corresponde" in st["ortho"]["error"]


def test_reducir_resolucion(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "fina.tif")
        _geotiff(tif, w=600, h=400, pix=0.05)  # 5 cm por píxel
        data = open(tif, "rb").read()
    oid, st = _upload_parts(client, project, data, "fina.tif", 1 << 20, target_res_cm=20)
    assert st["ortho"]["target_res_m"] == pytest.approx(0.2)
    status, error = _process(oid)
    assert status == "ready", error
    meta = _info(os.path.join(ORTHO_DIR, oid, "cog.tif"))
    lat = to_geo.transform(UL_E, UL_N)[1]
    ground = abs(meta["geoTransform"][1]) * math.cos(math.radians(lat))
    assert ground == pytest.approx(0.2, rel=0.03)  # 20 cm de terreno por píxel
    assert meta["size"][0] < 600 / 3


# ── Georreferenciación con puntos de control: imagen de referencia ──

# Imagen de referencia de 800 × 600 píxeles, girada 12° y con 0,25 m por píxel; esquina superior izquierda conocida.
ROT = math.radians(12)
RES = 0.25
REF_W, REF_H = 800, 600


def _ref_xy(px, py):
    """Posición UTM exacta de un píxel de la imagen de referencia."""
    u, v = px * RES, py * RES
    return UL_E + u * math.cos(ROT) + v * math.sin(ROT), UL_N + u * math.sin(ROT) - v * math.cos(ROT)


def _png(path, w, h):
    tif = path + ".tif"
    _gdal("gdal_create", "-of", "GTiff", "-outsize", str(w), str(h), "-bands", "3", "-burn", "70", "-ot", "Byte", tif)
    _gdal("gdal_translate", "-q", "-of", "PNG", tif, path)


def _ll(px, py):
    lon, lat = to_geo.transform(*_ref_xy(px, py))
    return {"px": px, "py": py, "lon": lon, "lat": lat}


def _utm(px, py):
    e, n = _ref_xy(px, py)
    return {"px": px, "py": py, "e": e, "n": n, "zone": 19, "south": True}


def _err_m(lonlat, px, py):
    x, y = to_utm.transform(*lonlat)
    ex, ey = _ref_xy(px, py)
    return math.hypot(x - ex, y - ey)


@pytest.fixture(scope="module")
def ref_image(client, project):
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "plano-referencia.png")
        _png(png, REF_W, REF_H)
        r = client.post(f"/api/projects/{project}/orthophotos", files={"file": ("plano-referencia.png", open(png, "rb"), "image/png")})
    assert r.status_code == 201
    return r.json()["id"]


def test_dos_puntos_posicion_esperada(client, project, ref_image):
    fit = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps",
                      json={"gcps": [_ll(40, 50), _ll(760, 540)]}).json()
    assert fit["method"] == "similitud" and fit["rms_m"] < 0.01 and fit["worst"] is None
    corners = [(0, 0), (REF_W, 0), (REF_W, REF_H), (0, REF_H)]
    for c, (px, py) in zip(fit["corners"], corners):
        assert _err_m(c, px, py) < 0.05  # esquinas de la imagen dentro de 5 cm
    # Un píxel de control que no se usó en el ajuste queda en su lugar.
    A, D, B, E, C, F = fit["world"]
    col, row = 500, 120  # el archivo world usa índices de píxel con origen en el centro del primero
    px, py = col + 0.5, row + 0.5
    x, y = A * col + B * row + C, D * col + E * row + F
    assert math.hypot(x - _ref_xy(px, py)[0], y - _ref_xy(px, py)[1]) < 0.05


def test_tres_puntos_utm_residuos_y_peor_punto(client, project, ref_image):
    pts = [_utm(30, 30), _utm(770, 40), _utm(400, 580)]
    fit = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps", json={"gcps": pts}).json()
    assert fit["method"] == "afín" and fit["rms_m"] < 0.01
    for (lon, lat), p in zip(fit["points"], pts):
        assert _err_m((lon, lat), p["px"], p["py"]) < 0.01  # UTM convertido a lat/lon sin pérdida
    for c, (px, py) in zip(fit["corners"], [(0, 0), (REF_W, 0), (REF_W, REF_H), (0, REF_H)]):
        assert _err_m(c, px, py) < 0.05
    # Cuatro puntos con 4 m de error en uno: es el peor y el RMS lo refleja.
    bad = dict(_utm(760, 560))
    bad["e"] += 4.0
    fit4 = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps", json={"gcps": [*pts, bad]}).json()
    assert fit4["worst"] == 3 and fit4["residuals_m"][3] == max(fit4["residuals_m"]) and fit4["rms_m"] > 0.5
    # Guardar los puntos sin procesar: quedan para retomar el ajuste.
    saved = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps", json={"gcps": pts, "save": True})
    assert saved.status_code == 200
    o = next(x for x in client.get(f"/api/projects/{project}/orthophotos").json() if x["id"] == ref_image)
    assert o["status"] == "uploaded" and len(o["gcps"]) == 3 and o["gcps"][0]["zone"] == 19
    # Aplicar y procesar: la ortofoto queda donde corresponde.
    assert client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps", json={"gcps": pts, "apply": True}).status_code == 200
    status, error = _process(ref_image)
    assert status == "ready", error
    o = next(x for x in client.get(f"/api/projects/{project}/orthophotos").json() if x["id"] == ref_image)
    w, s, e, n = o["bounds"]
    xs, ys = zip(*[_ref_xy(px, py) for px, py in ((0, 0), (REF_W, 0), (REF_W, REF_H), (0, REF_H))])
    lons, lats = zip(*[to_geo.transform(x, y) for x, y in zip(xs, ys)])
    for got, want in ((w, min(lons)), (e, max(lons)), (s, min(lats)), (n, max(lats))):
        assert abs(got - want) * 111_000 < 1.0  # dentro de 1 m


def test_puntos_invalidos(client, project, ref_image):
    r = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps",
                    json={"gcps": [{"px": 1, "py": 1}, _ll(10, 10)]})
    assert r.status_code == 422
    same = client.post(f"/api/projects/{project}/orthophotos/{ref_image}/gcps", json={"gcps": [_ll(10, 10), _ll(10, 10)]})
    assert same.status_code == 422 and "puntos" in same.json()["detail"]


# ── .trazo: ortofotos, eventos de pérdidas y configuración del Resumen ──


def _trazo_doc(content: bytes) -> tuple[dict, set[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return json.loads(z.read("trazo.json")), set(z.namelist())


def test_trazo_ida_y_vuelta_con_ortofotos_perdidas_y_resumen(client):
    from tests.test_sig_excel import create_demo

    pid = create_demo(client, "APR trazo completo")
    settings = client.get(f"/api/projects/{pid}/summary/settings").json()
    settings.update({"pressure_ranges": [10, 25, 45], "area_margin_m": 75, "service_life": {**settings["service_life"], "PVC": 45},
                     "prices": [{"material": "*", "dn_max": 200, "price_m": 70000}], "life_verified": True, "top_n": 20})
    assert client.put(f"/api/projects/{pid}/summary/settings", json=settings).status_code == 200
    with tempfile.TemporaryDirectory() as tmp:
        tif = os.path.join(tmp, "o.tif")
        _geotiff(tif)
        geo_bytes = open(tif, "rb").read()
        png = os.path.join(tmp, "plano.png")
        _png(png, REF_W, REF_H)
        png_bytes = open(png, "rb").read()
    g = client.post(f"/api/projects/{pid}/orthophotos", files={"file": ("o.tif", geo_bytes, "image/tiff")},
                    data={"name": "Vuelo 2025", "source": "Dron", "captured_on": "2025-01-15"}).json()
    client.patch(f"/api/projects/{pid}/orthophotos/{g['id']}", json={"opacity": 0.6, "visible": False})
    p = client.post(f"/api/projects/{pid}/orthophotos", files={"file": ("plano.png", png_bytes, "image/png")}).json()
    pts = [_utm(30, 30), _utm(770, 40), _utm(400, 580)]
    client.post(f"/api/projects/{pid}/orthophotos/{p['id']}/gcps", json={"gcps": pts, "save": True})

    a = client.get(f"/api/projects/{pid}/export.trazo", params={"ortofotos": True})
    assert a.status_code == 200
    doc_a, names = _trazo_doc(a.content)
    assert len(doc_a["leak_events"]) == 8 and doc_a["project"]["summary_settings"]["area_margin_m"] == 75
    files = {o["name"]: o.get("file") for o in doc_a["orthophotos"]}
    assert all(files.values()) and set(files.values()) <= names
    # Sin la opción, solo referencias (sin archivos).
    light, light_names = _trazo_doc(client.get(f"/api/projects/{pid}/export.trazo").content)
    assert not any(n.startswith("ortofotos/") for n in light_names) and all("file" not in o for o in light["orthophotos"])

    r = client.post("/api/projects/import-trazo", files={"file": ("apr.trazo", a.content, "application/zip")})
    assert r.status_code == 201, r.text
    pid2 = r.json()["project"]["id"]
    b = client.get(f"/api/projects/{pid2}/export.trazo", params={"ortofotos": True})
    doc_b, _ = _trazo_doc(b.content)
    assert doc_b["leak_events"] == doc_a["leak_events"]
    assert doc_b["project"]["summary_settings"] == doc_a["project"]["summary_settings"]
    assert client.get(f"/api/projects/{pid2}/summary/settings").json()["pressure_ranges"] == [10, 25, 45]
    keys = ("name", "source", "captured_on", "georef", "original_name", "original_ext", "src_crs", "world", "gcps",
            "width", "height", "size_bytes", "opacity", "visible", "target_res_m")
    by_a = {o["name"]: o for o in doc_a["orthophotos"]}
    by_b = {o["name"]: o for o in doc_b["orthophotos"]}
    assert set(by_a) == set(by_b)
    for name in by_a:
        assert {k: by_a[name][k] for k in keys} == {k: by_b[name][k] for k in keys}, name
    orthos2 = {o["name"]: o for o in client.get(f"/api/projects/{pid2}/orthophotos").json()}
    assert orthos2["Vuelo 2025"]["status"] == "pending" and orthos2["plano"]["status"] == "uploaded"
    assert open(os.path.join(ORTHO_DIR, orthos2["Vuelo 2025"]["id"], "original.tif"), "rb").read() == geo_bytes
    assert open(os.path.join(ORTHO_DIR, orthos2["plano"]["id"], "original.png"), "rb").read() == png_bytes
    status, error = _process(orthos2["Vuelo 2025"]["id"])
    assert status == "ready", error
    assert np.isclose(len(client.get(f"/api/projects/{pid2}/leaks").json()), 8)
