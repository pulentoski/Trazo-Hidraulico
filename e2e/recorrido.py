"""Recorrido visual e2e de Trazo Hidráulico con Playwright (make test-e2e; fuera de make test).

Requiere la pila levantada (make up) en http://localhost:8080; ingresa con E2E_EMAIL/E2E_PASSWORD (make test-e2e
crea ese usuario administrador en la organización «Recorrido e2e»). Crea un proyecto
«APR Demo (e2e)» desde examples/apr-demo.xlsx, recorre menú, panel general (Resumen), paneles plegables,
herramientas, importación Excel, ortofoto, consultas, cuarteles, factibilidad, escenarios, simulación de 24 h,
gráficos, deslizador de hora, diagnóstico, mediciones y exportaciones, y toma capturas en tema claro y oscuro a
1440 y 1024 px (docs/capturas/). Falla si hay errores de consola o solicitudes fallidas, y elimina el proyecto
al terminar.
"""
from __future__ import annotations

import base64
import hashlib
import json
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
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "e2e-plataforma@trazo.local")
PASSWORD = os.environ.get("E2E_PASSWORD", "Recorrido-e2e-2026")
ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / os.environ.get("E2E_SHOTS", "docs/capturas")
INSECURE = BASE.startswith("https://")  # instancia con certificado interno de Caddy
DEMO = ROOT / "examples" / "apr-demo.xlsx"
ORTHO = ROOT / "e2e" / "fixtures" / "ortofoto.tif"
PLANO = ROOT / "e2e" / "fixtures" / "plano-referencia.png"  # foto sin coordenadas (make_plano_referencia.py)
PLANO_REF = ROOT / "e2e" / "fixtures" / "plano-referencia.json"
TOOLS = ["V", "B", "N", "T", "E", "R", "M", "X", "D", "C", "L", "G", "W", "F"]
IGNORED = [
    re.compile(r"/tiles/.+\.png"),  # teselas fuera de los límites de la ortofoto: 404 esperado
    re.compile(r"maps\.googleapis|gstatic"),
    re.compile(r"tile\.openstreetmap\.org|server\.arcgisonline\.com|nominatim\.openstreetmap\.org"),  # servicios externos del mapa OSM
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
    """Abre una pestaña del panel inferior; si no cabe en la barra, desde el menú «Más ▾»."""
    btn = page.locator(".bottom .tabs > button", has_text=re.compile(rf"^{label}"))
    if btn.count():
        btn.first.click()
        return
    page.locator(".bottom .tabs-more").click()
    page.locator(".tabs-more-pop button", has_text=re.compile(rf"^{label}")).first.click()


def wait_sim(page: Page) -> None:
    expect(page.locator(".status")).to_contain_text("Actualizado", timeout=30000)


def tour(page: Page, pid: str, theme: str, width: int, full: bool) -> None:
    set_theme(page, theme)
    page.goto(f"{BASE}/")
    expect(page.get_by_text("APR Demo (e2e)").first).to_be_visible()
    card = page.get_by_role("article", name="APR Demo (e2e)")
    expect(card).to_contain_text("30 clientes")
    page.get_by_label("Buscar proyecto").fill("zzz-no-existe")
    expect(page.get_by_text("Ningún proyecto coincide")).to_be_visible()
    page.get_by_label("Buscar proyecto").fill("demo (e2e")
    expect(card).to_be_visible()
    page.get_by_label("Buscar proyecto").fill("")
    shot(page, "inicio", theme, width)
    page.get_by_role("button", name="Menú de usuario").click()
    expect(page.get_by_role("menuitem", name="Cerrar sesión")).to_be_visible()
    page.keyboard.press("Escape")
    if full:
        page.get_by_role("button", name=re.compile("^Nuevo proyecto")).first.click()
        expect(page.get_by_role("dialog", name="Nuevo proyecto")).to_be_visible()
        page.keyboard.press("Escape")
    page.goto(f"{BASE}/proyecto/{pid}")
    expect(page.locator(".net-layer")).to_be_visible()
    wait_sim(page)
    shot(page, "editor", theme, width)

    log("resumen")
    summary = page.locator(".summary-tab")
    expect(summary.locator(".summary-grid")).to_be_visible(timeout=30000)
    expect(page.locator(".bottom .tabs > button.on")).to_have_text("Resumen")  # primera pestaña al abrir
    expect(summary.get_by_label("Clientes sobre cota")).to_contain_text("C-025")
    expect(summary.get_by_label("Pérdidas y filtraciones")).to_contain_text("P-06")
    expect(summary.get_by_label("Mantenimiento a futuro")).to_contain_text("P-08")
    summary.get_by_role("button", name="Zonas por presión").first.click()
    summary.get_by_role("button", name="Área operacional").first.click()
    expect(page.locator(".net-layer path.ov-zone").first).to_be_attached()
    expect(page.locator(".net-layer path.ov-area").first).to_be_attached()
    summary.get_by_label("Clientes", exact=True).locator(".num-link").nth(1).click()  # activos → lista y mapa
    expect(summary.locator(".summary-list")).to_contain_text("C-001")
    expect(page.locator(".net-layer .hl-point").first).to_be_attached()
    shot(page, "resumen", theme, width)
    summary.get_by_label("Pérdidas y filtraciones").evaluate("el => el.scrollIntoView({block: 'start'})")
    shot(page, "resumen-perdidas", theme, width)
    summary.locator(".summary-list").get_by_role("button", name="Cerrar lista").click()
    summary.get_by_role("button", name="Zonas por presión").first.click()
    summary.get_by_role("button", name="Área operacional").first.click()

    log("panel inferior: maximizar, plegar y tamaño normal")
    page.get_by_role("button", name="Maximizar el panel inferior").click()
    expect(page.locator(".bottom.maxed")).to_be_visible()
    page.wait_for_timeout(300)
    shot(page, "resumen-maximizado", theme, width)
    page.get_by_role("button", name="Tamaño normal del panel inferior").click()
    expect(page.locator(".bottom.maxed")).to_have_count(0)

    log("paneles plegados y desplegados")
    page.locator(".tools-fold").click()
    page.get_by_role("button", name="Plegar el panel inferior").click()
    expect(page.locator(".tools.collapsed")).to_be_visible()
    expect(page.locator(".bottom.collapsed")).to_be_visible()
    page.wait_for_timeout(300)
    shot(page, "paneles-plegados", theme, width)
    page.locator(".tools-fold").click()
    page.get_by_role("button", name="Desplegar el panel inferior").click()
    expect(page.locator(".props .sec.open")).to_have_count(1)  # por defecto, solo la sección más usada
    page.locator(".props").get_by_role("button", name="Expandir todo").click()
    expect(page.locator(".props .sec:not(.open)")).to_have_count(0)
    page.wait_for_timeout(300)
    shot(page, "paneles-desplegados", theme, width)
    page.locator(".props").get_by_role("button", name="Contraer todo").click()
    expect(page.locator(".props .sec.open")).to_have_count(0)
    page.locator(".props .sec-toggle", has_text="Opciones hidráulicas").click()
    expect(page.locator(".props .sec.open")).to_have_count(1)

    if full:
        log("resumen: registro de pérdidas y exportaciones")
        losses = summary.get_by_label("Pérdidas y filtraciones")
        tab(page, "Resumen")
        expect(losses).to_contain_text("8 eventos")
        losses.get_by_label("Tramo").select_option("P-10")
        losses.get_by_label("Caudal estimado (L/s)").fill("0,04")
        losses.get_by_label("Observación").fill("Recorrido e2e")
        losses.get_by_role("button", name="Agregar").click()
        expect(losses).to_contain_text("9 eventos")
        losses.get_by_role("row", name=re.compile("Recorrido e2e")).get_by_role("button").last.click()
        expect(losses).to_contain_text("8 eventos")
        for path in ("summary.xlsx", "summary.html", "summary/area.geojson", "summary/zones.geojson", "leaks/template.xlsx"):
            r = page.request.get(f"{BASE}/api/projects/{pid}/{path}")
            assert r.ok, f"{path}: {r.status}"
        log("panel inferior redimensionable y recordado")
        handle = page.get_by_role("separator", name="Cambiar la altura del panel inferior")
        h0 = page.locator(".bottom").bounding_box()["height"]
        hb = handle.bounding_box()
        page.mouse.move(hb["x"] + hb["width"] / 2, hb["y"] + hb["height"] / 2)
        page.mouse.down()
        page.mouse.move(hb["x"] + hb["width"] / 2, hb["y"] - 120, steps=6)
        page.mouse.up()
        h1 = page.locator(".bottom").bounding_box()["height"]
        assert h1 > h0 + 80, (h0, h1)
        page.mouse.move(hb["x"] + hb["width"] / 2, hb["y"] - 120)
        page.mouse.down()
        page.mouse.move(hb["x"] + hb["width"] / 2, 2000, steps=6)  # tamaño mínimo
        page.mouse.up()
        assert page.locator(".bottom").bounding_box()["height"] >= 139
        handle.focus()
        for _ in range(6):
            page.keyboard.press("ArrowUp")
        h2 = page.locator(".bottom").bounding_box()["height"]
        page.reload()
        wait_sim(page)
        assert abs(page.locator(".bottom").bounding_box()["height"] - h2) < 2  # se recuerda por usuario
        handle.dblclick()  # doble clic: vuelve al tamaño normal
        expect(page.locator(".props .sec.open")).to_have_count(1)  # el estado de las secciones se recuerda
        expect(page.locator(".props .sec.open .sec-toggle")).to_have_text("Opciones hidráulicas")

    tab(page, "Alertas")  # el resto del recorrido usa el mapa con el panel inferior de altura normal

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

        log("asistente de ubicación de una foto sin coordenadas")
        ref = json.loads(PLANO_REF.read_text())
        layers = page.locator(".layers-tab")
        layers.locator("input[type=file]").first.set_input_files(str(PLANO))
        layers.get_by_placeholder("Nombre", exact=True).fill("Plano e2e")
        layers.get_by_role("button", name="Subir").click()
        wiz = page.get_by_role("dialog", name="Asistente de ubicación de la foto")
        expect(wiz).to_be_visible(timeout=30000)
        expect(wiz).to_contain_text("Elija puntos fáciles de reconocer")
        shot(page, "georref-guia", theme, width)
        wiz.get_by_role("button", name="Comenzar").click()
        img = wiz.locator(".photo-box img")
        expect(img).to_be_visible()
        for i, pt in enumerate(ref["points"]):
            img.scroll_into_view_if_needed()
            b = img.bounding_box()
            img.click(position={"x": pt["px"] / ref["width"] * b["width"], "y": pt["py"] / ref["height"] * b["height"]})
            expect(wiz.locator(".wizard-hint")).to_contain_text(f"Punto {i + 1}")
            wiz.get_by_label("Latitud").fill(str(pt["lat"]).replace(".", ","))
            wiz.get_by_label("Longitud").fill(str(pt["lon"]).replace(".", ","))
            wiz.get_by_role("button", name="Usar coordenadas").click()
        expect(wiz.locator(".fit-summary")).to_contain_text("Ajuste con 3 o más puntos")
        rms = float(re.search(r"\(RMS\) ([\d,]+) m", wiz.locator(".fit-summary").inner_text()).group(1).replace(",", "."))
        assert rms < 1.5, f"error medio {rms} m"
        expect(wiz.locator(".fit-summary")).to_contain_text("pasa exacta")  # 3 puntos: ajuste afín exacto
        # Un 4.º punto con unos 6 m de error al este: queda marcado como el de mayor error.
        (tl, tr_, _br, bl) = ref["corners"]
        u, v = 150.5 / ref["width"], 300.5 / ref["height"]
        lon4 = tl[0] + u * (tr_[0] - tl[0]) + v * (bl[0] - tl[0]) + 6 / 96_500
        lat4 = tl[1] + u * (tr_[1] - tl[1]) + v * (bl[1] - tl[1])
        img.click(position={"x": 150.5 / ref["width"] * b["width"], "y": 300.5 / ref["height"] * b["height"]})
        wiz.get_by_label("Latitud").fill(str(round(lat4, 8)).replace(".", ","))
        wiz.get_by_label("Longitud").fill(str(round(lon4, 8)).replace(".", ","))
        wiz.get_by_role("button", name="Usar coordenadas").click()
        expect(wiz.locator(".worst-row")).to_have_count(1)
        expect(wiz.locator(".worst-row")).to_contain_text("mayor error")
        wiz.locator(".worst-row").get_by_role("button", name="Borrar punto 4").click()
        expect(wiz.locator(".worst-row")).to_have_count(0)
        expect(page.locator(".gcp-preview img")).to_be_attached()
        wiz.get_by_label("Opacidad de la vista previa").fill("0.5")
        shot(page, "georref-asistente", theme, width)
        wiz.get_by_role("button", name="Guardar puntos").click()
        wiz.get_by_role("button", name="Aplicar").click()
        expect(wiz).to_be_hidden()
        expect(layers.locator("tbody tr", has_text="Plano e2e")).to_contain_text("lista", timeout=60000)
        layers.locator("tbody tr", has_text="Plano e2e").get_by_role("button", name="Ver").click()
        page.wait_for_timeout(1200)
        shot(page, "georref-aplicada", theme, width)

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


def config_tour(browser, state: dict, theme: str, width: int) -> None:
    """Configuración → Mapa base con el superadministrador: guardar una key de prueba (cifrada), ver su estado y borrarla."""
    ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="es-CL", storage_state=state,
                              ignore_https_errors=INSECURE, reduced_motion="reduce")
    page = ctx.new_page()
    watch(page)
    set_theme(page, theme)
    page.goto(f"{BASE}/configuracion")
    sec = page.get_by_label("Mapa base")
    expect(sec.get_by_text("Administración de la plataforma")).to_be_visible()
    had = sec.get_by_text("Key guardada").count() and sec.locator(".kv.compact dd").first.inner_text().strip() not in ("—", "")
    if not had:  # solo si la plataforma no tiene una key real: se guarda una de prueba y se borra al final
        sec.get_by_label("API key de Google Maps").fill("AIzaSyE2E-prueba-0000000000000000000")
        sec.get_by_role("button", name="Guardar").click()
        expect(sec.locator(".kv.compact")).to_contain_text("AIza…0000")
    shot(page, "configuracion", theme, width)
    if not had:
        page.once("dialog", lambda d: d.accept())
        sec.get_by_role("button", name="Borrar").click()
        expect(sec.locator(".kv.compact dd").first).to_have_text("—")
    ctx.close()


