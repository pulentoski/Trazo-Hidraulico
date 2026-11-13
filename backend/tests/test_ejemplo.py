"""Proyecto de ejemplo «APR Ejemplo Valle de Elqui» (examples/apr-ejemplo-valle-elqui.trazo): se importa en una
organización limpia y todas las pestañas de Gestión, el Resumen, el informe mensual y la simulación de 24 h muestran
datos (ningún indicador «sin datos»). El archivo se regenera con `make ejemplo` (scripts/generar_apr_ejemplo.py)."""
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from tests.conftest import make_user, new_client

EXAMPLE = Path(os.environ.get("EXAMPLES_DIR", "/app/examples")) / "apr-ejemplo-valle-elqui.trazo"
TABS = ("operacion", "clientes", "perdidas", "activos", "cumplimiento", "planificacion", "equipo")

pytestmark = pytest.mark.skipif(not EXAMPLE.exists(), reason="falta examples/apr-ejemplo-valle-elqui.trazo")


@pytest.fixture(scope="module")
def ejemplo(database):
    make_user("ejemplo@trazo.test", "Organización limpia (ejemplo)", "admin")
    with new_client("ejemplo@trazo.test") as c:
        assert c.get("/api/projects").json() == []  # organización limpia
        r = c.post("/api/projects/import-trazo", files={"file": (EXAMPLE.name, EXAMPLE.read_bytes(), "application/zip")})
        assert r.status_code == 201, r.text
        yield c, r.json()["project"]["id"], r.json()


def test_el_archivo_trae_todo_sin_ortofoto():
    with zipfile.ZipFile(EXAMPLE) as z:
        names = z.namelist()
        doc = json.loads(z.read("trazo.json"))
    assert "modelo.inp" in names and not any(n.startswith("ortofotos/") for n in names)
    net = doc["model"]["network"]["features"]
    kinds = [f["properties"].get("element") or f["properties"].get("kind") for f in net]
    assert sum(1 for k in kinds if k == "client") >= 170
    assert len(doc["sectors"]) >= 6  # cuarteles de corta de las 8 llaves
    assert len(doc["measurements"]) > 5000 and len(doc["leak_events"]) > 20
    for kind in ("energia", "cloro", "cortes", "reclamos", "mantenciones", "lecturas"):
        assert doc["records"][kind], kind
    assert doc["maintenance_logs"] and len(doc["feasibility_history"]) >= 3
    p = doc["project"]
    assert p["gestion_settings"]["water_right_lps"] and p["demand_projection"] and p["design_params"]
    assert all(not x["verified"] for x in p["design_params"])  # criterios típicos: «no verificado»
    months = sorted({r["period"] for r in doc["records"]["lecturas"]})
    assert len(months) >= 23


def test_importa_en_organizacion_limpia(ejemplo):
    c, pid, res = ejemplo
    assert res["project"]["name"] == "APR Ejemplo Valle de Elqui"
    assert not [n for n in res["notes"] if "no válid" in n], res["notes"]
    assert len(c.get(f"/api/projects/{pid}/measurements").json()) > 5000


def test_simulacion_de_24_horas_sin_errores(ejemplo):
    c, pid, _ = ejemplo
    r = c.post(f"/api/projects/{pid}/simulate", json={"model_version": 1})
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["status"] == "ok", [m["message"] for m in sim["messages"]]
    assert len(sim["times"]) == 25
    tank = sim["nodes"]["E-1"]["head"]
    assert max(tank) - min(tank) > 0.5  # el estanque se llena y se vacía en el día


@pytest.mark.parametrize("tab", TABS)
def test_gestion_sin_indicadores_vacios(ejemplo, tab):
    c, pid, _ = ejemplo
    if tab == "planificacion":
        assert c.get(f"/api/projects/{pid}/gestion/capacity").status_code == 200
    r = c.get(f"/api/projects/{pid}/gestion/tabs/{tab}")  # período por defecto: 12 meses hasta el último dato
    assert r.status_code == 200, r.text
    body = r.json()
    empty = [(i["key"], i["empty"]["missing"]) for i in body["indicators"] if i.get("empty")]
    assert not empty, empty
    assert body["indicators"] and all(i["value"] is not None for i in body["indicators"]), \
        [i["key"] for i in body["indicators"] if i["value"] is None]


def test_casos_interesantes(ejemplo):
    c, pid, _ = ejemplo
    ind = {t: {i["key"]: i for i in c.get(f"/api/projects/{pid}/gestion/tabs/{t}").json()["indicators"]} for t in TABS}
    assert ind["activos"]["maintenance_ok"]["value"] < 100  # hay mantenciones atrasadas
    assert ind["equipo"]["tasks_overdue"]["value"] >= 3
    assert 15 <= ind["perdidas"]["nrw"]["value"] <= 32  # agua no contabilizada entre 18 % y 30 % (aprox.)
    alto = c.get(f"/api/projects/{pid}/gestion/tabs/operacion", params={"sector": "El Arrayán"}).json()
    pmin = {i["key"]: i for i in alto["indicators"]}["pressure_min"]
    assert pmin["value"] < 15 and pmin["status"] != "bueno"  # presión baja en El Arrayán (verano)
    rows = c.get(f"/api/projects/{pid}/gestion/records/reclamos").json()["rows"]
    per = Counter(r["received_at"][:7] for r in rows)
    vals = sorted(per.values())
    assert max(vals) >= 2 * vals[len(vals) // 2]  # un mes con reclamos altos


def test_resumen_e_informe_mensual_con_datos(ejemplo):
    c, pid, _ = ejemplo
    s = c.get(f"/api/projects/{pid}/summary")
    assert s.status_code == 200, s.text
    html = c.get(f"/api/projects/{pid}/gestion/report.html")
    assert html.status_code == 200
    text = html.text.lower()
    assert "sin datos" not in text, text[text.find("sin datos") - 300:text.find("sin datos") + 100]
    assert "apr ejemplo valle de elqui" in text
    xlsx = c.get(f"/api/projects/{pid}/gestion/report.xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(xlsx.content), read_only=True)
    assert len(wb.sheetnames) >= 7
