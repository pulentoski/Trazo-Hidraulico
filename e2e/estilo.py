"""Capturas de la identidad visual (docs/estilo.md): inicio, editor, Gestión, Ajustes → Mapa base e ingreso, en
tema claro y oscuro a 1440 y 1024 px, en docs/capturas/estilo/.

ESTILO_FASE=antes|despues (por defecto «despues») antepone la fase al nombre del archivo, para comparar el estilo
anterior con el nuevo. Usa el superadministrador e2e (make test-e2e lo crea), importa «APR Demo (estilo)» desde
examples/apr-demo.xlsx y lo elimina al terminar. Animaciones desactivadas (preferencia y prefers-reduced-motion).
"""
from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import Page, expect, sync_playwright

from recorrido import ADMIN_EMAIL, BASE, DEMO, EMAIL_RE, INSECURE, ROOT, log, login, problems, set_theme, watch

FASE = os.environ.get("ESTILO_FASE", "despues")
OUT = ROOT / "docs" / "capturas" / "estilo"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def snap(page: Page, name: str, theme: str, width: int) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)
    # Correos (p. ej. «última modificación» de la key) tapados: las capturas van al repositorio.
    page.screenshot(path=str(OUT / f"{FASE}-{name}-{theme}-{width}.png"), full_page=False,
                    mask=[page.get_by_text(EMAIL_RE)], mask_color="#8a9aa8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        state = login(browser, ADMIN_EMAIL)
        api = p.request.new_context(base_url=BASE, storage_state=state, ignore_https_errors=INSECURE)
        r = api.post("/api/projects/import-excel", multipart={
            "file": {"name": "apr-demo.xlsx", "mimeType": XLSX, "buffer": DEMO.read_bytes()}, "name": "APR Demo (estilo)"})
        assert r.status == 201, r.text()
        pid = r.json()["project_id"]
        try:
            for theme, tema in (("light", "claro"), ("dark", "oscuro")):
                for width in (1440, 1024):
                    log(f"capturas {FASE}: tema {tema}, {width} px")
                    anon = browser.new_context(viewport={"width": width, "height": 900}, locale="es-CL",
                                               ignore_https_errors=INSECURE, reduced_motion="reduce",
                                               color_scheme=theme)
                    page = anon.new_page()
                    set_theme(page, theme)
                    page.goto(f"{BASE}/login")
                    expect(page.get_by_role("button", name="Ingresar")).to_be_visible()
                    snap(page, "login", tema, width)
                    anon.close()

                    ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="es-CL", storage_state=state,
                                              ignore_https_errors=INSECURE, reduced_motion="reduce", color_scheme=theme)
                    page = ctx.new_page()
                    watch(page)
                    set_theme(page, theme)
                    page.goto(f"{BASE}/")
                    expect(page.get_by_role("article", name="APR Demo (estilo)")).to_be_visible()
                    snap(page, "inicio", tema, width)
                    page.goto(f"{BASE}/proyecto/{pid}")
                    expect(page.locator(".status")).to_contain_text("Actualizado", timeout=30000)
                    snap(page, "editor", tema, width)
                    page.goto(f"{BASE}/proyecto/{pid}/gestion")
                    expect(page.locator(".kpi-tile").first).to_be_visible(timeout=30000)
                    snap(page, "gestion", tema, width)
                    page.goto(f"{BASE}/ajustes/mapa-base")
                    expect(page.get_by_label("Proveedor y key del mapa base")).to_be_visible()
                    snap(page, "ajustes-mapa-base", tema, width)
                    ctx.close()
        finally:
            api.delete(f"/api/projects/{pid}")
            browser.close()
    bad = [x for x in dict.fromkeys(problems) if not re.search(r"/api/auth/me", x)]
    if bad:
        print("\n✖ Problemas encontrados:", *bad, sep="\n  - ")
        return 1
    print(f"\n✔ Capturas «{FASE}» en {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
