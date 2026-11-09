"""Recorrido visual e2e de Trazo Hidráulico con Playwright (make test-e2e; fuera de make test).

Requiere la pila levantada (make up) en http://localhost:8080; ingresa con E2E_EMAIL/E2E_PASSWORD (make test-e2e
crea ese usuario administrador en la organización «Recorrido e2e»). Crea un proyecto
«APR Demo (e2e)» desde examples/apr-demo.xlsx, recorre menú, herramientas, importación Excel, ortofoto,
consultas, cuarteles, factibilidad, escenarios, simulación de 24 h, gráficos, deslizador de hora, diagnóstico,
mediciones y exportaciones, y toma capturas en tema claro y oscuro a 1440 y 1024 px (docs/capturas/).
Falla si hay errores de consola o solicitudes fallidas, y elimina el proyecto al terminar.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
import re
import sys
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:8080")
EMAIL = os.environ.get("E2E_EMAIL", "e2e@trazo.local")
PASSWORD = os.environ.get("E2E_PASSWORD", "Recorrido-e2e-2026")
ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "capturas"
DEMO = ROOT / "examples" / "apr-demo.xlsx"
ORTHO = ROOT / "e2e" / "fixtures" / "ortofoto.tif"
TOOLS = ["V", "B", "N", "T", "E", "R", "M", "X", "D", "C", "L", "G", "W", "F"]
IGNORED = [
    re.compile(r"/tiles/.+\.png"),  # teselas fuera de los límites de la ortofoto: 404 esperado
    re.compile(r"maps\.googleapis|gstatic"),
]

problems: list[str] = []


def log(msg: str) -> None:
    print(f"› {msg}", flush=True)


def watch(page: Page) -> None:
    def on_console(m):
        # Antes de ingresar, la consulta de sesión (/api/auth/me) responde 401: esperado. Cualquier otro 401
        # queda registrado por el observador de respuestas.
        if "status of 401" in m.text:
            return
        if m.type == "error" and not any(p.search(m.text) for p in IGNORED):
            problems.append(f"consola: {m.text} ({page.url})")

    def on_response(r):
        if r.status == 401 and r.url.endswith("/api/auth/me"):
            return
        if r.status >= 400 and not any(p.search(r.url) for p in IGNORED):
            problems.append(f"HTTP {r.status}: {r.request.method} {r.url}")

    page.on("console", on_console)
    page.on("pageerror", lambda e: problems.append(f"excepción: {e}"))
    page.on("response", on_response)
    page.on("requestfailed", lambda r: None if any(p.search(r.url) for p in IGNORED) or "downloads" in (r.failure or "")
            else problems.append(f"falló: {r.url} {r.failure}"))


def shot(page: Page, name: str, theme: str, width: int) -> None:
    page.wait_for_timeout(250)
    page.screenshot(path=str(SHOTS / f"{name}-{theme}-{width}.png"), full_page=False)


def set_theme(page: Page, theme: str) -> None:
    page.context.add_init_script(f"try {{ localStorage.setItem('trazo.theme', JSON.stringify('{theme}')) }} catch (e) {{}}")


def tab(page: Page, label: str) -> None:
    page.locator(".bottom .tabs button", has_text=re.compile(rf"^{label}")).first.click()


def wait_sim(page: Page) -> None:
    expect(page.locator(".status")).to_contain_text("Actualizado", timeout=30000)


def tour(page: Page, pid: str, theme: str, width: int, full: bool) -> None:
    set_theme(page, theme)
    page.goto(f"{BASE}/")
    expect(page.get_by_text("APR Demo (e2e)").first).to_be_visible()
    shot(page, "inicio", theme, width)
    page.goto(f"{BASE}/proyecto/{pid}")
    expect(page.locator(".net-layer")).to_be_visible()
    wait_sim(page)
    shot(page, "editor", theme, width)

    if full:
        log("herramientas")
        page.locator(".net-layer").hover()
        for k in TOOLS:
            page.keyboard.press(k)
            expect(page.locator(".tools button[aria-pressed=true] kbd")).to_have_text(k)
        page.keyboard.press("V")
        # Agregar un nudo con la herramienta y deshacer
        box = page.locator(".net-layer").bounding_box()
        page.keyboard.press("N")
        page.mouse.click(box["x"] + box["width"] * 0.12, box["y"] + box["height"] * 0.3)
        expect(page.locator(".props h3")).to_contain_text("Nudo")
        page.keyboard.press("Control+z")
        page.keyboard.press("V")

        log("importar Excel (vista previa)")
        page.get_by_role("button", name=re.compile("Planilla y SIG")).click()
        page.get_by_role("button", name="Importar Excel o CSV…").click()
        page.locator(".imp-form input[type=file]").set_input_files(str(DEMO))
        page.get_by_role("button", name="Vista previa").click()
        expect(page.locator(".imp-preview")).to_be_visible(timeout=20000)
        shot(page, "importar-excel", theme, width)
        page.keyboard.press("Escape")

        log("ortofoto")
        tab(page, "Capas")
        page.locator(".layers-tab input[type=file]").first.set_input_files(str(ORTHO))
        page.locator(".layers-tab").get_by_placeholder("Nombre", exact=True).fill("Ortofoto e2e")
        page.get_by_role("button", name="Subir").click()
        expect(page.locator(".layers-tab tbody tr").first).to_contain_text("lista", timeout=60000)
        page.locator(".layers-tab").get_by_role("button", name="Ver").first.click()
        page.wait_for_timeout(1200)
        shot(page, "ortofoto", theme, width)

    log("consultas")
    tab(page, "Consultas")
    page.locator(".query-form select").first.select_option("clientes")
    page.get_by_role("button", name="+ Condición").click()
    page.locator(".cond select").first.select_option("route")
    page.locator(".cond input").first.fill("3")
    page.get_by_role("button", name="Consultar").click()
    expect(page.locator(".query-res")).to_contain_text("10 de 30")
    shot(page, "consultas", theme, width)

    log("cuarteles")
    tab(page, "Cuarteles")
    expect(page.locator(".bottom .tbl tbody tr")).to_have_count(4, timeout=15000)
    page.locator(".bottom .tbl tbody tr", has_text="C-02").click()
    expect(page.locator(".cut-msg")).to_contain_text("Para cortar aquí")
    shot(page, "cuarteles", theme, width)

    if full:
        log("factibilidad")
        page.keyboard.press("F")
        hit = page.locator("polyline.hit").nth(8)
        b = hit.bounding_box()
        page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        dlg = page.get_by_role("dialog")
        expect(dlg).to_be_visible()
        dlg.locator("input").first.fill("0,5")
        dlg.locator("input").nth(1).fill("235")
        dlg.get_by_role("button", name="Evaluar factibilidad").click()
        expect(dlg.locator(".verdict")).to_be_visible(timeout=30000)
        shot(page, "factibilidad", theme, width)
        page.keyboard.press("Escape")
        page.keyboard.press("V")

        log("escenarios")
        tab(page, "Escenarios")
        page.get_by_role("button", name="Simular escenario").click()
        page.wait_for_timeout(2500)
        shot(page, "escenarios", theme, width)

    log("simulación 24 h, gráficos y hora")
    tab(page, "Simulación")
    expect(page.locator(".sim-tab")).to_contain_text("Curvas de modulación")
    shot(page, "simulacion", theme, width)
    tab(page, "Gráficos")
    expect(page.locator(".chart svg").first).to_be_visible()
    shot(page, "grafico-estanque", theme, width)
    if full:
        sel = page.locator(".charts-tab select").first
        for kind in ("pressure", "flow", "mass"):
            sel.select_option(kind)
            expect(page.locator(".chart svg").first).to_be_visible()
        shot(page, "grafico-masas", theme, width)
        sel.select_option("profile")
        selects = page.locator(".charts-tab select")
        selects.nth(1).select_option(label="E-1")
        selects.nth(2).select_option(label="J-9")
        expect(page.locator(".chart")).to_have_count(2)
        shot(page, "grafico-perfil", theme, width)
    slider = page.locator(".hour-slider input[type=range]")
    slider.fill("8")
    expect(page.locator(".hour-slider b")).to_have_text("8:00")
    shot(page, "hora-8", theme, width)

    log("diagnóstico")
    tab(page, "Diagnóstico")
    expect(page.locator(".diag-status")).to_be_visible(timeout=60000)
    shot(page, "diagnostico", theme, width)

    if full:
        log("mediciones")
        tab(page, "Mediciones")
        expect(page.locator(".meas-tab")).to_be_visible()
        shot(page, "mediciones", theme, width)

        log("pozo")
        page.get_by_label("Búsqueda rápida").fill("PZ-1")
        page.locator(".qs-results li").first.click()
        expect(page.locator(".props h3")).to_contain_text("Pozo")
        page.get_by_role("button", name="+ Datos de bombeo del pozo").click()
        page.locator(".props select").filter(has_text="Cota indicada").select_option(label="Estanque E-1 (rebalse)")
        page.locator(".props").get_by_role("button", name=re.compile("calcular$", re.I)).click()
        expect(page.locator(".props")).to_contain_text("H manométrica", timeout=30000)
        shot(page, "pozo", theme, width)

        log("perfil y organización")
        page.goto(f"{BASE}/perfil")
        expect(page.get_by_role("heading", name="Sesiones activas")).to_be_visible()
        shot(page, "perfil", theme, width)
        page.goto(f"{BASE}/organizacion")
        expect(page.get_by_role("heading", name="Auditoría")).to_be_visible()
        expect(page.locator("table").last).to_contain_text("login.ok")
        shot(page, "organizacion", theme, width)
        page.goto(f"{BASE}/proyecto/{pid}")
        wait_sim(page)

        log("exportaciones")
        for path in ("sig/export.xlsx", "export.dxf", "export.gpkg", "export.trazo", "export.inp", "report.html"):
            r = page.request.get(f"{BASE}/api/projects/{pid}/{path}")
            assert r.ok, f"{path}: {r.status}"
        page.get_by_role("button", name=re.compile("Planilla y SIG")).click()
        shot(page, "menu-exportar", theme, width)
        page.keyboard.press("Escape")


def totp(secret: str) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000).zfill(6)


def login(browser) -> dict:
    """Ingreso por la pantalla /login (con TOTP si el rol lo exige); devuelve el estado de sesión."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL")
    page = ctx.new_page()
    watch(page)
    page.goto(f"{BASE}/acerca-de")
    expect(page).to_have_url(re.compile(r"/login\?volver="))
    shot(page, "login", "light", 1440)
    page.get_by_label("Correo").fill(EMAIL)
    page.get_by_label("Contraseña").fill(PASSWORD)
    page.get_by_role("button", name="Ingresar").click()
    page.wait_for_url(re.compile(r"/(acerca-de|perfil)"), timeout=15000)
    if "/perfil" in page.url:  # el rol exige segundo factor: configurarlo
        log("configurando TOTP del usuario e2e")
        page.get_by_role("button", name="Configurar").click()
        secret = page.locator(".mono.small").first.inner_text().strip()
        page.get_by_label("Código de 6 dígitos").fill(totp(secret))
        page.get_by_role("button", name="Activar").click()
        expect(page.get_by_text("Activo.")).to_be_visible()
    state = ctx.storage_state()
    ctx.close()
    return state


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = login(browser)
        api = p.request.new_context(base_url=BASE, storage_state=state)
        r = api.post("/api/projects/import-excel", multipart={
            "file": {"name": "apr-demo.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     "buffer": DEMO.read_bytes()}, "name": "APR Demo (e2e)"})
        assert r.status == 201, r.text()
        pid = r.json()["project_id"]
        try:
            for i, (theme, width) in enumerate((("claro", 1440), ("oscuro", 1440), ("claro", 1024), ("oscuro", 1024))):
                log(f"== tema {theme}, {width} px ==")
                ctx = browser.new_context(viewport={"width": width, "height": 900}, accept_downloads=True, locale="es-CL",
                                          storage_state=state)
                page = ctx.new_page()
                watch(page)
                try:
                    tour(page, pid, "light" if theme == "claro" else "dark", width, full=(i == 0))
                except Exception:
                    page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
                    print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
                    raise
                ctx.close()
        finally:
            api.delete(f"/api/projects/{pid}")
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print(f"\n✔ Recorrido e2e sin errores. Capturas en {SHOTS.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
