import { describe, expect, it } from "vitest";
import { metersPerPixel, scaleBar } from "./geo";

describe("escala gráfica", () => {
  it("usa la resolución Web Mercator en la latitud del centro", () => {
    expect(metersPerPixel({ center: [0, 0], zoom: 0 })).toBeCloseTo(156543.034, 2);
    // A −33,45° la resolución es cos(lat) veces la del ecuador.
    const santiago = metersPerPixel({ center: [-70.65, -33.45], zoom: 16 });
    expect(santiago).toBeCloseTo((156543.034 / 2 ** 16) * Math.cos((33.45 * Math.PI) / 180), 6);
  });

  it("elige un largo redondo que cabe en el ancho máximo y su ancho en píxeles es coherente", () => {
    for (let zoom = 3; zoom <= 21; zoom++) {
      const cam = { center: [-70.65, -33.45] as [number, number], zoom };
      const s = scaleBar(cam, 120);
      expect(s.px).toBeLessThanOrEqual(120 + 1e-9);
      expect(s.px).toBeGreaterThan(120 / 5 - 1e-9);
      expect(String(s.meters / 10 ** Math.floor(Math.log10(s.meters)))).toMatch(/^(1|2|5)$/);
      expect(s.px * metersPerPixel(cam)).toBeCloseTo(s.meters, 6);
    }
  });

  it("rotula en metros o kilómetros", () => {
    expect(scaleBar({ center: [-70.65, -33.45], zoom: 18 }).label).toMatch(/^\d+ m$/);
    expect(scaleBar({ center: [-70.65, -33.45], zoom: 8 }).label).toMatch(/ km$/);
  });
});
