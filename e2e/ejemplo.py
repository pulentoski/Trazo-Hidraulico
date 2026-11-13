"""Proyecto de ejemplo «APR Ejemplo Valle de Elqui» (make test-e2e).

En una organización limpia (usuario propio, sin proyectos): el inicio vacío ofrece «Cargar proyecto de ejemplo», que
importa examples/apr-ejemplo-valle-elqui.trazo (servido como ejemplos/apr-ejemplo-valle-elqui.trazo). Se verifica que
la simulación de 24 h corre sin errores, que el Resumen y todas las pestañas de Gestión muestran datos (ningún
«sin datos» ni indicador vacío) y que el informe mensual también. Deja capturas de cada pestaña en
docs/capturas/ejemplo/. Al terminar borra el proyecto: la organización queda limpia para la próxima vez.
"""
from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import Page, expect, sync_playwright

from gestion import SLUG, TABS, open_tab, wait_tab
from recorrido import BASE, INSECURE, ROOT, SHOTS, log, login, problems, set_theme, tab, wait_sim, watch

EMAIL = os.environ.get("E2E_EJEMPLO_EMAIL", "e2e-ejemplo@trazo.local")
NAME = "APR Ejemplo Valle de Elqui"
OUT = SHOTS / "ejemplo"
EMPTY = re.compile(r"sin datos", re.I)


def clean_org(api) -> None:
    for p in api.get("/api/projects").json():
        assert api.delete(f"/api/projects/{p['id']}").ok, p["name"]


def no_empty(page: Page, where: str) -> None:
    hints = page.locator(".empty-hint")
    assert hints.count() == 0, f"{where}: indicadores vacíos: {hints.all_inner_texts()[:3]}"
    body = page.locator("main").inner_text()
    m = EMPTY.search(body)
    assert m is None, f"{where}: «{body[max(0, m.start() - 120):m.end() + 40]}»"


def tour(page: Page, api) -> str:
    set_theme(page, "light")
    page.goto(f"{BASE}/")
    expect(page.get_by_role("heading", name="Todavía no hay proyectos")).to_be_visible(timeout=30000)
    log("inicio vacío → «Cargar proyecto de ejemplo»")
    page.get_by_role("button", name="Cargar proyecto de ejemplo").click()
    page.wait_for_url(re.compile(r"/proyecto/[0-9a-f-]{36}$"), timeout=60000)
    pid = page.url.rsplit("/", 1)[1]
    expect(page.locator(".toast").last).to_contain_text("Proyecto de ejemplo cargado")
    expect(page.locator(".net-layer g.node").first).to_be_attached(timeout=30000)
    page.locator(".toast").first.click()  # se cierra con un clic: capturas sin el aviso encima
    expect(page.locator(".toast")).to_have_count(0)

    log("simulación de 24 h")
    page.keyboard.press("F5")
    wait_sim(page)
    sim = api.post(f"/api/projects/{pid}/simulate", data={"model_version": 1}).json()
    assert sim["status"] == "ok" and len(sim["times"]) == 25, [m["message"] for m in sim["messages"]][:5]

    log("resumen")
    tab(page, "Resumen")
    summary = page.locator(".summary-tab")
    expect(summary.locator(".summary-grid")).to_be_visible(timeout=30000)
    page.wait_for_timeout(500)
    txt = summary.inner_text()
    assert not EMPTY.search(txt), f"Resumen: {txt[:300]}"
    expect(summary.get_by_label("Pérdidas y filtraciones")).to_contain_text("eventos")
    page.screenshot(path=str(OUT / "resumen.png"))

    log("gestión: las 7 pestañas")
    page.get_by_role("button", name="Gestión", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/proyecto/{pid}/gestion"))
    wait_tab(page)
    for t in TABS:
        open_tab(page, t)
        page.wait_for_timeout(400)
        no_empty(page, f"Gestión · {t}")
        page.screenshot(path=str(OUT / f"gestion-{SLUG[t]}.png"))
    open_tab(page, "Operación")
    page.get_by_label("Sector").select_option("El Arrayán")
    wait_tab(page)
    expect(page.locator('article.kpi-tile[aria-label="Presión mínima medida"] .kpi-value b')).not_to_have_text("—")
    page.screenshot(path=str(OUT / "gestion-operacion-el-arrayan.png"))
    page.get_by_label("Sector").select_option("")
    wait_tab(page)

    log("informe mensual")
    href = page.get_by_role("link", name="Informe mensual").get_attribute("href")
    rep = page.context.new_page()
    watch(rep)
    rep.goto(f"{BASE}{href}")
    expect(rep.get_by_role("heading", name=re.compile(f"Informe mensual de gestión — {re.escape(NAME)}"))).to_be_visible()
    for t in TABS:
        expect(rep.get_by_role("heading", name=t, exact=True)).to_be_visible()
    body = rep.locator("body").inner_text()
    assert not EMPTY.search(body), "informe mensual con «sin datos»"
    rep.screenshot(path=str(OUT / "informe-mensual.png"))
    rep.close()
    return pid


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = login(browser, EMAIL)
        api = p.request.new_context(base_url=BASE, storage_state=state, ignore_https_errors=INSECURE)
        clean_org(api)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL", reduced_motion="reduce",
                                  storage_state=state, ignore_https_errors=INSECURE)
        page = ctx.new_page()
        watch(page)
        pid = None
        try:
            pid = tour(page, api)
        except Exception:
            page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
            print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
            raise
        finally:
            ctx.close()
            clean_org(api)
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print(f"\n✔ Proyecto de ejemplo: importado, simulado y con datos en todas las pestañas. Capturas en {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
