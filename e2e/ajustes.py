"""Ajustes y Panel admin por rol (make test-e2e, después de Gestión).

Con cada rol (lector, revisor, proyectista, administrador y superadministrador): el menú de Ajustes muestra solo sus
secciones, las secciones ajenas y las rutas antiguas redirigen («Plataforma» pasó a «Panel admin»), el menú de
usuario ofrece Mi cuenta / Organización / Panel admin según corresponda y cada sección visible abre con su título.
Guardar muestra «Guardado». Con el plan al tope de usuarios, «Invitar» queda deshabilitado con «Su plan permite N
usuarios». El Panel admin solo existe para el Super Admin: resumen, organizaciones con su ficha, planes, usuarios,
mapa base y sistema; suspender pide escribir el nombre. Capturas de todas las secciones en tema claro y oscuro.
"""
from __future__ import annotations

import re
import sys
import time

from playwright.sync_api import Page, expect, sync_playwright

from recorrido import ADMIN_EMAIL, BASE, EMAIL, INSECURE, ROOT, SHOTS, log, login, problems, set_theme, shot, watch

CUENTA = {"perfil": "Perfil", "seguridad": "Seguridad", "preferencias": "Preferencias"}
ORG = {"organizacion": "Datos de la organización", "miembros": "Miembros e invitaciones", "criterios": "Criterios de diseño por defecto", "catalogos": "Catálogos",
       "uso": "Uso y plan", "auditoria": "Auditoría"}
# Panel admin (antes Ajustes → Plataforma): sección → título del primer panel
PANEL = {"": "Organizaciones cerca de su límite", "organizaciones": "Organizaciones", "planes": "Planes y límites",
         "usuarios": "Usuarios", "mapa-base": "Mapa base", "sistema": "Sistema"}
PLAT = ["organizaciones", "mapa-base", "planes", "sistema"]  # rutas antiguas /ajustes/<x> que ahora van al Panel admin
ROLES = [  # rol, correo, secciones visibles
    ("lector", "e2e-lector@trazo.local", CUENTA),
    ("revisor", "e2e-revisor@trazo.local", CUENTA),
    ("proyectista", "e2e-proyectista@trazo.local", CUENTA),
    ("admin", EMAIL, {**CUENTA, **ORG}),
    ("superadmin", ADMIN_EMAIL, {**CUENTA, **ORG}),
]
OLD = {"/perfil": "/ajustes/seguridad", "/configuracion": "/ajustes/preferencias", "/acerca-de": "/ajustes/perfil",
       "/organizacion": "/ajustes/miembros"}


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


def org_id(page: Page) -> str:
    me = page.request.get(f"{BASE}/api/auth/me").json()
    return me["current_org"]


