"""Cálculos de la página «Gestión» (funciones puras, sin base de datos): se prueban con resultados conocidos.

Fechas en hora local del proyecto (sin zona); los meses se identifican como «AAAA-MM».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


# ── Períodos ──

def month_key(d: date | datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_start(key: str) -> date:
    y, m = key.split("-")
    return date(int(y), int(m), 1)


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def months_between(start: date, end: date) -> list[str]:
    """Meses «AAAA-MM» que tocan el rango [start, end] (ambos incluidos)."""
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        out.append(month_key(cur))
        cur = next_month(cur)
    return out


def days_in_month(key: str) -> int:
    s = month_start(key)
    return (next_month(s) - s).days


def previous_period(start: date, end: date) -> tuple[date, date]:
    """Período anterior de igual largo, inmediatamente antes de `start`."""
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def variation_pct(value: float | None, previous: float | None) -> float | None:
    """Variación porcentual respecto al período anterior (None si no hay base)."""
    if value is None or previous is None or abs(previous) < 1e-12:
        return None
    return round((value - previous) / abs(previous) * 100, 1)


def status_of(value: float | None, good: float, bad: float, higher_is_better: bool) -> str | None:
    """Semáforo de un indicador: «bueno», «regular» o «malo» según los umbrales configurados."""
    if value is None:
        return None
    if higher_is_better:
        return "bueno" if value >= good else "malo" if value <= bad else "regular"
    return "bueno" if value <= good else "malo" if value >= bad else "regular"


# ── Agua no contabilizada ──

def meter_volumes_by_month(readings: Iterable[tuple[datetime, float]]) -> dict[str, float]:
    """Lecturas acumuladas de un medidor (m³) → volumen por mes.

    Cada intervalo entre dos lecturas consecutivas se reparte entre los meses que cubre, en proporción al tiempo.
    Una lectura menor que la anterior (cambio de medidor) corta la serie sin sumar volumen negativo.
    """
    pts = sorted(readings)
    out: dict[str, float] = {}
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        dv, total = v1 - v0, (t1 - t0).total_seconds()
        if dv < 0 or total <= 0:
            continue
        cur = t0
        while cur < t1:
            nm = next_month(cur.date())
            edge = min(t1, datetime(nm.year, nm.month, 1, tzinfo=cur.tzinfo))
            share = (edge - cur).total_seconds() / total
            k = month_key(cur)
            out[k] = out.get(k, 0.0) + dv * share
            cur = edge
    return out


@dataclass
class NrwRow:
    month: str
    production_m3: float
    consumption_m3: float
    nrw_m3: float
    nrw_pct: float | None


def nrw(production_m3: float, consumption_m3: float) -> tuple[float, float | None]:
    """Agua no contabilizada (m³ y %) = producción − consumo facturado; % sobre la producción."""
    lost = production_m3 - consumption_m3
    return round(lost, 3), (round(lost / production_m3 * 100, 2) if production_m3 > 0 else None)


def nrw_monthly(production: dict[str, float], consumption: dict[str, float]) -> list[NrwRow]:
    """ANC mensual: solo los meses con producción medida."""
    rows = []
    for m in sorted(production):
        p, c = production[m], consumption.get(m, 0.0)
        lost, pct = nrw(p, c)
        rows.append(NrwRow(m, round(p, 3), round(c, 3), lost, pct))
    return rows


# ── Consumo ──

def dotacion(m3: float, dwellings: int, persons_per_dwelling: float, days: int) -> float | None:
    """Dotación real (L/hab/día) = consumo (m³) × 1000 / (viviendas × habitantes por vivienda × días)."""
    people = dwellings * persons_per_dwelling
    if people <= 0 or days <= 0:
        return None
    return round(m3 * 1000 / (people * days), 1)


CONSUMPTION_BINS = [(0, 10, "0–10 m³"), (10, 20, "10–20 m³"), (20, 30, "20–30 m³"), (30, 50, "30–50 m³"),
                    (50, float("inf"), "≥ 50 m³")]


def consumption_bin(m3_month: float) -> str:
    for lo, hi, label in CONSUMPTION_BINS:
        if lo <= m3_month < hi:
            return label
    return CONSUMPTION_BINS[-1][2]


def client_movements(months: list[str], readings: dict[str, set[str]], history: dict[str, list[str]]) -> dict[str, tuple[int, int, int]]:
    """Clientes activos, nuevos y dados de baja por mes, desde las lecturas.

    `readings`: mes → clientes con consumo registrado; `history`: cliente → meses con lectura (toda la historia).
    Nuevo = su primera lectura es de ese mes (salvo el primer mes del registro); baja = tuvo lectura el mes anterior y
    ninguna desde ese mes en adelante (solo si el registro sigue después).
    """
    first = {c: min(ms) for c, ms in history.items() if ms}
    last = {c: max(ms) for c, ms in history.items() if ms}
    data_first = min(first.values(), default="")
    data_last = max(last.values(), default="")
    out = {}
    for m in months:
        active = readings.get(m, set())
        # En el primer mes del registro todos los clientes «aparecen»: no se cuentan como nuevos.
        new = sum(1 for c in active if first.get(c) == m) if m > data_first else 0
        prev = month_key(month_start(m) - timedelta(days=1))
        # Sin lecturas posteriores en todo el registro no se puede saber si el cliente se fue: no se cuenta como baja.
        gone = sum(1 for lm in last.values() if lm == prev) if m <= data_last else 0
        out[m] = (len(active), new, gone)
    return out


# ── Continuidad del servicio ──

@dataclass
class OutageSpan:
    start: datetime
    end: datetime | None
    clients: int


def client_hours_by_month(outages: Iterable[OutageSpan], months: list[str], now: datetime) -> dict[str, float]:
    """Horas-cliente sin servicio por mes: duración × clientes afectados, repartida entre los meses que cubre.

    Un corte sin término se cuenta hasta `now`.
    """
    out = {m: 0.0 for m in months}
    for o in outages:
        end = o.end or now
        if end <= o.start or o.clients <= 0:
            continue
        cur = o.start
        while cur < end:
            nm = next_month(cur.date())
            edge = min(end, datetime(nm.year, nm.month, 1, tzinfo=cur.tzinfo))
            k = month_key(cur)
            if k in out:
                out[k] += (edge - cur).total_seconds() / 3600 * o.clients
            cur = edge
    return {k: round(v, 2) for k, v in out.items()}


# ── Mantenciones ──

def maintenance_status(next_date: date | None, done_on: date | None, frequency_days: int | None, today: date) -> str:
    """Estado de una mantención: «hecha» (tarea única cumplida), «atrasada» (próxima fecha vencida) o «pendiente»
    (al día). Una mantención periódica nunca queda «hecha»: al cumplirla avanza su próxima fecha."""
    if frequency_days is None and done_on is not None:
        return "hecha"
    if next_date is not None and next_date < today:
        return "atrasada"
    return "pendiente"


def advance(next_date: date, frequency_days: int, done_on: date) -> date:
    """Próxima fecha tras cumplir una mantención periódica: desde la fecha de cumplimiento más la frecuencia, sin
    quedar en el pasado respecto de la fecha programada original."""
    base = done_on if done_on >= next_date else next_date
    return base + timedelta(days=frequency_days)


# ── Cloro ──

def within(value: float, lo: float, hi: float) -> bool:
    return lo - 1e-12 <= value <= hi + 1e-12


# ── Planificación ──

def projection(base_m3_day: float, rate_pct: float, years: list[int]) -> list[tuple[int, float]]:
    """Demanda proyectada con crecimiento compuesto."""
    return [(n, round(base_m3_day * (1 + rate_pct / 100) ** n, 3)) for n in years]
