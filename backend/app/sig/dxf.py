"""Exportación DXF (R12 ASCII) por capas, en coordenadas UTM del proyecto.

Capas: AP_DN<diámetro> (red de agua potable por diámetro), AP_BOMBAS, VALVULAS, CLIENTES, ESTANQUES,
RESERVORIOS, NUDOS, GRIFOS, POZOS y TEXTO_ID (etiquetas).
"""
from __future__ import annotations

from app.schemas.network import NetworkModel
from app.services.geometry import to_metric

COLORS = {"VALVULAS": 1, "CLIENTES": 3, "ESTANQUES": 5, "RESERVORIOS": 5, "NUDOS": 8, "GRIFOS": 1, "POZOS": 6,
          "AP_BOMBAS": 6, "TEXTO_ID": 7}
DN_COLORS = [4, 2, 30, 1, 6, 5, 3, 140, 200, 40]


def _layer_name(dn: int | None) -> str:
    return f"AP_DN{dn}" if dn else "AP_SIN_DN"


def write_dxf(model: NetworkModel, srid: int) -> bytes:
    tr = to_metric(srid)

    def xy(lon: float, lat: float) -> tuple[float, float]:
        x, y = tr.transform(lon, lat)
        return float(x), float(y)

    ents: list[str] = []
    layers: dict[str, int] = dict(COLORS)
    dns = sorted({lk.properties.dn for lk in model.network.links() if lk.properties.kind == "pipe"}, key=lambda d: d or 0)
    for i, dn in enumerate(dns):
        layers[_layer_name(dn)] = DN_COLORS[i % len(DN_COLORS)]

    def g(code: int, value) -> None:
        ents.append(f"{code}\n{value}")

    def point(layer: str, x: float, y: float) -> None:
        g(0, "POINT"); g(8, layer); g(10, f"{x:.3f}"); g(20, f"{y:.3f}"); g(30, "0.0")

    def circle(layer: str, x: float, y: float, r: float) -> None:
        g(0, "CIRCLE"); g(8, layer); g(10, f"{x:.3f}"); g(20, f"{y:.3f}"); g(30, "0.0"); g(40, f"{r:.3f}")

    def text(x: float, y: float, s: str, h: float = 1.5) -> None:
        g(0, "TEXT"); g(8, "TEXTO_ID"); g(10, f"{x:.3f}"); g(20, f"{y:.3f}"); g(30, "0.0"); g(40, f"{h:.2f}")
        g(1, s.replace("\n", " "))

    def polyline(layer: str, pts: list[tuple[float, float]]) -> None:
        g(0, "POLYLINE"); g(8, layer); g(66, 1); g(10, "0.0"); g(20, "0.0"); g(30, "0.0"); g(70, 0)
        for x, y in pts:
            g(0, "VERTEX"); g(8, layer); g(10, f"{x:.3f}"); g(20, f"{y:.3f}"); g(30, "0.0")
        g(0, "SEQEND"); g(8, layer)

    for lk in model.network.links():
        pts = [xy(*c) for c in lk.geometry.coordinates]
        k = lk.properties.kind
        layer = _layer_name(lk.properties.dn) if k == "pipe" else ("AP_BOMBAS" if k == "pump" else "VALVULAS")
        polyline(layer, pts)
        mx, my = pts[len(pts) // 2] if len(pts) > 2 else ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
        text(mx, my, lk.id)
    for n in model.network.nodes():
        x, y = xy(*n.geometry.coordinates)
        layer = {"junction": "NUDOS", "tank": "ESTANQUES", "reservoir": "RESERVORIOS"}[n.properties.kind]
        point(layer, x, y)
        if n.properties.kind != "junction":
            circle(layer, x, y, 4.0)
        text(x + 1, y + 1, n.id)
    for s in model.network.shutoffs():
        x, y = xy(*s.geometry.coordinates)
        point("VALVULAS", x, y)
        circle("VALVULAS", x, y, 1.0)
        text(x + 1, y + 1, s.id)
    for h in model.network.hydrants():
        x, y = xy(*h.geometry.coordinates)
        point("GRIFOS", x, y)
        circle("GRIFOS", x, y, 1.5)
        text(x + 1, y + 1, h.id)
    for w in model.network.wells():
        x, y = xy(*w.geometry.coordinates)
        point("POZOS", x, y)
        circle("POZOS", x, y, 2.5)
        text(x + 1, y + 1, w.id)
    for c in model.network.clients():
        x, y = xy(*c.geometry.coordinates)
        point("CLIENTES", x, y)
        circle("CLIENTES", x, y, 0.5)

    head = ["0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1009\n9\n$INSUNITS\n70\n6\n0\nENDSEC",
            "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n" + str(len(layers) + 1),
            "0\nLAYER\n2\n0\n70\n0\n62\n7\n6\nCONTINUOUS"]
    for name, color in layers.items():
        head.append(f"0\nLAYER\n2\n{name}\n70\n0\n62\n{color}\n6\nCONTINUOUS")
    head.append("0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES")
    body = "\n".join(head + ents + ["0\nENDSEC\n0\nEOF\n"])
    return body.encode("cp1252", errors="replace")
