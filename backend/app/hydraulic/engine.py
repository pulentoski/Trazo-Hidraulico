"""Ejecución del motor OWA-EPANET 2.3.5: modelo → .inp → simulación → resultados.

Se usa EN_runproject (el mismo camino que el ejecutable runepanet): el motor escribe el
reporte (.rpt) y el binario de resultados (.out). Los resultados se leen del .out en
todos los pasos de reporte, y las advertencias del .rpt se traducen al español.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field

from epanet import toolkit as en

from app.hydraulic.inp_writer import write_inp
from app.hydraulic.messages import EngineMessage, parse_report, translate_exception
from app.hydraulic.out_reader import OutFileError, OutResults, read_out
from app.hydraulic.version import engine_info
from app.schemas.network import NetworkModel

# El toolkit es reentrante por proyecto, pero se serializa: EPANET crea su archivo hidráulico
# temporal en el directorio de trabajo, por lo que cada corrida cambia a un directorio propio.
ENGINE_LOCK = threading.RLock()


@contextmanager
def engine_workdir(prefix: str = "trazo-"):
    """Directorio temporal de trabajo para el motor (el sistema de archivos raíz es de solo lectura)."""
    with ENGINE_LOCK, tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(previous)


@dataclass
class EngineRun:
    inp_text: str
    inp_sha256: str
    ok: bool
    messages: list[EngineMessage] = field(default_factory=list)
    results: OutResults | None = None
    report_text: str = ""
    elapsed_ms: float = 0.0
    engine: dict = field(default_factory=dict)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_inp_file(inp_path: str, workdir: str) -> tuple[bool, list[EngineMessage], OutResults | None, str]:
    rpt = os.path.join(workdir, "model.rpt")
    out = os.path.join(workdir, "model.out")
    ok = True
    messages: list[EngineMessage] = []
    ph = en.createproject()
    try:
        with warnings.catch_warnings():
            # El wheel emite un Warning genérico de Python; el detalle se lee del reporte.
            warnings.simplefilter("ignore")
            try:
                en.runproject(ph, inp_path, rpt, out, None)
            except Exception as exc:  # noqa: BLE001
                ok = False
                exc_msg = translate_exception(exc)
                messages.append(exc_msg)
    finally:
        en.deleteproject(ph)

    report = ""
    if os.path.exists(rpt):
        with open(rpt, encoding="latin-1") as fh:
            report = fh.read()
    parsed = parse_report(report)
    if not ok:
        # Los errores del reporte son más específicos que la excepción genérica (p. ej. Error 200).
        specific = [m for m in parsed if m.severity == "error"]
        if specific:
            messages = specific + [m for m in messages if m.code not in {s.code for s in specific}]
        messages += [m for m in parsed if m.severity != "error"]
    else:
        messages = parsed

    results = None
    if ok and os.path.exists(out):
        try:
            results = read_out(out)
        except OutFileError as exc:
            ok = False
            messages.append(EngineMessage(code="OUTPUT_ERROR", severity="error",
                                          message=f"No fue posible leer los resultados del motor: {exc}"))
    return ok, messages, results, report


def run_model(model: NetworkModel) -> EngineRun:
    inp_text = write_inp(model)
    digest = sha256_text(inp_text)
    t0 = time.perf_counter()
    with engine_workdir() as tmp:
        inp_path = os.path.join(tmp, "model.inp")
        with open(inp_path, "w", encoding="latin-1", errors="replace") as fh:
            fh.write(inp_text)
        ok, messages, results, report = run_inp_file(inp_path, tmp)
    elapsed = (time.perf_counter() - t0) * 1000

    if results is not None:
        messages += negative_pressure_details(results)
    return EngineRun(inp_text=inp_text, inp_sha256=digest, ok=ok, messages=messages, results=results,
                     report_text=report, elapsed_ms=elapsed, engine=engine_info())


def negative_pressure_details(res: OutResults, limit: int = 8) -> list[EngineMessage]:
    """Detalle por nudo de las presiones negativas (el motor solo informa la hora)."""
    p = res.nodes["pressure"]
    if p.size == 0:
        return []
    worst = p.min(axis=0)
    idx = [i for i in range(len(res.node_ids)) if worst[i] < -1e-6]
    idx.sort(key=lambda i: worst[i])
    out = []
    for i in idx[:limit]:
        out.append(EngineMessage(
            code="NEGATIVE_PRESSURE_NODE", severity="warning", element_type="node", element_id=res.node_ids[i],
            message=f"Presión negativa en el nudo {res.node_ids[i]}: mínimo {_es(worst[i])} m.",
        ))
    if len(idx) > limit:
        out.append(EngineMessage(code="NEGATIVE_PRESSURE_NODE", severity="warning", element_type="network",
                                 message=f"Otros {len(idx) - limit} nudos con presión negativa."))
    return out


def _es(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")
