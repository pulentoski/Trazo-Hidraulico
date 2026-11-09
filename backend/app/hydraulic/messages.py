"""Traducción al español de advertencias y errores de OWA-EPANET.

Se leen las líneas del reporte (.rpt) que produce el motor en cada corrida y se
convierten en mensajes estructurados con código, severidad, elemento y hora.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

Severity = Literal["error", "warning", "info"]


class EngineMessage(BaseModel):
    code: str
    severity: Severity
    message: str
    original: str | None = None
    element_type: Literal["node", "link", "network"] | None = None
    element_id: str | None = None
    time: str | None = None


ERROR_CODES: dict[int, str] = {
    101: "memoria insuficiente",
    102: "no hay datos de red para procesar",
    110: "no es posible resolver las ecuaciones hidráulicas (revise conectividad, bombas y válvulas)",
    120: "no es posible resolver las ecuaciones de calidad",
    200: "uno o más errores en los datos de entrada",
    201: "error de sintaxis",
    202: "valor numérico ilegal",
    203: "nudo no definido",
    204: "tramo no definido",
    205: "patrón de tiempo no definido",
    206: "curva no definida",
    207: "intento de controlar una válvula de retención",
    208: "nudo especificado no válido",
    209: "valor ilegal para una propiedad de nudo",
    210: "tramo especificado no válido",
    211: "valor ilegal para una propiedad de tramo",
    212: "nudo de trazado no válido",
    213: "valor de opción ilegal",
    214: "línea con demasiados caracteres",
    215: "ID duplicado",
    216: "faltan datos de la bomba",
    217: "datos de energía no válidos para la bomba",
    219: "válvula conectada ilegalmente a un reservorio o estanque",
    220: "válvula conectada ilegalmente a otra válvula",
    221: "regla mal ubicada",
    222: "el tramo tiene el mismo nudo inicial y final",
    223: "no hay suficientes nudos en la red",
    224: "la red no tiene reservorios ni estanques (sin fuente)",
    225: "niveles de estanque no válidos",
    226: "no hay curva ni potencia para la bomba",
    227: "curva de bomba no válida",
    230: "la curva no tiene valores de X crecientes",
    233: "nudo sin tramos conectados",
    252: "formato de ID no válido",
    253: "no existen categorías de demanda",
    302: "no es posible abrir el archivo de entrada",
    303: "no es posible abrir el archivo de reporte",
    304: "no es posible abrir el archivo de resultados",
    308: "no es posible guardar los resultados",
    309: "no es posible escribir el reporte",
}

_PUMP_STATES = {
    "closed because cannot deliver head": "se cierra porque no puede entregar la altura requerida",
    "open but exceeds maximum flow": "opera abierta pero supera el caudal máximo de su curva",
    "open but cannot deliver head": "opera abierta pero no puede entregar la altura requerida",
}
_VALVE_STATES = {
    "open but cannot deliver pressure": "está abierta pero no puede mantener la presión de consigna",
    "open but cannot deliver flow": "está abierta pero no puede entregar el caudal de consigna",
    "closed because cannot deliver flow": "se cierra porque no puede entregar el caudal",
}
_VALVES = r"(?P<vtype>PRV|PSV|PBV|FCV|TCV|GPV|PCV)"
_T = r"(?P<t>\d+:\d{2}(?::\d{2})?)"


def _fmt_time(t: str | None) -> str:
    return f" a las {t} h" if t else ""


def _match_line(line: str) -> EngineMessage | None:
    s = line.strip()

    if m := re.match(rf"WARNING: Negative pressures at {_T} hrs", s):
        return EngineMessage(code="NEGATIVE_PRESSURE", severity="warning", original=s, element_type="network",
                             time=m["t"], message=f"Presiones negativas en la red{_fmt_time(m['t'])}.")
    if m := re.match(rf"WARNING: System unbalanced at {_T} hrs", s):
        return EngineMessage(code="UNBALANCED", severity="error", original=s, element_type="network", time=m["t"],
                             message=f"Sistema desequilibrado{_fmt_time(m['t'])}: el motor no convergió y los "
                                     "resultados no son confiables.")
    if m := re.match(rf"WARNING: System may be hydraulically unstable at {_T} hrs", s):
        return EngineMessage(code="UNSTABLE", severity="warning", original=s, element_type="network", time=m["t"],
                             message=f"El sistema puede ser hidráulicamente inestable{_fmt_time(m['t'])}.")
    if m := re.match(rf"WARNING: Node (?P<id>\S+) disconnected at {_T} hrs", s):
        return EngineMessage(code="DISCONNECTED_NODE", severity="warning", original=s, element_type="node",
                             element_id=m["id"], time=m["t"],
                             message=f"El nudo {m['id']} quedó desconectado de toda fuente{_fmt_time(m['t'])}.")
    if m := re.match(rf"WARNING: (?P<n>\d+) additional nodes disconnected at {_T} hrs", s):
        return EngineMessage(code="DISCONNECTED_NODE", severity="warning", original=s, element_type="network",
                             time=m["t"], message=f"Otros {m['n']} nudos desconectados{_fmt_time(m['t'])}.")
    if m := re.match(r"WARNING: System disconnected because of Link (?P<id>\S+)", s):
        return EngineMessage(code="DISCONNECTED_SYSTEM", severity="warning", original=s, element_type="link",
                             element_id=m["id"], message=f"La red quedó desconectada a causa del tramo {m['id']}.")
    if m := re.match(rf"WARNING: Pump (?P<id>\S+) (?P<state>.+?) at {_T} hrs", s):
        state = _PUMP_STATES.get(m["state"], m["state"])
        return EngineMessage(code="PUMP_OUT_OF_RANGE", severity="warning", original=s, element_type="link",
                             element_id=m["id"], time=m["t"],
                             message=f"La bomba {m['id']} {state}{_fmt_time(m['t'])}.")
    if m := re.match(rf"WARNING: {_VALVES} (?P<id>\S+) (?P<state>.+?) at {_T} hrs", s):
        state = _VALVE_STATES.get(m["state"], m["state"])
        return EngineMessage(code="VALVE_OUT_OF_RANGE", severity="warning", original=s, element_type="link",
                             element_id=m["id"], time=m["t"],
                             message=f"La válvula {m['vtype']} {m['id']} {state}{_fmt_time(m['t'])}.")
    if m := re.match(r"Error (?P<code>\d{3}):\s*(?P<msg>.*?):?$", s):
        code = int(m["code"])
        detail = m["msg"]
        base = ERROR_CODES.get(code, "error del motor")
        element = None
        if mm := re.search(r"undefined (?:node|link|pattern|curve) (?P<id>\S+)", detail):
            element = mm["id"]
        text = f"Error {code} del motor: {base}"
        if detail and code not in (200,):
            text += f" ({_translate_detail(detail)})"
        return EngineMessage(code=f"ENGINE_ERROR_{code}", severity="error", original=s, element_id=element,
                             message=text + ".")
    if s.startswith("WARNING:"):
        return EngineMessage(code="ENGINE_WARNING", severity="warning", original=s,
                             message=f"Advertencia del motor: {s[8:].strip()}")
    return None


def _translate_detail(detail: str) -> str:
    out = detail
    for en_txt, es_txt in (("undefined node", "nudo no definido"), ("undefined link", "tramo no definido"),
                           ("undefined pattern", "patrón no definido"), ("undefined curve", "curva no definida"),
                           ("in [", "en la sección ["), (" section", ""), ("illegal", "ilegal"),
                           ("duplicate ID", "ID duplicado")):
        out = out.replace(en_txt, es_txt)
    return out


def parse_report(text: str) -> list[EngineMessage]:
    """Extrae y traduce los mensajes relevantes del reporte del motor (sin duplicados)."""
    messages: list[EngineMessage] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("WARNING") or s.startswith("Error ")):
            continue
        if s in seen:
            continue
        seen.add(s)
        msg = _match_line(s)
        if msg is not None:
            messages.append(msg)
    return messages


def translate_exception(exc: Exception) -> EngineMessage:
    text = str(exc).strip()
    msg = _match_line(text)
    if msg is not None:
        return msg
    return EngineMessage(code="ENGINE_ERROR", severity="error", original=text, message=f"Error del motor: {text}")
