"""Cuarteles de corta: sectores que quedan aislados al cerrar el conjunto mínimo de válvulas que los rodea.

Cada válvula de corte divide su tubería en tramos parciales. Los cuarteles son las componentes conexas de la
red cuando se «cortan» todas las válvulas operativas (nudos + tramos parciales unidos por tuberías, bombas y
válvulas de control). Las válvulas a cerrar de un cuartel son las que tienen un lado dentro y otro fuera.

Al cerrar un cuartel también pueden quedar sin agua sectores aguas abajo (sin otro camino a una fuente):
se informan aparte como afectados indirectos.
"""
from __future__ import annotations

from collections import defaultdict

from app.schemas.network import NetworkModel
from app.schemas.sig import Sector, SectorPiece, SectorsResult


class _UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def compute_sectors(model: NetworkModel, *, project_id: str = "", version: int = 0) -> SectorsResult:
    net = model.network
    nodes = {n.id: n for n in net.nodes()}
    links = net.links()
    inoperative = sorted(s.id for s in net.shutoffs() if s.properties.condition == "inoperativo")
    valves_by_link: dict[str, list] = defaultdict(list)
    for s in net.shutoffs():
        if s.properties.condition != "inoperativo":
            valves_by_link[s.properties.link].append(s)
    closed_links = {lk.id for lk in links if lk.properties.initial_status == "closed"
                    or lk.properties.condition == "fuera_servicio"}

    uf = _UF()
    pieces: list[tuple[str, str, float, float, float]] = []  # (clave, link, inicio, fin, metros)
    valve_sides: dict[str, tuple[str, str, str]] = {}  # válvula → (pieza antes, pieza después, estado)
    piece_ends: dict[str, list[str]] = defaultdict(list)  # pieza → nudos extremos
    for n in nodes:
        uf.find("n:" + n)
    for lk in links:
        p = lk.properties
        length = (p.length_hydraulic_m or p.length_plan_m or 0.0) if p.kind == "pipe" else 0.0
        vs = sorted(valves_by_link.get(lk.id, []), key=lambda s: s.properties.position) if p.kind == "pipe" else []
        cuts = [0.0] + [s.properties.position for s in vs] + [1.0]
        keys = []
        for k in range(len(cuts) - 1):
            key = f"p:{lk.id}:{k}"
            uf.find(key)
            keys.append(key)
            pieces.append((key, lk.id, cuts[k], cuts[k + 1], length * (cuts[k + 1] - cuts[k])))
        for end, key in ((p.from_node, keys[0]), (p.to_node, keys[-1])):
            if end in nodes:
                uf.union("n:" + end, key)
                piece_ends[key].append(end)
        for j, s in enumerate(vs):
            valve_sides[s.id] = (keys[j], keys[j + 1], s.properties.state)

    # Componentes en orden de aparición de los tramos.
    order: list[str] = []
    members: dict[str, dict[str, list]] = {}
    for key, link, a, b, m in pieces:
        root = uf.find(key)
        if root not in members:
            order.append(root)
            members[root] = {"pieces": [], "nodes": []}
        members[root]["pieces"].append((link, a, b, m))
    for n in nodes:
        root = uf.find("n:" + n)
        if root in members:
            members[root]["nodes"].append(n)
    code = {root: f"C-{i + 1:02d}" for i, root in enumerate(order)}
    sector_of_element = {}
    for key, *_ in pieces:
        sector_of_element[key] = code[uf.find(key)]
    for n in nodes:
        r = uf.find("n:" + n)
        if r in code:
            sector_of_element["n:" + n] = code[r]

    boundary: dict[str, list[str]] = defaultdict(list)
    for v, (a, b, _state) in valve_sides.items():
        sa, sb = sector_of_element[a], sector_of_element[b]
        if sa != sb:
            boundary[sa].append(v)
            boundary[sb].append(v)

    clients_by_node: dict[str, list] = defaultdict(list)
    for c in net.clients():
        clients_by_node[c.properties.node].append(c)

    # Grafo de suministro entre elementos (tramos cerrados no conectan; válvulas abiertas unen piezas).
    adj: dict[str, set[str]] = defaultdict(set)
    piece_link = {key: link for key, link, *_ in pieces}
    for key, ends in piece_ends.items():
        if piece_link[key] in closed_links:
            continue
        for n in ends:
            adj[key].add("n:" + n)
            adj["n:" + n].add(key)
    open_valves: dict[str, tuple[str, str]] = {v: (a, b) for v, (a, b, st) in valve_sides.items() if st == "open"}
    sources = ["n:" + n for n, f in nodes.items() if f.properties.kind in ("reservoir", "tank")]

    sectors: list[Sector] = []
    for root in order:
        sid = code[root]
        mem = members[root]
        closed = set(boundary[sid])
        inside = {k for k, s in sector_of_element.items() if s == sid}
        reach: set[str] = set()
        stack = [s for s in sources if s not in inside]
        reach.update(stack)
        valve_adj: dict[str, list[str]] = defaultdict(list)
        for v, (a, b) in open_valves.items():
            if v not in closed:
                valve_adj[a].append(b)
                valve_adj[b].append(a)
        while stack:
            x = stack.pop()
            for y in list(adj[x]) + valve_adj.get(x, []):
                if y not in reach and y not in inside:
                    reach.add(y)
                    stack.append(y)
        down_nodes = sorted(n for n in nodes if "n:" + n not in inside and "n:" + n not in reach
                            and "n:" + n in sector_of_element)
        own_clients = [c for n in mem["nodes"] for c in clients_by_node.get(n, [])]
        down_clients = [c for n in down_nodes for c in clients_by_node.get(n, [])]
        all_c = own_clients + down_clients
        consumption = sum(c.properties.consumption_lps for c in all_c if c.properties.status == "activo")
        links_in = list(dict.fromkeys(p[0] for p in mem["pieces"]))
        sectors.append(Sector(
            id=sid, valves=sorted(set(closed)), links=links_in,
            pieces=[SectorPiece(link=link, start=round(a, 6), end=round(b, 6)) for link, a, b, _m in mem["pieces"]],
            length_m=round(sum(p[3] for p in mem["pieces"]), 2), nodes=mem["nodes"],
            clients=[c.id for c in own_clients], downstream_nodes=down_nodes,
            downstream_clients=[c.id for c in down_clients], affected_clients=len(all_c),
            affected_consumption_lps=round(consumption, 6),
            has_source=any(nodes[n].properties.kind in ("reservoir", "tank") for n in mem["nodes"]),
        ))
    notes = []
    if inoperative:
        notes.append(f"Válvulas inoperativas ignoradas: {', '.join(inoperative)}.")
    if not valve_sides:
        notes.append("La red no tiene válvulas de corte operativas: toda la red es un solo cuartel.")
    return SectorsResult(project_id=project_id, model_version=version, sectors=sectors,
                         inoperative_valves=inoperative, notes=notes)


def sector_of_client(result: SectorsResult) -> dict[str, str]:
    return {c: s.id for s in result.sectors for c in s.clients}


def sector_of_node(result: SectorsResult) -> dict[str, str]:
    return {n: s.id for s in result.sectors for n in s.nodes}


def sectors_of_link(result: SectorsResult) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for s in result.sectors:
        for lk in s.links:
            if s.id not in out[lk]:
                out[lk].append(s.id)
    return out
