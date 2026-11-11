import { describe, expect, it } from "vitest";
import { EMPTY } from "./network";
import { clp, hourLabel, pointsOf, polygonsOf, uidMaps, uidsOf, zoneColor } from "./summary";

describe("resumen: utilidades", () => {
  it("convierte Polygon y MultiPolygon en anillos", () => {
    const ring = [[0, 0], [1, 0], [1, 1], [0, 0]];
    expect(polygonsOf({ type: "Polygon", coordinates: [ring] })).toEqual([[ring]]);
    expect(polygonsOf({ type: "MultiPolygon", coordinates: [[ring], [ring]] })).toHaveLength(2);
    expect(polygonsOf(null)).toEqual([]);
  });
  it("enlaza IDs visibles con uids y encuadra los elementos", () => {
    const net = { ...EMPTY, nodes: { u1: { uid: "u1", id: "J-1", kind: "junction", pos: [-71, -30], props: {} } } } as never;
    const maps = uidMaps(net);
    expect(uidsOf(maps, "node", ["J-1", "X"])).toEqual(["u1"]);
    expect(pointsOf(net, ["u1"])).toEqual([[-71, -30]]);
  });
  it("formatea hora, pesos y colores de rango", () => {
    expect(hourLabel(8 * 3600 + 30 * 60)).toBe("8:30");
    expect(clp(1234567.4)).toMatch(/^\$1\.234\.567$/);
    expect(zoneColor(0)).toBe("#d7301f");
    expect(zoneColor(99)).toBe("#555555");
  });
});
