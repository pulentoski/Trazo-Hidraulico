"""Ajustes por rol (make test-e2e, después de Gestión).

Con cada rol (lector, revisor, proyectista, administrador y superadministrador): el menú lateral muestra solo sus
secciones, las secciones ajenas y las rutas antiguas redirigen, el menú de usuario ofrece Mi cuenta / Organización /
Plataforma según corresponda y cada sección visible abre con su título. Guardar muestra «Guardado». Capturas de
todas las secciones en tema claro y oscuro (superadministrador) y del menú lateral de cada rol.
"""
from __future__ import annotations

import re
import sys
import time

from playwright.sync_api import Page, expect, sync_playwright

from recorrido import ADMIN_EMAIL, BASE, EMAIL, INSECURE, ROOT, SHOTS, log, login, problems, set_theme, shot, watch

CUENTA = {"perfil": "Perfil", "seguridad": "Seguridad", "preferencias": "Preferencias"}
ORG = {"miembros": "Miembros e invitaciones", "criterios": "Criterios de diseño por defecto", "catalogos": "Catálogos",
       "uso": "Uso y plan", "auditoria": "Auditoría"}
PLAT = {"organizaciones": "Organizaciones", "mapa-base": "Mapa base", "planes": "Planes y límites", "sistema": "Sistema"}
ROLES = [  # rol, correo, secciones visibles
    ("lector", "e2e-lector@trazo.local", CUENTA),
    ("revisor", "e2e-revisor@trazo.local", CUENTA),
    ("proyectista", "e2e-proyectista@trazo.local", CUENTA),
    ("admin", EMAIL, {**CUENTA, **ORG}),
    ("superadmin", ADMIN_EMAIL, {**CUENTA, **ORG, **PLAT}),
]
OLD = {"/perfil": "/ajustes/seguridad", "/configuracion": "/ajustes/preferencias", "/acerca-de": "/ajustes/perfil",
       "/organizacion": "/ajustes/miembros", "/plataforma": "/ajustes/organizaciones"}


def fresh_window() -> None:
    """La API limita las solicitudes por IP y minuto (300): cada bloque de la prueba parte en un minuto nuevo."""
    time.sleep(61 - time.time() % 60)


def nav_ids(page: Page) -> list[str]:
    nav = page.get_by_role("navigation", name="Secciones de ajustes")
    expect(nav).to_be_visible()
    return [h.split("/ajustes/")[-1] for h in nav.locator("a").evaluate_all("els => els.map(a => a.getAttribute('href'))")]


def visit(page: Page, sid: str, title: str) -> None:
    """Abre una sección con el menú lateral (navegación sin recargar, como un usuario)."""
    nav = page.get_by_role("navigation", name="Secciones de ajustes")
    if "/ajustes/" in page.url and nav.count():
        nav.locator(f'a[href="/ajustes/{sid}"]').click()
    else:
        page.goto(f"{BASE}/ajustes/{sid}")
    expect(page).to_have_url(re.compile(rf"/ajustes/{sid}$"))
    expect(page.locator(".ajustes-panel > header h2")).to_have_text(title)
    expect(page.get_by_role("navigation", name="Secciones de ajustes").locator("a.on")).to_have_attribute("href", f"/ajustes/{sid}")


