"""Identificación del motor. EN_getversion se registra pero no se usa como prueba de equivalencia:
la equivalencia entre el wheel y runepanet la demuestra test_reference_networks.py."""
import importlib.metadata

from app.hydraulic.version import engine_info

EXPECTED_SHA = "444725fbf16ab28b0470ef0ed281dc4849d49583"


def test_wheel_version_is_pinned():
    assert importlib.metadata.version("owa-epanet") == "2.3.5"


def test_runepanet_built_from_pinned_tag():
    info = engine_info()
    assert info["epanet_tag"] == "v2.3.5"
    assert info["epanet_sha"] == EXPECTED_SHA
    assert info["runepanet_banner"] is not None and "2.3.05" in info["runepanet_banner"]
