import { describe, expect, it } from "vitest";
import type { SimulationResult } from "../api/types";
import { massCurve, niceTicks, seriesCsv, shortestRoute } from "./charts";
import type { Network } from "./network";
import { EMPTY, applyUpgrade } from "./network";
import { CURVA_MOD, CURVA_MOD_NORMALIZADA, formatPatterns, mean, meanWarning, normalize, parsePatterns } from "./patterns";

const n = (uid: string, kind: "junction" | "tank" = "junction") => ({ uid, id: uid.toUpperCase(), kind, pos: [0, 0] as [number, number], props: {} as never });
const l = (uid: string, from: string, to: string, len: number, kind: "pipe" | "pump" = "pipe") =>
  ({ uid, id: uid.toUpperCase(), kind, from, to, vertices: [], props: { length_hydraulic_m: len, dn: 63, inner_diameter_mm: 57 } as never });

describe("patrones", () => {
  it("CurvaMod tiene promedio 0,956 y normalizada promedia 1", () => {
    expect(mean(CURVA_MOD)).toBeCloseTo(0.95625, 5);
    expect(mean(CURVA_MOD_NORMALIZADA)).toBeCloseTo(1, 3);
    expect(meanWarning(CURVA_MOD)).toContain("0,956");
    expect(meanWarning(normalize(CURVA_MOD))).toBeNull();
  });
  it("lee y escribe [PATTERNS] en varias líneas", () => {
    const text = formatPatterns({ MOD: CURVA_MOD, B: [1, 0] });
    const back = parsePatterns(text + "\n; comentario");
    expect(back.MOD).toEqual(CURVA_MOD);
    expect(back.B).toEqual([1, 0]);
  });
});

describe("gráficos", () => {
  const net: Network = {
    ...EMPTY,
    nodes: { a: n("a"), b: n("b"), c: n("c"), d: n("d") },
    links: { p1: l("p1", "a", "b", 100), p2: l("p2", "b", "d", 100), p3: l("p3", "a", "c", 50), p4: l("p4", "c", "d", 300) },
  };
  it("ruta más corta entre dos nudos", () => {
    const r = shortestRoute(net, "a", "d")!;
    expect(r.nodes).toEqual(["a", "b", "d"]);
    expect(r.links).toEqual(["p1", "p2"]);
    expect(r.dist).toEqual([0, 100, 200]);
  });
  it("curva de masas y volumen de regulación", () => {
    const pumpNet: Network = { ...EMPTY, nodes: { j: n("j"), e: n("e", "tank") }, links: { b: l("b", "e", "j", 1, "pump") } };
    const res = { times: [0, 3600, 7200], nodes: { J: { demand: [10, 0, 0], pressure: [], head: [] } },
      links: { B: { flow: [0, 10, 0], velocity: [], headloss: [], status: [] } } } as unknown as SimulationResult;
    const m = massCurve(pumpNet, res);
    expect(m.consumption).toEqual([0, 36, 36]);
    expect(m.pumping).toEqual([0, 0, 36]);
    expect(m.regulation).toBeCloseTo(36);
  });
  it("marcas de eje y CSV con coma decimal", () => {
    expect(niceTicks(0, 3.5)).toEqual([0, 1, 2, 3]);
    expect(seriesCsv("Hora", ["0:00"], [{ name: "Nivel", values: [2.5] }])).toContain('"0:00";2,5');
  });
  it("aplica la mejora de DN sugerida con el catálogo", () => {
    const cat = [{ id: 7, material: "PVC", pipe_class: "C10", dn: 90, inner_diameter_mm: 81.4 }];
    const r = applyUpgrade(net, { link: "P2", material: "PVC", pipe_class: "C10", dn_to: 90 }, cat, "p4");
    expect(r.changed.sort()).toEqual(["P2", "P4"]);
    expect(r.net.links.p2.props.dn).toBe(90);
    expect(r.net.links.p2.props.inner_diameter_mm).toBe(81.4);
    expect(r.net.links.p2.props.catalog_pipe_id).toBe(7);
  });
});
