"""Verificación del motor hidráulico en el build y en el arranque.

Comprueba que el wheel owa-epanet es exactamente 2.3.5 y que el ejecutable
runepanet compilado desde el tag v2.3.5 funciona y declara la versión 2.3.05.
EN_getversion se registra, pero NO se usa como prueba de equivalencia: la
equivalencia la demuestra tests/test_reference_networks.py.
"""
import sys

sys.path.insert(0, ".")
from app.hydraulic.version import engine_info  # noqa: E402

info = engine_info()
print("Motor:", info)
problems = []
if info["wheel_version"] != "2.3.5":
    problems.append(f"owa-epanet {info['wheel_version']} != 2.3.5")
if info["runepanet_banner"] is None or "2.3.05" not in info["runepanet_banner"]:
    problems.append(f"runepanet no declara 2.3.05: {info['runepanet_banner']!r}")
if info["epanet_sha"] != "444725fbf16ab28b0470ef0ed281dc4849d49583":
    problems.append(f"SHA inesperado: {info['epanet_sha']}")
if problems:
    print("ERROR de verificación del motor:", "; ".join(problems), file=sys.stderr)
    sys.exit(1)
print("Motor verificado.")