def check_role(browser, role: str, email: str, visible: dict[str, str]) -> None:
    log(f"ajustes: {role}")
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
        expect(page.locator(".frame-footer")).to_contain_text("versión")
        shot(page, f"ajustes-menu-{role}", "light", 1280)
        # Menú de usuario según el rol
        page.get_by_role("button", name="Menú de usuario").click()
        menu = page.get_by_role("menu")
        expect(menu.get_by_role("menuitem", name="Mi cuenta")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Organización")).to_have_count(1 if "miembros" in visible else 0)
        expect(menu.get_by_role("menuitem", name="Panel admin")).to_have_count(1 if role == "superadmin" else 0)
        expect(menu.get_by_role("menuitem", name="Plataforma")).to_have_count(0)
        expect(menu.get_by_role("menuitem", name="Cerrar sesión")).to_be_visible()
        page.keyboard.press("Escape")
        # Secciones visibles abren; las ajenas redirigen a Perfil
        for sid, title in visible.items():
            visit(page, sid, title)
        for sid in ORG:
            if sid not in visible:
                page.goto(f"{BASE}/ajustes/{sid}")
                expect(page).to_have_url(re.compile(r"/ajustes/perfil$"))
        # Lo que era Ajustes → Plataforma ahora vive en el Panel admin (solo Super Admin)
        for sid in PLAT:
            page.goto(f"{BASE}/ajustes/{sid}")
            expect(page).to_have_url(re.compile(rf"/panel-admin/{sid}$" if role == "superadmin" else r"/ajustes/perfil$"))
        page.goto(f"{BASE}/plataforma")
        expect(page).to_have_url(re.compile(r"/panel-admin$" if role == "superadmin" else rf"{re.escape(BASE)}/$"))
        if role != "superadmin":
            page.goto(f"{BASE}/panel-admin/organizaciones")
            expect(page).to_have_url(re.compile(rf"{re.escape(BASE)}/$"))
            expect(page.get_by_role("navigation", name="Menú principal").get_by_role("link", name="Panel admin")).to_have_count(0)
        # Rutas antiguas
        for old, new in OLD.items():
            page.goto(f"{BASE}{old}")
            target = new if new.split("/")[-1] in visible else "/ajustes/perfil"
            expect(page).to_have_url(re.compile(rf"{target}$"))
        if role == "lector":
            log("ajustes: un 429 reintenta sin cerrar la sesión")
            hits = {"n": 0}

            def limited(route):
                hits["n"] += 1
                if hits["n"] <= 2:
                    route.fulfill(status=429, headers={"Retry-After": "1", "Content-Type": "application/json"},
                                  body='{"detail": "Demasiadas solicitudes", "code": "rate_limited"}')
                else:
                    route.continue_()
            page.route("**/api/auth/me", limited)
            n = len(problems)
            page.goto(f"{BASE}/ajustes/seguridad")
            expect(page.locator(".toast").filter(has_text="Demasiadas solicitudes, reintentando")).to_be_visible()
            expect(page.locator(".ajustes-panel > header h2")).to_have_text("Seguridad", timeout=15000)
            expect(page).to_have_url(re.compile(r"/ajustes/seguridad$"))  # no se fue al ingreso
            assert hits["n"] == 3, hits
            page.unroute("**/api/auth/me")
            problems[n:] = [x for x in problems[n:] if "429" not in x]  # los 429 simulados son esperados
        # Guardar con confirmación: nombre visible
        visit(page, "perfil", "Perfil")
        name = page.get_by_label("Nombre visible")
        name.fill(f"E2E {role} {int(time.time()) % 100000}")
        page.get_by_role("button", name="Guardar", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Guardado")).to_be_visible()
        expect(page.get_by_role("button", name="Menú de usuario")).to_be_visible()
        if role == "admin":
            log("ajustes: tope de usuarios del plan en Miembros")
            visit(page, "miembros", "Miembros e invitaciones")
            u = page.request.get(f"{BASE}/api/orgs/{org_id(page)}/usage").json()
            cap = u["limits"].get("max_users")
            if cap is not None and u["users"] + u["pending_invitations"] >= cap:
                expect(page.get_by_role("button", name="Invitar", exact=True)).to_be_disabled()
                expect(page.get_by_role("status").filter(has_text=f"Su plan permite {cap} usuarios")).to_be_visible()
            else:
                expect(page.get_by_role("button", name="Invitar", exact=True)).to_be_enabled()
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
                log(f"ajustes y Panel admin: capturas de todas las secciones ({theme})")
                set_theme(page, theme)
                page.reload()
                for sid, title in visible.items():
                    visit(page, sid, title)
                    page.wait_for_timeout(200)
                    shot(page, f"ajustes-{sid}", theme, 1280)
                for sid, title in PANEL.items():
                    page.goto(f"{BASE}/panel-admin{'/' + sid if sid else ''}")
                    expect(page.locator(".ajustes-panel > header h2").first).to_have_text(title)
                    if sid == "sistema":
                        expect(page.locator(".service-list")).to_contain_text("Base de datos")
                    page.wait_for_timeout(200)
                    shot(page, f"panel-admin-{sid or 'resumen'}", theme, 1280)
            log("panel admin: ficha de organización y confirmación escrita")
            page.goto(f"{BASE}/panel-admin/organizaciones")
            page.locator('table[data-table-label="Organizaciones"]').get_by_role("link", name="Recorrido e2e", exact=True).click()
            expect(page).to_have_url(re.compile(r"/panel-admin/organizaciones/[0-9a-f-]{36}$"))
            for t in ("Cambiar plan", "Uso contra límites", "Usuarios"):
                expect(page.get_by_role("heading", name=t, exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Entrar como soporte")).to_be_visible()
            page.get_by_role("button", name="Suspender").click()
            dlg = page.get_by_role("dialog", name="Suspender organización")
            confirm = dlg.get_by_role("button", name="Suspender")
            expect(confirm).to_be_disabled()
            dlg.get_by_label("Nombre de la organización").fill("Recorrido")
            expect(confirm).to_be_disabled()  # nombre incompleto: no se habilita
            shot(page, "panel-admin-confirmacion", "dark", 1280)
            dlg.get_by_role("button", name="Cancelar").click()
            expect(dlg).to_have_count(0)
            log("ajustes: preferencias (tema y animaciones)")
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
