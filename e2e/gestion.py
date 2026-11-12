"""Página «Gestión» y coordenadas en el mapa (make test-e2e, después del recorrido visual).

Sobre un «APR Demo» nuevo (planilla con 12 meses de registros): acceso desde el inicio y desde el editor, recorrido
por las 7 pestañas con capturas en tema claro y oscuro, filtros (período, sector y ruta), detalle y exportación de
una tabla, importación Excel de un registro con vista previa y errores por fila, metas, informe mensual y «ver en el
mapa». En el editor: buscar una coordenada (queda marcada), crear un grifo por coordenadas UTM y moverlo editando sus
coordenadas; la barra inferior muestra la coordenada del cursor. Falla con errores de consola o solicitudes fallidas.
"""
from __future__ import annotations

import io
import json
import re
import sys

from openpyxl import Workbook
from playwright.sync_api import Page, expect, sync_playwright

from recorrido import BASE, DEMO, INSECURE, ROOT, SHOTS, log, login, problems, set_theme, shot, watch

NAME = "APR Demo (gestión e2e)"
TABS = ["Operación", "Clientes y consumo", "Pérdidas", "Activos y mantenimiento", "Cumplimiento", "Planificación", "Equipo"]
SLUG = {"Operación": "operacion", "Clientes y consumo": "clientes", "Pérdidas": "perdidas", "Activos y mantenimiento": "activos",
        "Cumplimiento": "cumplimiento", "Planificación": "planificacion", "Equipo": "equipo"}


def download(page: Page, locator) -> str:
    """Descarga con un enlace: el navegador aborta la navegación (ERR_ABORTED) y eso no es un error de la app."""
    n = len(problems)
    with page.expect_download() as dl:
        locator.click()
    name = dl.value.suggested_filename
    problems[n:] = [x for x in problems[n:] if "ERR_ABORTED" not in x]
    return name


def card(page: Page, label: str):
    return page.locator(f'article.kpi-card[aria-label="{label}"]')


def value_of(page: Page, label: str) -> float:
    txt = page.locator(f'article.kpi-tile[aria-label="{label}"] .kpi-value b').inner_text().strip().replace(".", "").replace(",", ".")
    return float(txt)


def wait_tab(page: Page) -> None:
    expect(page.locator(".gestion-body[aria-busy='false'] .kpi-card").first).to_be_visible(timeout=60000)
    page.wait_for_timeout(150)


def open_tab(page: Page, label: str) -> None:
    page.get_by_role("tab", name=label).click()
    expect(page.get_by_role("tab", name=label)).to_have_attribute("aria-selected", "true")
    wait_tab(page)


