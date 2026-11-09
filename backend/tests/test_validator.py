"""Validador: un caso por cada error bloqueante y por cada advertencia (vía POST /validate)."""
import pytest

from tests.helpers import fc, node, pipe

R = node("R1", "reservoir", lon=-70.651, head=80.0, elevation=80.0)
J1 = node("J1", lon=-70.650, elevation=40.0, base_demand=2.0)
J2 = node("J2", lon=-70.649, elevation=41.0, base_demand=1.5)
P1 = pipe("P1", "R1", "J1", [[-70.651, -33.45], [-70.650, -33.45]])
P2 = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.649, -33.45]])


@pytest.fixture(scope="module")
def pid(client):
    return client.post("/api/projects", json={"name": "Validador"}).json()["id"]


def validate(client, pid, *features, options=None, aux=None):
    body = {"network": fc(*features)}
    if options:
        body["options"] = options
    if aux is not None:
        body["aux"] = aux
    r = client.post(f"/api/projects/{pid}/validate", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def codes(report, key):
    return {i["code"] for i in report[key]}


def test_valid_network_has_no_errors(client, pid):
    rep = validate(client, pid, R, J1, J2, P1, P2)
    assert rep["ok"] and rep["errors"] == []


# ── Errores bloqueantes ──────────────────────────────────────────────────

def test_error_empty_network(client, pid):
    assert "E_EMPTY_NETWORK" in codes(validate(client, pid), "errors")


def test_error_no_source(client, pid):
    rep = validate(client, pid, J1, J2, P2)
    assert "E_NO_SOURCE" in codes(rep, "errors") and not rep["ok"]


def test_error_link_without_valid_node(client, pid):
    rep = validate(client, pid, R, J1, P1, pipe("P9", "J1", "J99"))
    assert "E_LINK_NODE" in codes(rep, "errors")
    issue = next(i for i in rep["errors"] if i["code"] == "E_LINK_NODE")
    assert issue["element_id"] == "P9" and "J99" in issue["message"]


def test_error_link_same_start_and_end(client, pid):
    rep = validate(client, pid, R, J1, P1, pipe("P8", "J1", "J1"))
    assert "E_LINK_NODE" in codes(rep, "errors")


def test_error_diameter_not_in_catalog(client, pid):
    bad = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.649, -33.45]], material="PVC", dn=105, pipe_class="C10")
    rep = validate(client, pid, R, J1, J2, P1, bad)
    assert "E_DIAMETER_NOT_IN_CATALOG" in codes(rep, "errors")


def test_error_catalog_item_not_found(client, pid):
    bad = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.649, -33.45]], catalog_pipe_id=999999)
    assert "E_DIAMETER_NOT_IN_CATALOG" in codes(validate(client, pid, R, J1, J2, P1, bad), "errors")


def test_error_duplicate_ids(client, pid):
    dup = node("J1", lon=-70.648, elevation=40.0, base_demand=1.0)
    rep = validate(client, pid, R, J1, J2, dup, P1, P2)
    assert "E_DUPLICATE_ID" in codes(rep, "errors")


def test_error_invalid_id(client, pid):
    bad = node("J 3", lon=-70.648, elevation=40.0)
    rep = validate(client, pid, R, J1, bad, P1, pipe("P3", "J1", "J 3"))
    assert "E_INVALID_ID" in codes(rep, "errors")


def test_error_missing_parameters(client, pid):
    no_elev = node("J2", lon=-70.649, base_demand=1.0)  # sin cota
    no_rough = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.649, -33.45]], roughness=None)
    rep = validate(client, pid, R, J1, no_elev, P1, no_rough)
    missing = [i for i in rep["errors"] if i["code"] == "E_MISSING_PARAM"]
    assert {i["element_id"] for i in missing} >= {"J2", "P2"}


def test_error_missing_pda_parameters(client, pid):
    rep = validate(client, pid, R, J1, J2, P1, P2,
                   options={"demand_model": "PDA", "minimum_pressure": 20, "required_pressure": 10})
    assert "E_MISSING_PARAM" in codes(rep, "errors")


def test_error_undefined_pattern(client, pid):
    j = node("J2", lon=-70.649, elevation=41.0, base_demand=1.0, demand_pattern="PX")
    rep = validate(client, pid, R, J1, j, P1, P2)
    assert any(i["code"] == "E_MISSING_PARAM" and "PX" in i["message"] for i in rep["errors"])


def test_error_isolated_node(client, pid):
    rep = validate(client, pid, R, J1, J2, P1, P2, node("J7", lon=-70.640, elevation=40.0, base_demand=1.0))
    assert "E_ISOLATED_NODE" in codes(rep, "errors")


# ── Advertencias ─────────────────────────────────────────────────────────

def test_warning_doubtful_elevation_assumed(client, pid):
    j = node("J2", lon=-70.649, elevation=41.0, base_demand=1.0, elevation_source="supuesta")
    rep = validate(client, pid, R, J1, j, P1, P2)
    assert rep["ok"] and "W_ELEVATION_DOUBTFUL" in codes(rep, "warnings")


def test_warning_doubtful_elevation_jump(client, pid):
    j = node("J2", lon=-70.649, elevation=400.0, base_demand=1.0)
    rep = validate(client, pid, R, J1, j, P1, P2)
    assert any(i["code"] == "W_ELEVATION_DOUBTFUL" and i["element_id"] == "J2" for i in rep["warnings"])


def test_warning_short_pipe(client, pid):
    short = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.650005, -33.45]])  # ~0,46 m en planta
    j = node("J2", lon=-70.650005, elevation=40.0, base_demand=1.0)
    rep = validate(client, pid, R, J1, j, P1, short)
    assert "W_SHORT_PIPE" in codes(rep, "warnings")


def test_warning_node_without_demand(client, pid):
    j = node("J2", lon=-70.649, elevation=41.0, base_demand=0.0)
    rep = validate(client, pid, R, J1, j, P1, P2)
    assert any(i["code"] == "W_NO_DEMAND" and i["element_id"] == "J2" for i in rep["warnings"])


def test_warning_criteria_out_of_range_dn(client, pid):
    small = pipe("P2", "J1", "J2", [[-70.650, -33.45], [-70.649, -33.45]], material="PVC", dn=63, pipe_class="C10",
                 inner_diameter_mm=58.0)
    rep = validate(client, pid, R, J1, J2, P1, small)
    assert any(i["code"] == "W_CRITERIA" and "DN 63" in i["message"] for i in rep["warnings"])


def test_warning_criteria_roughness_range_for_formula(client, pid):
    # C = 150 interpretado como ε = 150 mm en Darcy-Weisbach: fuera de rango típico
    rep = validate(client, pid, R, J1, J2, P1, P2, options={"headloss": "D-W"})
    assert any(i["code"] == "W_CRITERIA" and "rugosidad" in i["message"] for i in rep["warnings"])


def test_simulate_is_blocked_by_errors(client, pid):
    r = client.put(f"/api/projects/{pid}/network", json={"network": fc(J1, J2, P2), "kind": "manual"})
    assert r.status_code == 200
    v = r.json()["version"]
    r = client.post(f"/api/projects/{pid}/simulate", json={"model_version": v})
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "blocked"
    assert "E_NO_SOURCE" in {i["code"] for i in body["validation"]["errors"]}


def test_structural_errors_cannot_be_saved(client, pid):
    r = client.put(f"/api/projects/{pid}/network", json={"network": fc(R, J1, P1, pipe("P9", "J1", "J99"))})
    assert r.status_code == 422
    assert "E_LINK_NODE" in {i["code"] for i in r.json()["validation"]["errors"]}
