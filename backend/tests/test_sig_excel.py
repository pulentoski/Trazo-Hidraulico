"""SIG — planillas: plantilla, ida y vuelta sin cambios, errores por fila, actualización parcial, CSV y la
demostración «APR Demo» (simula sin errores y tiene al menos 2 cuarteles)."""
import io
import os
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

EXAMPLES = Path(os.environ.get("EXAMPLES_DIR", "/app/examples"))
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def demo_bytes() -> bytes:
    return (EXAMPLES / "apr-demo.xlsx").read_bytes()


def create_demo(client, name="APR Demo (prueba)") -> str:
    r = client.post("/api/projects/import-excel", files={"file": ("apr-demo.xlsx", demo_bytes(), XLSX)},
                    data={"name": name})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] and body["version"] == 1
    return body["project_id"]


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def preview(client, pid, content, name="cambios.xlsx", **data):
    r = client.post(f"/api/projects/{pid}/sig/import/preview", files={"file": (name, content, XLSX)}, data=data)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def demo(client):
    return create_demo(client)


def test_plantilla_tiene_hojas_validaciones_e_instrucciones(client):
    r = client.get("/api/sig/template.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Instrucciones"
    for name in ("Nudos", "Tramos", "Estanques", "Reservorios", "Válvulas", "Grifos", "Pozos", "Bombas", "Clientes"):
        assert name in wb.sheetnames
    ws = wb["Tramos"]
    headers = [c.value for c in ws[1]]
    assert headers[:3] == ["ID", "Nudo inicial", "Nudo final"]
    assert ws.cell(2, 1).value.startswith("Identificador único")  # fila de descripción
    lists = [dv.formula1 for dv in ws.data_validations.dataValidation if dv.type == "list"]
    assert any("PVC" in f for f in lists), "lista de materiales del catálogo"
    assert any("fuera de servicio" in f for f in lists), "lista de estado"
    assert any("distribución" in f for f in lists), "lista de tipo de red"


def test_demo_simula_sin_errores_y_tiene_cuarteles(client, demo):
    doc = client.get(f"/api/projects/{demo}/network").json()
    feats = doc["network"]["features"]
    count = lambda el, kind=None: sum(1 for f in feats if f["properties"]["element"] == el  # noqa: E731
                                      and (kind is None or f["properties"].get("kind") == kind))
    assert count("client") == 30 and count("link", "pipe") == 15 and count("node", "tank") == 1
    assert count("well") == 1 and count("link", "pump") == 1 and count("shutoff") == 4 and count("hydrant") == 1
    res = next(f for f in feats if f["id"] == "R-POZO")["properties"]
    assert res["head"] == pytest.approx(210.0 - 35.0)  # cota del pozo − nivel dinámico
    pozo = next(f for f in feats if f["id"] == "PZ-1")["properties"]
    assert pozo["attributes"] == {"Derecho DGA": "ND-0401-1234"}
    sim = client.post(f"/api/projects/{demo}/simulate", json={"model_version": 1})
    assert sim.status_code == 200, sim.text
    assert sim.json()["status"] in ("ok", "warning")
    assert not [m for m in sim.json()["messages"] if m["severity"] == "error"]
    sectors = client.get(f"/api/projects/{demo}/sectors").json()["sectors"]
    assert len(sectors) >= 2


def test_ida_y_vuelta_excel_sin_cambios(client, demo):
    exp = client.get(f"/api/projects/{demo}/sig/export.xlsx")
    assert exp.status_code == 200 and exp.content[:2] == b"PK"
    p = preview(client, demo, exp.content, name="export.xlsx")
    assert p["ok"], p["errors"]
    assert p["new"] == [] and p["modified"] == [] and p["deleted"] == []
    assert len(p["unchanged"]) == 14 + 15 + 1 + 1 + 4 + 1 + 1 + 1 + 30
    r = client.post(f"/api/projects/{demo}/sig/import/apply", files={"file": ("export.xlsx", exp.content, XLSX)})
    assert r.status_code == 200 and r.json()["created"] is False
    # La exportación de la nueva importación conserva los atributos libres.
    wb = load_workbook(io.BytesIO(exp.content))
    assert "Sector social" in [c.value for c in wb["Clientes"][1]]


def test_importar_con_errores_reporta_cada_fila(client, demo):
    content = xlsx({
        "Nudos": [["ID", "Latitud", "Longitud", "Cota"],
                  ["N-OK", -29.94, -71.14, 230],
                  ["N-MAL", -29.94, -71.14, "alto"],
                  ["N-SIN", None, None, 230],
                  ["N-OK", -29.95, -71.15, 231]],
        "Tramos": [["ID", "Nudo inicial", "Nudo final", "DN", "Material", "Clase", "Estado"],
                   ["T-X", "N-OK", "NO-EXISTE", 63, "PVC", "C10", "bueno"],
                   ["T-Y", "J-1", "J-2", 63, "PVC", "C10", "pésimo"]],
    })
    p = preview(client, demo, content)
    assert not p["ok"]
    got = {(e["sheet"], e["row"]) for e in p["errors"]}
    assert ("Nudos", 3) in got  # cota no numérica
    assert ("Nudos", 4) in got  # sin coordenadas
    assert ("Nudos", 5) in got  # ID repetido
    assert ("Tramos", 2) in got  # nudo inexistente
    assert ("Tramos", 3) in got  # estado fuera de la lista
    msg = {(e["sheet"], e["row"]): e["message"] for e in p["errors"]}
    assert "Cota" in msg[("Nudos", 3)] and "NO-EXISTE" in msg[("Tramos", 2)] and "pésimo" in msg[("Tramos", 3)]
    r = client.post(f"/api/projects/{demo}/sig/import/apply", files={"file": ("x.xlsx", content, XLSX)})
    assert r.status_code == 422 and r.json()["created"] is False
    assert client.get(f"/api/projects/{demo}/versions").json()[0]["number"] == 1  # nada aplicado


def test_actualizacion_parcial_solo_cambia_columnas_presentes(client):
    pid = create_demo(client, "APR parcial")
    before = {f["id"]: f for f in client.get(f"/api/projects/{pid}/network").json()["network"]["features"]}
    content = xlsx({"Tramos": [["ID", "Estado", "Inspección 2026"], ["P-05", "malo", "fisura"], ["P-06", "bueno", None]]})
    p = preview(client, pid, content)
    assert p["ok"], p["errors"]
    changes = {m["id"]: {c["field"]: (c["old"], c["new"]) for c in m["changes"]} for m in p["modified"]}
    assert changes == {"P-05": {"Estado": ("regular", "malo"), "Inspección 2026": (None, "fisura")},
                       "P-06": {"Estado": ("malo", "bueno")}}
    r = client.post(f"/api/projects/{pid}/sig/import/apply", files={"file": ("p.xlsx", content, XLSX)},
                    data={"base_version": 1})
    assert r.status_code == 200 and r.json()["version"] == 2
    after = {f["id"]: f for f in client.get(f"/api/projects/{pid}/network").json()["network"]["features"]}
    for fid in before:
        a, b = dict(before[fid]["properties"]), dict(after[fid]["properties"])
        if fid == "P-05":
            assert b["condition"] == "malo" and b["attributes"] == {"Inspección 2026": "fisura"}
            a.pop("condition"), b.pop("condition"), a.pop("attributes"), b.pop("attributes")
        elif fid == "P-06":
            assert b["condition"] == "bueno"
            a.pop("condition"), b.pop("condition")
        assert a == b, fid
        assert before[fid]["geometry"] == after[fid]["geometry"], fid
    # Versión base desactualizada → conflicto.
    r = client.post(f"/api/projects/{pid}/sig/import/apply", files={"file": ("p.xlsx", content, XLSX)},
                    data={"base_version": 1})
    assert r.status_code == 409


def test_nuevos_sin_id_reciben_id_unico_y_eliminar_es_opcional(client):
    pid = create_demo(client, "APR ids")
    content = xlsx({"Clientes": [["ID", "Nombre", "Consumo", "Unidad", "Nudo"], [None, "Nuevo A", 15, "m3/mes", "J-3"],
                                 [None, "Nuevo B", 15, "m3/mes", "J-4"]]})
    p = preview(client, pid, content)
    assert p["ok"] and len(p["new"]) == 2 and p["deleted"] == []
    ids = [n["id"] for n in p["new"]]
    assert len(set(ids)) == 2 and all(i.startswith("C") for i in ids)
    p2 = preview(client, pid, content, delete_missing="true")
    assert len(p2["deleted"]) == 30 and all(d["sheet"] == "Clientes" for d in p2["deleted"])


def test_utm_y_csv_por_hoja(client):
    pid = create_demo(client, "APR csv")
    doc = client.get(f"/api/projects/{pid}/network").json()
    j1 = next(f for f in doc["network"]["features"] if f["id"] == "J-1")
    from app.services.geometry import to_metric

    e, n = to_metric(32719).transform(*j1["geometry"]["coordinates"])
    csv_text = f"ID;Este;Norte;Cota;Nombre del sector\nJ-NUEVO;{e + 50:.3f};{n:.3f};239,5;Norte\n".replace(".", ",")
    p = preview(client, pid, csv_text.encode(), name="nudos.csv", sheet="Nudos", utm_zone="19", hemisphere="S")
    assert p["ok"], p["errors"]
    assert [x["id"] for x in p["new"]] == ["J-NUEVO"]
    r = client.post(f"/api/projects/{pid}/sig/import/apply", files={"file": ("nudos.csv", csv_text.encode(), "text/csv")},
                    data={"sheet": "Nudos"})
    assert r.status_code == 200, r.text
    doc = client.get(f"/api/projects/{pid}/network").json()
    node = next(f for f in doc["network"]["features"] if f["id"] == "J-NUEVO")
    e2, n2 = to_metric(32719).transform(*node["geometry"]["coordinates"])
    assert abs(e2 - (e + 50)) < 0.01 and abs(n2 - n) < 0.01
    assert node["properties"]["elevation"] == 239.5 and node["properties"]["attributes"] == {"Nombre del sector": "Norte"}
    out = client.get(f"/api/projects/{pid}/sig/export.csv", params={"sheet": "nudos"})
    assert out.status_code == 200 and "Nombre del sector" in out.content.decode("utf-8-sig").splitlines()[0]