def login(browser, email: str = EMAIL) -> dict:
    """Ingreso por la pantalla /login (con TOTP si el rol lo exige); devuelve el estado de sesión."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL", ignore_https_errors=INSECURE)
    page = ctx.new_page()
    watch(page)
    page.goto(f"{BASE}/acerca-de")
    expect(page).to_have_url(re.compile(r"/login\?volver="))
    shot(page, "login", "light", 1440)
    page.get_by_label("Correo").fill(email)
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
        admin_state = login(browser, ADMIN_EMAIL)
        api = p.request.new_context(base_url=BASE, storage_state=state, ignore_https_errors=INSECURE)
        r = api.post("/api/projects/import-excel", multipart={
            "file": {"name": "apr-demo.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     "buffer": DEMO.read_bytes()}, "name": "APR Demo (e2e)"})
        assert r.status == 201, r.text()
        pid = r.json()["project_id"]
        try:
            for i, (theme, width) in enumerate((("claro", 1440), ("oscuro", 1440), ("claro", 1024), ("oscuro", 1024))):
                log(f"== tema {theme}, {width} px ==")
                ctx = browser.new_context(viewport={"width": width, "height": 900}, accept_downloads=True, locale="es-CL", reduced_motion="reduce",
                                          storage_state=state, ignore_https_errors=INSECURE)
                page = ctx.new_page()
                watch(page)
                try:
                    tour(page, pid, "light" if theme == "claro" else "dark", width, full=(i == 0))
                except Exception:
                    page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
                    print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
                    raise
                ctx.close()
                config_tour(browser, admin_state, "light" if theme == "claro" else "dark", width)
        finally:
            api.delete(f"/api/projects/{pid}")
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print(f"\n✔ Recorrido e2e sin errores. Capturas en {SHOTS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
