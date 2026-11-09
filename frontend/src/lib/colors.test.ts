import { describe, expect, it } from "vitest";
import { DEFAULT_CRITERIA, legendClasses, linkScale, linkValue } from "./colors";

const crit = DEFAULT_CRITERIA;
const legend = (mode: Parameters<typeof linkScale>[0], values: number[]) => legendClasses(linkScale(mode, crit, values), values);
const pipe = (id: string, d = 83) => ({ id, kind: "pipe", props: { inner_diameter_mm: d } });
const res = (q: number, v: number, h: number) => ({ flow: [q], velocity: [v], headloss: [h] });

describe("leyenda de tramos", () => {
  it("usa solo la variable seleccionada y omite tramos sin dato", () => {
    const pump = { id: "B1", kind: "pump", props: { inner_diameter_mm: null } };
    expect(linkValue("headloss", pipe("P1"), res(-10, 1.8, -36.4), 0)).toBeCloseTo(36.4);
    expect(linkValue("flow", pipe("P1"), res(-10, 1.8, -36.4), 0)).toBe(10);
    expect(linkValue("velocity", pipe("P1"), res(-10, 1.8, -36.4), 0)).toBeCloseTo(1.8);
    expect(linkValue("headloss", pump, res(10, 0, -40), 0)).toBeNull(); // bomba: m, no m/km
    expect(linkValue("flow", pipe("P2"), undefined, 0)).toBeNull(); // sin resultados ≠ 0
    expect(linkValue("diameter", pipe("P1", 147.6), undefined, 0)).toBe(147.6);
  });

  it("con un solo valor muestra una sola clase", () => {
    for (const mode of ["flow", "diameter", "headloss", "velocity"] as const) {
      const c = legend(mode, [mode === "diameter" ? 83 : 2]);
      expect(c, mode).toHaveLength(1);
      expect(c[0].count).toBe(1);
    }
    expect(legend("flow", [10])[0].label).toBe("10,00 L/s");
  });

  it("no repite clases ni muestra rangos vacíos", () => {
    const flows = [0, 0, 0, 0, 0.001, 0.002, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    for (const mode of ["flow", "headloss", "velocity"] as const) {
      const c = legend(mode, flows);
      const labels = c.map((x) => x.label);
      expect(new Set(labels).size, mode).toBe(labels.length);
      for (const l of labels) {
        expect(l).not.toMatch(/(\d+,\d+) – \1(?!\d)/); // «0,00 – 0,00»
        expect(l).not.toContain("—");
      }
      expect(c.every((x) => x.count > 0)).toBe(true);
      expect(c.reduce((s, x) => s + x.count, 0)).toBe(flows.length);
    }
  });

  it("valores repetidos o casi iguales no generan clases duplicadas", () => {
    const c = legend("flow", [2, 2, 2.001, 1.999, 5, 5]);
    expect(c.map((x) => x.label)).toEqual(["2,00 L/s", "5,00 L/s"]);
    expect(c.map((x) => x.count)).toEqual([4, 2]);
    const d = legend("diameter", [83, 83, 147.6]);
    expect(d.map((x) => x.label)).toEqual(["83 mm", "148 mm"]);
  });

  it("sin valores no muestra clases", () => {
    expect(legend("flow", [])).toEqual([]);
    expect(legend("headloss", [])).toEqual([]);
  });

  it("la pérdida se ancla al criterio del perfil", () => {
    const c = legend("headloss", [2.2, 36.4]);
    expect(c.map((x) => x.label)).toEqual(["1,0 – 3,0 m/km", "≥ 20,0 m/km"]);
    expect(c[0].lower).toBeLessThan(crit.headlossMax);
    expect(c[1].lower).toBeGreaterThanOrEqual(crit.headlossMax); // «sobre criterio»
  });
});