def check_role(browser, role: str, email: str, visible: dict[str, str]) -> None:
    log(f"ajustes: {role}")
    fresh_window()
    state = login(browser, email)
    ctx = browser.new_context(viewport={"width": 1280, "height": 860}, locale="es-CL", storage_state=state,
                              ignore_https_errors=INSECURE, reduced_motion="reduce")
    page = ctx.new_page()
    watch(page)
    set_theme(page, "light")
    try:
        page.goto(f"{BASE}/ajustes")
        expect(page).to_have_url(re.compile(r"/ajustes/perfil$"))
        assert nav_ids(page) == list(visible), (role, nav_ids(page))
        expect(page.locator(".page-footer")).to_contain_text("versión")
        shot(page, f"ajustes-menu-{role}", "light", 1280)
        # Menú de usuario según el rol
        page.get_by_role("button", name="Menú de usuario").click()
        menu = page.get_by_role("menu")
        expect(menu.get_by_role("menuitem", name="Mi cuenta")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Organización")).to_have_count(1 if "miembros" in visible else 0)
        expect(menu.get_by_role("menuitem", name="Plataforma")).to_have_count(1 if "sistema" in visible else 0)
        expect(menu.get_by_role("menuitem", name="Cerrar sesión")).to_be_visible()
        page.keyboard.press("Escape")
        # Secciones visibles abren; las ajenas redirigen a Perfil
        for sid, title in visible.items():
            visit(page, sid, title)
        for sid in [*ORG, *PLAT]:
            if sid not in visible:
                page.goto(f"{BASE}/ajustes/{sid}")
                expect(page).to_have_url(re.compile(r"/ajustes/perfil$"))
        # Rutas antiguas
        for old, new in OLD.items():
            page.goto(f"{BASE}{old}")
            target = new if new.split("/")[-1] in visible else "/ajustes/perfil"
            expect(page).to_have_url(re.compile(rf"{target}$"))
        # Guardar con confirmación: nombre visible
        visit(page, "perfil", "Perfil")
        name = page.get_by_label("Nombre visible")
        name.fill(f"E2E {role} {int(time.time()) % 100000}")
        page.get_by_role("button", name="Guardar", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()
        expect(page.get_by_role("button", name="Menú de usuario")).to_be_visible()
        if role == "admin":
            log("ajustes: criterios y catálogos de la organización")
            visit(page, "catalogos", "Catálogos")
            page.get_by_label("Vida útil PVC").fill("48")
            page.get_by_label("Vida útil PVC").blur()
            page.get_by_role("button", name="Guardar", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()
            visit(page, "criterios", "Criterios de diseño por defecto")
            visit(page, "catalogos", "Catálogos")
            expect(page.get_by_label("Vida útil PVC")).to_have_value("48")
            page.get_by_label("Vida útil PVC").fill("50")
            page.get_by_label("Vida útil PVC").blur()
            page.get_by_role("button", name="Guardar", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()
        if role == "superadmin":
            for theme in ("light", "dark"):
                log(f"ajustes: capturas de todas las secciones ({theme})")
                fresh_window()
                set_theme(page, theme)
                page.reload()
                for sid, title in visible.items():
                    visit(page, sid, title)
                    if sid == "sistema":
                        expect(page.locator(".service-list")).to_contain_text("Base de datos")
                    page.wait_for_timeout(200)
                    shot(page, f"ajustes-{sid}", theme, 1280)
            log("ajustes: preferencias (tema y animaciones)")
            fresh_window()
            set_theme(page, "light")
            page.reload()
            visit(page, "preferencias", "Preferencias")
            page.get_by_role("radio", name="Oscuro").click()
            sw = page.get_by_role("switch", name="Animaciones")
            expect(sw).not_to_be_checked()  # las pruebas corren con animaciones desactivadas
            page.get_by_role("button", name="Guardar", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.get_by_role("radio", name="Claro").click()
            page.get_by_role("button", name="Guardar", exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-theme", "light")
    except Exception:
        page.screenshot(path=str(ROOT / "e2e" / "fallo.png"))
        print("Problemas hasta el fallo:", *dict.fromkeys(problems), sep="\n  - ")
        raise
    finally:
        ctx.close()


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for role, email, visible in ROLES:
                check_role(browser, role, email, visible)
        finally:
            browser.close()
    if problems:
        print("\n✖ Problemas encontrados:")
        for x in dict.fromkeys(problems):
            print("  -", x)
        return 1
    print(f"\n✔ Ajustes por rol sin errores. Capturas en {SHOTS}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