def chlorine_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Cloro"
    for r in (["Fecha y hora", "Punto", "Cloro libre", "Observación"], ["2026-10-30 09:00", "J-5", 0.7, "e2e"],
              ["2026-10-30 10:00", "J-9", "0,45", None], ["2026-10-30", "J-11", "mucho", None]):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def tour_gestion(page: Page, pid: str, theme: str, width: int, full: bool) -> None:
    set_theme(page, theme)
    page.goto(f"{BASE}/")
    page.get_by_role("article", name=NAME).get_by_role("button", name="Gestión", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/proyecto/{pid}/gestion"))
    expect(page.get_by_role("heading", name=re.compile("Gestión"))).to_be_visible()
    wait_tab(page)
    for t in TABS:
        log(f"gestión: {t} ({theme}, {width} px)")
        open_tab(page, t)
        expect(page.locator(".kpi-card").first).to_be_visible()
        shot(page, f"gestion-{SLUG[t]}", theme, width)
    if not full:
        return

    log("filtros: período, sector y ruta")
    open_tab(page, "Clientes y consumo")
    total = value_of(page, "Consumo facturado")
    page.get_by_label("Ruta").select_option("1")
    wait_tab(page)
    expect(page).to_have_url(re.compile(r"ruta=1"))
    for _ in range(40):  # el valor cambia cuando termina el recálculo del filtro
        if value_of(page, "Consumo facturado") < total:
            break
        page.wait_for_timeout(250)
    assert value_of(page, "Consumo facturado") < total, "el filtro de ruta no redujo el consumo"
    page.get_by_label("Ruta").select_option("")
    page.get_by_role("group", name="Período").get_by_role("button", name="Trimestre").click()
    wait_tab(page)
    expect(page.get_by_label("Desde")).to_have_value("2026-08-01")
    page.get_by_role("group", name="Período").get_by_role("button", name="Personalizado").click()
    page.get_by_label("Desde").fill("2026-01-01")
    wait_tab(page)
    expect(page.locator(".gestion-filters")).to_contain_text("Comparado con 2025-")
    page.get_by_role("group", name="Período").get_by_role("button", name="Año").click()
    wait_tab(page)
    open_tab(page, "Operación")
    page.get_by_label("Sector").select_option("Alto")
    wait_tab(page)
    expect(page.locator('article.kpi-tile[aria-label="Presión mínima medida"] .kpi-value b')).not_to_have_text("—")
    page.get_by_label("Sector").select_option("")
    wait_tab(page)

    log("detalle y exportación de una tabla")
    c = card(page, "Presión mínima medida")
    c.get_by_role("button", name="Detalle").click()
    expect(c.locator(".gtable table")).to_be_visible()
    name = download(page, c.locator("footer").get_by_role("link", name="Excel"))
    assert name.endswith("operacion-presion.xlsx"), name

    log("importación Excel de cloro con vista previa y errores por fila")
    open_tab(page, "Cumplimiento")
    panel = page.locator('details[data-record="cloro"]')
    panel.locator("summary").click()
    panel.get_by_label("Importar Cloro residual").set_input_files(
        {"name": "cloro.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "buffer": chlorine_xlsx()})
    pv = panel.get_by_role("region", name="Vista previa de la importación")
    expect(pv).to_contain_text("2 filas válidas")
    expect(pv).to_contain_text("1 con errores")
    expect(pv.locator("tr.row-error")).to_contain_text("Cloro libre")
    shot(page, "gestion-importacion", theme, width)
    pv.get_by_role("button", name="Importar 2 filas válidas").click()
    expect(page.locator(".toast").last).to_contain_text("2 filas nuevas")
    expect(panel.locator("summary")).to_contain_text("210 filas")

    log("metas")
    page.get_by_role("button", name="Metas").click()
    dlg = page.get_by_role("dialog", name="Metas e indicadores")
    expect(dlg).to_be_visible()
    dlg.get_by_label("Agua no contabilizada: verificada").check()
    dlg.get_by_role("button", name="Guardar metas").click()
    expect(page.locator(".toast").last).to_contain_text("Metas guardadas")

    log("informe mensual")
    href = page.get_by_role("link", name="Informe mensual").get_attribute("href")
    rep = page.context.new_page()
    watch(rep)
    rep.goto(f"{BASE}{href}")
    expect(rep.get_by_role("heading", name=re.compile(f"Informe mensual de gestión — {re.escape(NAME)}"))).to_be_visible()
    for t in TABS:
        expect(rep.get_by_role("heading", name=t, exact=True)).to_be_visible()
    expect(rep.locator(".meta")).to_contain_text("Versión del modelo: 1")
    rep.screenshot(path=str(SHOTS / f"gestion-informe-{theme}-{width}.png"), full_page=False)
    rep.close()
    assert download(page, page.get_by_role("link", name="Informe Excel")).endswith(".xlsx")

    log("ver en el mapa (mapa de calor de fugas)")
    open_tab(page, "Pérdidas")
    card(page, "Eventos de fuga").get_by_role("button", name="Ver en el mapa").click()
    expect(page).to_have_url(re.compile(rf"/proyecto/{pid}$"))
    expect(page.locator(".map-note")).to_contain_text("Gestión · Eventos de fuga")
    expect(page.locator(".net-layer .heat-link").first).to_be_attached(timeout=20000)
    shot(page, "gestion-ver-en-mapa", theme, width)
    page.locator(".map-note").get_by_role("button", name="Quitar resaltado").click()
    expect(page.locator(".net-layer .heat-link")).to_have_count(0)


def tour_coordinates(page: Page, pid: str, theme: str, width: int, api) -> None:
    set_theme(page, theme)
    page.goto(f"{BASE}/proyecto/{pid}")
    expect(page.locator(".net-layer g.node").first).to_be_attached(timeout=30000)
    expect(page.locator(".status")).not_to_contain_text("Calculando", timeout=30000)
    expect(page.get_by_role("button", name="Gestión", exact=True)).to_be_enabled()

    log("barra de coordenada del cursor")
    box = page.locator(".map").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.55)
    bar = page.get_by_role("status", name="Coordenada del cursor")
    expect(bar).to_contain_text("-29.9")
    expect(bar).to_contain_text("UTM 19S E")

    log("buscar una coordenada (grados-minutos-segundos)")
    search = page.get_by_label("Buscar dirección o coordenadas")
    search.fill("""29°56'30"S 71°08'30"W""")
    search.press("Enter")
    pin = page.locator(".net-layer .coord-pin")
    expect(pin).to_be_attached()
    assert pin.get_attribute("data-pin") == "-29.941667,-71.141667", pin.get_attribute("data-pin")
    shot(page, "coordenadas-busqueda", theme, width)
    bar.get_by_role("button", name="Quitar marca").click()
    expect(pin).to_have_count(0)

    log("crear un grifo por coordenadas UTM")
    net = api.get(f"/api/projects/{pid}/network").json()["network"]
    j5 = next(f for f in net["features"] if f["id"] == "J-5")["geometry"]["coordinates"]
    page.keyboard.press("g")
    page.get_by_role("button", name="Ingresar coordenadas (Grifo)").click()
    dlg = page.get_by_role("dialog", name="Grifo: ingresar coordenadas")
    # Primero en lat/lon (≈ 15 m al este de J-5) para leer su UTM en la vista previa; luego se crea con el UTM.
    dlg.get_by_label("Coordenadas del elemento").fill(f"{j5[1]:.7f}, {j5[0] + 0.00016:.7f}")
    expect(dlg.locator(".coord-preview")).to_contain_text("19S E")
    utm_text = dlg.locator(".coord-preview dd").nth(2).inner_text()
    m = re.search(r"E ([\d.]+) N ([\d.]+)", utm_text)
    e, n = int(m.group(1).replace(".", "")), int(m.group(2).replace(".", ""))
    dlg.get_by_label("Coordenadas del elemento").fill(f"E {e} N {n} 19S")
    expect(dlg.locator(".coord-preview")).to_contain_text(f"{j5[1]:.3f}"[:6])
    shot(page, "coordenadas-crear", theme, width)
    dlg.get_by_role("button", name="Crear grifo").click()
    expect(page.locator('.net-layer [data-t="hydrant"] .node-sel')).to_have_count(1)  # el grifo nuevo queda seleccionado

    log("mover el grifo editando sus coordenadas")
    sec = page.locator('section[data-section="elemento.coordenadas"]')
    expect(sec).to_be_visible()
    sec.get_by_role("button", name="UTM").click()
    expect(sec.get_by_label("Este UTM")).to_have_value(re.compile(rf"^{e}\.|^{e - 1}\.|^{e + 1}\."))
    sec.get_by_label("Este UTM").fill(str(e + 25))
    sec.get_by_role("button", name="Mover a estas coordenadas").click()
    expect(page.locator(".toast").last).to_contain_text("Elemento movido")
    shot(page, "coordenadas-editar", theme, width)
    page.keyboard.press("Control+s")
    expect(page.locator(".version-info")).to_contain_text(re.compile(r"v\d+ · guardado"), timeout=30000)
    net2 = api.get(f"/api/projects/{pid}/network").json()["network"]
    hyd = [f for f in net2["features"] if f["properties"].get("element") == "hydrant"]
    assert len(hyd) == 2, [f["id"] for f in hyd]
    lons = sorted(f["geometry"]["coordinates"][0] for f in hyd)
    # 15 + 25 m al este de J-5 ≈ 0,00041° de longitud a 30° S
    assert any(abs(x - (j5[0] + 0.00016 + 25 / (111320 * 0.8664))) < 2e-5 for x in lons), (lons, j5)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = login(browser)
        api = p.request.new_context(base_url=BASE, storage_state=state, ignore_https_errors=INSECURE)
        r = api.post("/api/projects/import-excel", multipart={
            "file": {"name": "apr-demo.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     "buffer": DEMO.read_bytes()}, "name": NAME})
        assert r.status == 201, r.text()
        notes = r.json()["preview"]["notes"]
        assert any("Lecturas" in n for n in notes) and any("Mantenciones" in n for n in notes), notes
        pid = r.json()["project_id"]
        try:
            for i, theme in enumerate(("light", "dark")):
                ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True, locale="es-CL",
                                          reduced_motion="reduce", storage_state=state, ignore_https_errors=INSECURE)
                page = ctx.new_page()
                watch(page)
                try:
                    tour_gestion(page, pid, theme, 1440, full=(i == 0))
                    if i == 0:
                        tour_coordinates(page, pid, theme, 1440, api)
                    else:
                        page.goto(f"{BASE}/proyecto/{pid}")
                        expect(page.locator(".net-layer g.node").first).to_be_attached(timeout=30000)
                        page.get_by_role("button", name="Gestión", exact=True).click()
                        expect(page).to_have_url(re.compile(rf"/proyecto/{pid}/gestion"))
                        wait_tab(page)
                except Exception:
                    page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
                    print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
                    raise
                ctx.close()
            for width in (1280, 1024):  # legible en pantallas medianas
                ctx = browser.new_context(viewport={"width": width, "height": 860}, locale="es-CL", reduced_motion="reduce",
                                          storage_state=state, ignore_https_errors=INSECURE)
                page = ctx.new_page()
                watch(page)
                tour_gestion(page, pid, "light", width, full=False)
                ctx.close()
        finally:
            api.delete(f"/api/projects/{pid}")
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print(f"\n✔ Gestión y coordenadas sin errores. Capturas en {SHOTS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
