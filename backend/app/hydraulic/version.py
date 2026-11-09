"""Identificación del motor OWA-EPANET (wheel Python y runepanet compilado)."""
import importlib.metadata
import os
import subprocess
import tempfile
from functools import lru_cache

from epanet import toolkit as en

from app.core.config import get_settings

_PROBE_INP = """[JUNCTIONS]
 J1 0 1
[RESERVOIRS]
 R1 10
[PIPES]
 P1 R1 J1 10 100 130 0 Open
[OPTIONS]
 UNITS LPS
[END]
"""


def _read_build_info(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    data[k] = v
    except FileNotFoundError:
        pass
    return data


def _runepanet_banner(exe: str) -> str | None:
    """Ejecuta runepanet sobre una red mínima y extrae la línea 'Version' del reporte."""
    if not os.path.exists(exe):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        inp, rpt = os.path.join(tmp, "p.inp"), os.path.join(tmp, "p.rpt")
        with open(inp, "w", encoding="ascii") as fh:
            fh.write(_PROBE_INP)
        subprocess.run([exe, inp, rpt], capture_output=True, timeout=30, check=False)
        try:
            with open(rpt, encoding="latin-1") as fh:
                for line in fh:
                    if "Version" in line:
                        return line.strip(" *\n")
        except FileNotFoundError:
            return None
    return None


@lru_cache
def engine_info() -> dict[str, str | int | None]:
    s = get_settings()
    build = _read_build_info(s.epanet_build_info)
    return {
        "engine": "OWA-EPANET",
        "wheel_package": "owa-epanet",
        "wheel_version": importlib.metadata.version("owa-epanet"),
        "en_getversion": int(en.getversion()),
        "epanet_tag": build.get("EPANET_TAG"),
        "epanet_sha": build.get("EPANET_SHA"),
        "runepanet_banner": _runepanet_banner(s.runepanet),
    }
