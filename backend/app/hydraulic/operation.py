"""Operación de bombas y válvulas en EPANET: horario por hora, control por nivel y curva por puntos.

- Horario (24 valores 0/1, como la columna F de SimulaEST1): controles `AT CLOCKTIME` en cada cambio; el estado
  de la hora 0 es el estado inicial. Se repite cada día en simulaciones de más de 24 h.
- Control por nivel: `LINK x OPEN IF NODE estanque BELOW a` y `LINK x CLOSED IF NODE estanque ABOVE b`.
- Horario + nivel: reglas ([RULES]) — fuera del horario queda apagada; dentro, el nivel la enciende y apaga.
- En válvulas «encender» = volver a su consigna (una válvula abierta a la fuerza ignora su consigna).
- Curva por puntos: curva `CB_<id>` en [CURVES] (1 punto o 3 o más, caudal L/s – altura m).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.network import LinkFeature, NetworkModel


def _num(x: float) -> str:
    return f"{float(x):.10g}"


def _clock(h: int) -> str:
    return f"{h % 24}:00"


def curve_id(link_id: str) -> str:
    return f"CB_{link_id}"[:31]


def windows(schedule: list[int]) -> list[tuple[int, int, bool]]:
    """Tramos contiguos (inicio, fin exclusivo, encendido) del horario de 24 h."""
    out: list[tuple[int, int, bool]] = []
    start = 0
    for h in range(1, 25):
        if h == 24 or bool(schedule[h]) != bool(schedule[start]):
            out.append((start, h, bool(schedule[start])))
            start = h
    return out


@dataclass
class Operation:
    curves: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    initial: dict[str, str] = field(default_factory=dict)  # link → "Open" | "Closed" | consigna (válvulas)


def _on(lk: LinkFeature, rule: bool = False) -> str:
    p = lk.properties
    if p.kind == "pump":
        return "STATUS IS OPEN" if rule else "OPEN"
    return f"SETTING IS {_num(p.valve_setting or 0)}" if rule else _num(p.valve_setting or 0)


def _off(rule: bool = False) -> str:
    return "STATUS IS CLOSED" if rule else "CLOSED"


def build(model: NetworkModel) -> Operation:
    op = Operation()
    for lk in model.network.links():
        p = lk.properties
        if p.kind == "pump" and p.curve_points:
            cid = curve_id(lk.id)
            for q, h in p.curve_points:
                op.curves.append(f" {cid}\t{_num(q)}\t{_num(h)}")
        if p.kind not in ("pump", "valve"):
            continue
        sched, lc = p.schedule, p.level_control
        kind = "PUMP" if p.kind == "pump" else "VALVE"
        if sched and not lc:
            op.initial[lk.id] = "Open" if sched[0] else "Closed"
            for h in range(1, 24):
                if bool(sched[h]) != bool(sched[h - 1]):
                    act = _on(lk) if sched[h] else _off()
                    op.controls.append(f" LINK {lk.id} {act} AT CLOCKTIME {_clock(h)}")
            if p.kind == "valve" and sched[0]:
                op.initial.pop(lk.id)
        elif lc and not sched:
            op.controls.append(f" LINK {lk.id} {_on(lk)} IF NODE {lc.tank} BELOW {_num(lc.on_below)}")
            op.controls.append(f" LINK {lk.id} {_off()} IF NODE {lc.tank} ABOVE {_num(lc.off_above)}")
        elif lc and sched:
            if not sched[0]:
                op.initial[lk.id] = "Closed"
            for k, (a, b, on) in enumerate(windows(sched)):
                end = "24:00" if b == 24 else _clock(b)
                if not on:
                    op.rules += [f"RULE {lk.id[:20]}_FUERA_{k}", f"IF SYSTEM CLOCKTIME >= {_clock(a)}",
                                 f"AND SYSTEM CLOCKTIME < {end}", f"THEN {kind} {lk.id} {_off(True)}",
                                 "PRIORITY 3", ""]
                else:
                    op.rules += [f"RULE {lk.id[:20]}_ENC_{k}", f"IF TANK {lc.tank} LEVEL BELOW {_num(lc.on_below)}",
                                 f"AND SYSTEM CLOCKTIME >= {_clock(a)}", f"AND SYSTEM CLOCKTIME < {end}",
                                 f"THEN {kind} {lk.id} {_on(lk, True)}", "PRIORITY 1", ""]
            op.rules += [f"RULE {lk.id[:20]}_NIVEL", f"IF TANK {lc.tank} LEVEL ABOVE {_num(lc.off_above)}",
                         f"THEN {kind} {lk.id} {_off(True)}", "PRIORITY 2", ""]
    return op
