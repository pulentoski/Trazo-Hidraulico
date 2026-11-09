import { describe, expect, it } from "vitest";
import type { ENode, ELink, Network } from "./network";
import { EMPTY, nearestJunction, nearestPipe, nodeDemand, pointAlong, splitPipe, toLps, toFeatureCollection, fromDocument,
  defaultNodeProps, defaultPipeProps } from "./network";
import { removeElements } from "../state/store";

const LON0 = -70.65, LAT0 = -33.45, D100 = 0.0010783; // ≈ 100 m
const node = (uid: string, kind: ENode["kind"], k: number, elevation: number | null = 30): ENode =>
  ({ uid, id: uid.toUpperCase(), kind, pos: [LON0 + D100 * k, LAT0], props: { ...defaultNodeProps(kind), elevation } });
const pipe = (uid: string, from: string, to: string, len?: number): ELink =>
  ({ uid, id: uid.toUpperCase(), kind: "pipe", from, to, vertices: [],
    props: defaultPipeProps(len ? { length_choice: "manual", length_hydraulic_m: len, inner_diameter_mm: 100, roughness: 150 } : {}) });

function net(): Network {
  return { ...EMPTY,
    nodes: { e1: node("e1", "tank", 0, 50), j1: node("j1", "junction", 3, 30), j2: node("j2", "junction", 4, 34) },
    links: { p1: pipe("p1", "e1", "j1", 300), p2: pipe("p2", "j1", "j2") },
    clients: {}, shutoffs: { ll1: { uid: "ll1", id: "LL1", link: "p2", position: 0.8, props: { name: null, state: "closed" } } },
  };
}

describe("conexión de clientes a la red", () => {
  it("proyecta sobre la tubería más cercana y asigna el nudo de consumo más cercano", () => {
    const n = net();
    const pr = nearestPipe(n, [LON0 + D100 * 3.25, LAT0 + 0.00005])!;
    expect(pr.link).toBe("p2");
    expect(pr.fraction).toBeCloseTo(0.25, 2);
    expect(pr.distanceM).toBeCloseTo(5.5, 0);
    expect(nearestJunction(n, pr)).toMatchObject({ node: "j1" });
    // Sobre P1 cerca del estanque: E1 es fuente, se asigna el extremo de consumo (J1).
    const pr2 = nearestPipe(n, [LON0 + D100 * 0.2, LAT0 + 0.0001])!;
    expect(pr2.link).toBe("p1");
    expect(nearestJunction(n, pr2)!.node).toBe("j1");
  });

  it("divide la tubería con un nudo nuevo, reparte el largo manual y mueve las llaves", () => {
    const n = net();
    const pr = nearestPipe(n, [LON0 + D100 * 1.5, LAT0])!;
    const { net: out, node: nu, second } = splitPipe(n, pr, "J9", 41);
    expect(out.nodes[nu]).toMatchObject({ id: "J9", kind: "junction", props: { elevation: 41 } });
    expect(out.links.p1.to).toBe(nu);
    expect(out.links[second]).toMatchObject({ from: nu, to: "j1", id: "P3" });
    expect(out.links.p1.props.length_hydraulic_m! + out.links[second].props.length_hydraulic_m!).toBeCloseTo(300, 6);
    expect(out.links.p1.props.length_hydraulic_m).toBeCloseTo(150, 0);
    // La llave en el 80 % de P2 pasa al segundo tramo si se divide P2 en el 50 %.
    const pr3 = nearestPipe(n, [LON0 + D100 * 3.5, LAT0])!;
    const r3 = splitPipe(n, pr3, "J10", null);
    expect(r3.net.shutoffs.ll1.link).toBe(r3.second);
    expect(r3.net.shutoffs.ll1.position).toBeCloseTo(0.6, 2);
    expect(r3.net.nodes[r3.node].props.elevation).toBeNull(); // la cota no se supone
  });

  it("la demanda del nudo es manual + clientes, con m³/mes convertido a L/s", () => {
    const n = net();
    n.nodes.j1.props.base_demand = 0.5;
    n.clients = {
      c1: { uid: "c1", id: "C1", pos: [0, 0], node: "j1", link: "p2", connection: null,
        props: { name: "A", client_type: "residencial", status: "activo", consumption_value: 2592, consumption_unit: "m3/mes", connection_mode: "nearest", elevation: null } },
      c2: { uid: "c2", id: "C2", pos: [0, 0], node: "j1", link: "p2", connection: null,
        props: { name: "B", client_type: "comercial", status: "proyectado", consumption_value: 2, consumption_unit: "L/s", connection_mode: "nearest", elevation: null } },
    };
    expect(toLps(2592, "m3/mes")).toBeCloseTo(1, 9);
    expect(nodeDemand(n, "j1", false)).toMatchObject({ manual: 0.5, total: 1.5 });
    expect(nodeDemand(n, "j1", true).total).toBeCloseTo(3.5, 9);
  });

  it("eliminar un nudo elimina sus clientes, y eliminar una tubería sus llaves", () => {
    const n = net();
    n.clients = { c1: { uid: "c1", id: "C1", pos: [0, 0], node: "j2", link: null, connection: null,
      props: { name: null, client_type: "residencial", status: "activo", consumption_value: 1, consumption_unit: "L/s", connection_mode: "nearest", elevation: null } } };
    const out = removeElements(n, ["j2"]);
    expect(out.clients).toEqual({});
    expect(out.shutoffs).toEqual({}); // P2 cae con J2 y con ella su llave
    expect(Object.keys(out.links)).toEqual(["p1"]);
  });

  it("ida y vuelta GeoJSON conserva clientes y llaves", () => {
    const n = net();
    n.clients = { c1: { uid: "c1", id: "C1", pos: [LON0, LAT0], node: "j1", link: "p2", connection: [LON0 + D100 * 3, LAT0],
      props: { name: "A", client_type: "industrial", status: "activo", consumption_value: 1, consumption_unit: "L/s", connection_mode: "nearest", elevation: 29 } } };
    const fc = toFeatureCollection(n);
    const ll = fc.features.find((f) => f.id === "LL1")!;
    const p = pointAlong([n.nodes.j1.pos, n.nodes.j2.pos], 0.8);
    expect(ll.geometry.coordinates[0]).toBeCloseTo(p[0], 9);
    const back = fromDocument({ network: fc } as never);
    const c = Object.values(back.clients)[0];
    expect(back.nodes[c.node].id).toBe("J1");
    expect(back.links[c.link!].id).toBe("P2");
    expect(c.props.client_type).toBe("industrial");
    expect(Object.values(back.shutoffs)[0]).toMatchObject({ id: "LL1", position: 0.8, props: { state: "closed" } });
  });
});
