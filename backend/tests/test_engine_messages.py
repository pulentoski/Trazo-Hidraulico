"""Traducción al español de los mensajes reales del motor (textos capturados de OWA-EPANET 2.3.5)."""
from app.hydraulic.engine import run_model
from app.hydraulic.messages import parse_report, translate_exception
from app.schemas.network import NetworkModel

REPORT = """
  WARNING: Negative pressures at 0:00:00 hrs.
  WARNING: Node J2 disconnected at 0:00:00 hrs
  WARNING: System disconnected because of Link P2
  WARNING: Pump B1 closed because cannot deliver head at 0:00:00 hrs.
  WARNING: FCV V1 open but cannot deliver flow at 1:00:00 hrs.
  WARNING: PRV V2 open but cannot deliver pressure at 2:00:00 hrs.
  WARNING: System unbalanced at 3:00:00 hrs.
  Error 203: undefined node J9 in [PIPES] section:
"""


def test_parse_report_translates_all_categories():
    msgs = {m.code: m for m in parse_report(REPORT)}
    assert "Presiones negativas" in msgs["NEGATIVE_PRESSURE"].message
    assert msgs["DISCONNECTED_NODE"].element_id == "J2"
    assert "desconectado" in msgs["DISCONNECTED_NODE"].message
    assert msgs["DISCONNECTED_SYSTEM"].element_id == "P2"
    assert "bomba B1" in msgs["PUMP_OUT_OF_RANGE"].message
    assert "no puede entregar la altura" in msgs["PUMP_OUT_OF_RANGE"].message
    assert msgs["VALVE_OUT_OF_RANGE"].element_id in {"V1", "V2"}
    assert msgs["UNBALANCED"].severity == "error"
    assert "desequilibrado" in msgs["UNBALANCED"].message
    assert msgs["ENGINE_ERROR_203"].element_id == "J9"
    assert "nudo no definido" in msgs["ENGINE_ERROR_203"].message


def test_exception_translation():
    m = translate_exception(Exception("Error 224: no tanks or reservoirs in network"))
    assert m.severity == "error" and "sin fuente" in m.message


def _model(features, **opts):
    return NetworkModel.model_validate({"options": opts, "network": {"type": "FeatureCollection", "features": features}})


def _node(i, kind="junction", x=0.0, **p):
    return {"type": "Feature", "id": i, "geometry": {"type": "Point", "coordinates": [x, 0.0]},
            "properties": {"element": "node", "kind": kind, **p}}


def _pipe(i, a, b, length=100.0, d=100.0, **p):
    return {"type": "Feature", "id": i, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]},
            "properties": {"element": "link", "kind": "pipe", "from_node": a, "to_node": b,
                           "length_hydraulic_m": length, "inner_diameter_mm": d, "roughness": 140, **p}}


def test_engine_reports_negative_pressure_and_disconnection():
    model = _model([
        _node("R1", "reservoir", head=30.0, elevation=30.0),
        _node("J1", elevation=0.0, base_demand=1.0),
        _node("J2", elevation=0.0, base_demand=80.0),
        _node("J3", elevation=0.0, base_demand=1.0),
        _pipe("P1", "R1", "J1", 500, 100),
        _pipe("P2", "J1", "J2", 800, 50),
        _pipe("P3", "J2", "J3", 10, 100, initial_status="closed"),
    ])
    run = run_model(model)
    codes = {m.code for m in run.messages}
    assert run.ok
    assert "NEGATIVE_PRESSURE" in codes and "NEGATIVE_PRESSURE_NODE" in codes
    assert "DISCONNECTED_NODE" in codes


def test_engine_error_is_reported_in_spanish():
    model = _model([_node("J1", elevation=0.0, base_demand=1.0), _node("J2", elevation=0.0),
                    _pipe("P1", "J1", "J2")])
    run = run_model(model)
    assert not run.ok and run.results is None
    assert any("sin fuente" in m.message for m in run.messages)
