import { describe, expect, it } from "vitest";
import type { LabelItem } from "./labels";
import { placeLabels } from "./labels";

const L = (key: string, x: number, y: number, prio: number, text = "J-10"): LabelItem =>
  ({ key, uid: key, x, y, text, cls: "lbl", anchor: "start", prio });

describe("etiquetas sin superposición", () => {
  it("oculta la de menor prioridad cuando chocan", () => {
    const vis = placeLabels([L("tramo", 10, 10, 30), L("nudo", 14, 12, 50), L("lejos", 200, 200, 10)]);
    expect([...vis].sort()).toEqual(["lejos", "nudo"]);
  });
  it("no ubica etiquetas fuera de la vista", () => {
    expect(placeLabels([L("a", -500, 10, 1)], { width: 800, height: 600 }).size).toBe(0);
  });
});
