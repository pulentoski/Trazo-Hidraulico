"""Prueba de una ortofoto grande (≈ 800 MB) contra la pila levantada (make test-ortho-grande).

Sube por partes (con un corte simulado y retoma desde la última parte), espera el procesamiento del worker,
pide teselas al proxy y toma una captura del editor con la ortofoto. Imprime los tiempos en JSON.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://localhost:8080")
EMAIL = os.environ.get("E2E_EMAIL", "e2e@trazo.local")
PASSWORD = os.environ.get("E2E_PASSWORD", "Recorrido-e2e-2026")
FILE = sys.argv[1]
SHOT = sys.argv[2] if len(sys.argv) > 2 else None
# La cookie de sesión es «Secure»: urllib no la reenviaría por http://localhost, así que se maneja a mano.
COOKIES: dict[str, str] = {}
opener = urllib.request.build_opener()


def req(method: str, path: str, body=None, ctype="application/json"):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    headers = {"Content-Type": ctype} if data is not None else {}
    if COOKIES:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in COOKIES.items())
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with opener.open(r, timeout=600) as resp:
            for h in resp.headers.get_all("Set-Cookie") or []:
                k, _, rest = h.partition("=")
                COOKIES[k.strip()] = rest.split(";", 1)[0]
            raw = resp.read()
            return resp.status, (json.loads(raw) if resp.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw


def log(msg: str) -> None:
    print(f"› {msg}", flush=True)


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def main() -> int:
    size = os.path.getsize(FILE)
    st, _ = req("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert st == 200, st
    st, proj = req("POST", "/api/projects", {"name": "Ortofoto grande (prueba)"})
    pid = proj["id"]
    result: dict = {"size_mb": round(size / 1024 / 1024, 1)}
    try:
        st, up = req("POST", f"/api/projects/{pid}/orthophotos/uploads",
                     {"filename": os.path.basename(FILE), "size": size, "name": "Ortofoto 800 MB", "source": "sintética GDAL"})
        assert st == 201, up
        oid, chunk = up["ortho"]["id"], up["chunk_size"]
        log(f"subida por partes de {result['size_mb']} MB en partes de {chunk // 1024 // 1024} MB")
        t0 = time.time()
        offset, cut, parts = 0, False, 0
        with open(FILE, "rb") as fh:
            while offset < size:
                if not cut and offset > size * 0.3:
                    # Corte simulado: el cliente pierde la respuesta de una parte y consulta desde dónde seguir.
                    cut = True
                    fh.seek(offset)
                    req("PUT", f"/api/projects/{pid}/orthophotos/{oid}/upload?offset={offset}", fh.read(chunk), "application/octet-stream")
                    st, state = req("GET", f"/api/projects/{pid}/orthophotos/{oid}/upload")
                    log(f"corte simulado en {offset // 1024 // 1024} MB: el servidor ya tiene {state['offset'] // 1024 // 1024} MB, se retoma desde ahí")
                    st, dup = req("PUT", f"/api/projects/{pid}/orthophotos/{oid}/upload?offset={offset}", b"x", "application/octet-stream")
                    assert st == 409 and dup["offset"] == state["offset"], (st, dup)
                    offset = state["offset"]
                    result["resume_at_mb"] = round(offset / 1024 / 1024, 1)
                    continue
                fh.seek(offset)
                st, state = req("PUT", f"/api/projects/{pid}/orthophotos/{oid}/upload?offset={offset}", fh.read(chunk), "application/octet-stream")
                assert st == 200, (st, state)
                offset = state["offset"]
                parts += 1
        result["upload_s"] = round(time.time() - t0, 1)
        result["upload_mb_s"] = round(size / 1024 / 1024 / result["upload_s"], 1)
        result["parts"] = parts
        log(f"subida completa en {result['upload_s']} s ({result['upload_mb_s']} MB/s); estado {state['ortho']['status']}")
        t1 = time.time()
        seen = set()
        while True:
            st, lst = req("GET", f"/api/projects/{pid}/orthophotos")
            o = next(x for x in lst if x["id"] == oid)
            if o["status"] not in seen:
                seen.add(o["status"])
                log(f"estado: {o['status']} ({round(time.time() - t1)} s)")
            if o["status"] in ("ready", "error"):
                break
            if time.time() - t1 > 3600:
                raise TimeoutError("el procesamiento superó 1 hora")
            time.sleep(2)
        assert o["status"] == "ready", o["error"]
        result["processing_s"] = round(time.time() - t1, 1)
        cog = None
        w, s, e, n = o["bounds"]
        lon, lat = (w + e) / 2, (s + n) / 2
        tiles = {}
        for z in (13, 16, 19):
            x, y = tile_xy(lon, lat, z)
            t = time.time()
            st, png = req("GET", f"/tiles/{oid}/{z}/{x}/{y}.png")
            assert st == 200 and png[:8] == b"\x89PNG\r\n\x1a\n", (z, st)
            tiles[z] = round((time.time() - t) * 1000)
        result["tile_ms"] = tiles
        result["bounds"] = o["bounds"]
        log(f"procesada en {result['processing_s']} s; teselas z13/z16/z19 en {tiles} ms")
        if SHOT:
            from playwright.sync_api import expect, sync_playwright

            with sync_playwright() as p:
                b = p.chromium.launch()
                ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")
                for k, v in COOKIES.items():
                    ctx.add_cookies([{"name": k, "value": v, "url": BASE}])
                page = ctx.new_page()
                page.goto(f"{BASE}/proyecto/{pid}")
                page.locator(".bottom .tabs button", has_text="Capas").click()
                row = page.locator(".layers-tab tbody tr", has_text="Ortofoto 800 MB")
                expect(row).to_contain_text("lista")
                row.get_by_role("button", name="Ver").click()
                page.wait_for_timeout(4000)
                page.screenshot(path=SHOT)
                b.close()
            log(f"captura: {SHOT}")
        print("RESULTADO " + json.dumps(result), flush=True)
        return 0
    finally:
        req("DELETE", f"/api/projects/{pid}")


if __name__ == "__main__":
    sys.exit(main())
