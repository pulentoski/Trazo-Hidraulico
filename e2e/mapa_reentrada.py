"""Mapa al entrar, salir y volver a entrar al editor (make test-e2e, después del recorrido visual).

Regresión del mapa que, al volver a abrir un proyecto, dejaba la capa de la red en 0×0: la rueda no acercaba, el
arrastre no movía el mapa, los botones +/− hacían desaparecer la red e «ir al elemento» no llevaba a ningún lado.

Se ejecuta dos veces:
  · con la key de Google Maps guardada en Configuración (se omite si la plataforma no tiene una), verificando que el
    mapa de Google recibe los gestos (gestureHandling «greedy») y que ninguna capa transparente los intercepta;
  · sin key (la configuración del mapa se intercepta y llega vacía): lienzo neutro, mismos gestos sobre la red.

En cada caso: abrir, dibujar un nudo y guardar; luego volver al menú y entrar de nuevo 3 veces. En cada vuelta se
verifica zoom con rueda, arrastre, red visible tras + y −, «Centrar en la red» e «ir al elemento» desde 4 lugares
(Nudos, Tramos, Clientes y la búsqueda global): el mapa se centra y acerca, el elemento queda seleccionado y resaltado.
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import Page, expect, sync_playwright

from recorrido import BASE, DEMO, INSECURE, ROOT, login, log, problems, tab, watch

NAME = "Mapa reentrada (e2e)"
ROUNDS = 3


def zoom_of(page: Page) -> int:
    return int(re.search(r"Zoom (\d+)", page.locator(".scale-bar").get_attribute("title") or "").group(1))


def settle(page: Page) -> None:
    """Espera a que la cámara termine de moverse (las animaciones de Google duran unos cientos de ms)."""
    last = None
    for _ in range(40):
        now = page.evaluate("""() => [document.querySelector('.scale-bar')?.title,
          [...document.querySelectorAll('.net-layer g.node')].slice(0, 3).map(g => g.getAttribute('transform')).join('|')]""")
        if now == last:
            return
        last = now
        page.wait_for_timeout(150)


def map_box(page: Page) -> dict:
    return page.locator(".map").bounding_box()


def visible_nodes(page: Page) -> list[list[float]]:
    """Posiciones de pantalla (relativas al mapa) de los nudos dentro del área visible."""
    return page.evaluate("""() => {
      const svg = document.querySelector('.net-layer');
      const w = +svg.getAttribute('width'), h = +svg.getAttribute('height');
      return [...svg.querySelectorAll('g.node')].map(g => {
        const m = /translate\\(([-\\d.e]+),([-\\d.e]+)\\)/.exec(g.getAttribute('transform') || '');
        return m ? [+m[1], +m[2], g.dataset.uid] : null;
      }).filter(p => p && p[0] >= 0 && p[1] >= 0 && p[0] <= w && p[1] <= h);
    }""")


def node_pos(page: Page, uid: str) -> tuple[float, float] | None:
    t = page.locator(f'.net-layer g.node[data-uid="{uid}"]').get_attribute("transform")
    m = re.search(r"translate\(([-\d.e]+),([-\d.e]+)\)", t or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def empty_point(page: Page) -> tuple[float, float]:
    """Un punto del mapa sin elementos de la red ni controles encima (para arrastrar el fondo)."""
    box = map_box(page)
    for fx, fy in ((0.5, 0.75), (0.3, 0.7), (0.7, 0.7), (0.5, 0.5), (0.25, 0.4), (0.75, 0.4)):
        x, y = box["x"] + box["width"] * fx, box["y"] + box["height"] * fy
        free = page.evaluate("""([x, y]) => { const el = document.elementFromPoint(x, y);
          return !!el && !el.closest('[data-t], .map-controls, .legend, .scale-bar, .hour-slider, .map-notice'); }""", [x, y])
        if free:
            return x, y
    raise AssertionError("no hay un punto libre del mapa para arrastrar")


def check_gestures(page: Page, google: bool) -> None:
    box = map_box(page)
    svg = page.locator(".net-layer")
    assert abs(float(svg.get_attribute("width")) - box["width"]) < 2, "la capa de la red no cubre el mapa"
    assert abs(float(svg.get_attribute("height")) - box["height"]) < 2, "la capa de la red no cubre el mapa"
    if google:
        expect(page.locator(".map-base .gm-style").first).to_be_attached(timeout=20000)
    page.get_by_role("button", name="Centrar en la red").click()
    settle(page)
    x, y = empty_point(page)
    if google:  # el fondo debe llegar al mapa de Google (sin capas transparentes encima)
        on_map = page.evaluate("([x, y]) => !!document.elementFromPoint(x, y)?.closest('.map-base')", [x, y])
        assert on_map, "una capa intercepta los gestos sobre el mapa de Google"

    # Rueda: acerca y aleja.
    z0 = zoom_of(page)
    page.mouse.move(x, y)
    page.mouse.wheel(0, -120)
    settle(page)
    z1 = zoom_of(page)
    assert z1 > z0, f"la rueda no acercó el mapa (zoom {z0} → {z1})"
    page.mouse.wheel(0, 120)
    settle(page)
    assert zoom_of(page) < z1, "la rueda no alejó el mapa"

    # Arrastre del fondo: los nudos se desplazan con el mapa.
    nodes = visible_nodes(page)
    assert nodes, "no hay nudos visibles para medir el arrastre"
    uid = nodes[0][2]
    before = node_pos(page, uid)
    x, y = empty_point(page)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 90, y - 50, steps=10)
    page.wait_for_timeout(400)  # sin velocidad al soltar: Google no agrega desplazamiento por inercia
    page.mouse.up()
    settle(page)
    after = node_pos(page, uid)
    # Google descarta unos px al iniciar el arrastre (umbral) y puede sumar algo de inercia: se exige la dirección y
    # una magnitud cercana a la del gesto; sin key, la capa propia desplaza exactamente lo arrastrado.
    tol = 30 if google else 3
    assert before and after and abs(after[0] - before[0] + 90) < tol and abs(after[1] - before[1] + 50) < tol, \
        f"el arrastre no movió el mapa: {before} → {after}"

    # Botones + y −: la red sigue visible.
    for name in ("Alejar", "Acercar", "Acercar", "Alejar"):
        z = zoom_of(page)
        page.get_by_role("button", name=name, exact=True).click()
        settle(page)
        assert zoom_of(page) == z + (1 if name == "Acercar" else -1), f"el botón {name} no cambió el zoom"
        assert visible_nodes(page), f"la red desapareció tras «{name}»"


def check_goto(page: Page) -> None:
    """Ir al elemento: centra, acerca, selecciona y resalta."""
    def expect_centered(label: str) -> None:
        settle(page)
        flash = page.locator(".net-layer g.flash[data-flash]")
        expect(flash, f"sin resaltado tras ir al elemento desde {label}").to_be_attached(timeout=3000)
        box = map_box(page)
        c = page.evaluate("""() => { const el = document.querySelector('.net-layer g.flash').firstElementChild;
          const b = el.getBBox(); return [b.x + b.width / 2, b.y + b.height / 2]; }""")
        assert abs(c[0] - box["width"] / 2) < box["width"] * 0.2 and abs(c[1] - box["height"] / 2) < box["height"] * 0.2, \
            f"{label}: el elemento no quedó al centro del mapa ({c}, mapa {box['width']}×{box['height']})"
        assert zoom_of(page) >= 17, f"{label}: el mapa no se acercó al elemento (zoom {zoom_of(page)})"
        expect(page.locator(".net-layer .sel, .net-layer .node-sel, .net-layer .link-sel").first, f"{label}: el elemento no quedó seleccionado").to_be_attached()

    def far_away() -> None:  # aleja la vista para que el encuadre sea un cambio real
        page.get_by_role("button", name="Centrar en la red").click()
        for _ in range(2):
            page.get_by_role("button", name="Alejar", exact=True).click()
        settle(page)

    for label in ("Nudos", "Tramos", "Clientes"):
        far_away()
        tab(page, label)
        rows = page.locator(".bottom table tr.clickable")
        expect(rows.first).to_be_visible()
        rows.nth(min(3, rows.count() - 1)).click()
        expect_centered(label)

    far_away()
    search = page.get_by_label("Búsqueda rápida")
    search.fill("C-01")
    page.locator(".qs-results li").first.dispatch_event("mousedown")
    expect_centered("búsqueda global")
    search.fill("")
    page.keyboard.press("Escape")


def open_project(page: Page) -> None:
    page.get_by_role("article", name=NAME).get_by_role("button", name="Abrir").click()
    expect(page.locator(".net-layer g.node").first).to_be_attached(timeout=30000)
    expect(page.locator(".status")).to_contain_text("Actualizado", timeout=30000)


def back_to_menu(page: Page) -> None:
    page.locator(".back-btn").click()
    page.wait_for_url(re.compile(r"/$"), timeout=15000)
    expect(page.get_by_role("article", name=NAME)).to_be_visible()


def run(browser, state: dict, google: bool) -> None:
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-CL", storage_state=state,
                              ignore_https_errors=INSECURE)
    page = ctx.new_page()
    watch(page)
    if not google:  # lienzo neutro: la configuración del mapa llega sin key
        page.route("**/api/maps/config", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"provider": "auto", "api_key": None, "map_id": None, "source": "none"})))
    try:
        page.goto(f"{BASE}/")
        open_project(page)
        if google:
            expect(page.locator(".map-base .gm-style").first).to_be_attached(timeout=20000)
        else:
            expect(page.locator(".map-base.blank")).to_be_attached()
        log("dibujar un tramo entre dos nudos y guardar")
        links0 = page.locator('.net-layer [data-t="link"].hit').count()
        box = map_box(page)
        js = page.evaluate("""() => [...document.querySelectorAll('.net-layer g.node-junction')].map(g => {
          const m = /translate\\(([-\\d.e]+),([-\\d.e]+)\\)/.exec(g.getAttribute('transform')); return [+m[1], +m[2]]; })""")
        inside = [q for q in js if 40 < q[0] < box["width"] - 40 and 40 < q[1] < box["height"] - 40]
        a, b = max(((p, q) for p in inside for q in inside if p != q), key=lambda pq: -abs(pq[0][0] - pq[1][0]) - abs(pq[0][1] - pq[1][1]) if abs(pq[0][0] - pq[1][0]) + abs(pq[0][1] - pq[1][1]) > 40 else -1e9)
        page.keyboard.press("t")
        page.mouse.click(box["x"] + a[0], box["y"] + a[1])
        page.mouse.click(box["x"] + b[0], box["y"] + b[1])
        expect(page.locator('.net-layer [data-t="link"].hit')).to_have_count(links0 + 1)
        page.keyboard.press("v")
        page.keyboard.press("Control+s")
        expect(page.locator(".version-info")).to_contain_text(re.compile(r"v\d+ · guardado"), timeout=30000)
        expect(page.locator(".status")).to_contain_text("Actualizado", timeout=30000)
        for i in range(1, ROUNDS + 1):
            back_to_menu(page)
            open_project(page)
            log(f"vuelta {i}: gestos y botones")
            check_gestures(page, google)
            log(f"vuelta {i}: ir al elemento")
            check_goto(page)
    except Exception:
        page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
        print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
        raise
    finally:
        ctx.close()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = login(browser)
        api = p.request.new_context(base_url=BASE, storage_state=state, ignore_https_errors=INSECURE)
        has_key = bool(api.get("/api/maps/config").json().get("api_key"))
        r = api.post("/api/projects/import-excel", multipart={
            "file": {"name": "apr-demo.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     "buffer": DEMO.read_bytes()}, "name": NAME})
        assert r.status == 201, r.text()
        pid = r.json()["project_id"]
        try:
            if has_key:
                log("== mapa de Google (key de Configuración) ==")
                run(browser, state, google=True)
            else:
                log("== mapa de Google: omitido (la plataforma no tiene key guardada) ==")
            log("== lienzo neutro (sin key) ==")
            run(browser, state, google=False)
        finally:
            api.delete(f"/api/projects/{pid}")
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print("\n✔ Mapa: entrar, salir y volver a entrar sin errores.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
