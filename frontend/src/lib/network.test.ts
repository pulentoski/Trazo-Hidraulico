import { describe, expect, it } from "vitest";
import { defaultNodeProps, tankStorage } from "./network";

describe("nudos nuevos", () => {
  it("no reciben una cota supuesta", () => {
    for (const kind of ["junction", "reservoir", "tank"] as const) {
      const p = defaultNodeProps(kind);
      expect(p.elevation).toBeNull();
      expect(p.elevation_source).toBe("manual");
    }
    expect(defaultNodeProps("reservoir").head).toBeNull();
  });
});

describe("panel de estanque", () => {
  const e1 = { elevation: 50, max_level: 4, min_level: 0.5, tank_diameter: 5, min_volume: 0, volume_curve: null };

  it("calcula la cota de rebalse y el volumen almacenado", () => {
    const t = tankStorage(e1, 3);
    expect(t.overflowElevation).toBe(54);
    expect(t.volume).toBeCloseTo((Math.PI / 4) * 25 * 3, 6); // 58,9 m³
  });

  it("respeta el volumen mínimo indicado (como EPANET)", () => {
    expect(tankStorage({ ...e1, min_volume: 20 }, 3).volume).toBeCloseTo(20 + (Math.PI / 4) * 25 * 2.5, 6);
  });

  it("sin datos suficientes no inventa valores", () => {
    expect(tankStorage({ ...e1, elevation: null }, 3).overflowElevation).toBeNull();
    expect(tankStorage(e1, undefined).volume).toBeNull();
    expect(tankStorage({ ...e1, volume_curve: "C1" }, 3).volume).toBeNull();
  });
});
