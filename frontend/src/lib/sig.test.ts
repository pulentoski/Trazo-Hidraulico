import { describe, expect, it } from "vitest";
import type { Network } from "./network";
import { EMPTY } from "./network";
import { cutMessage, joinEs, tileUrl, uidOf, visibleTiles } from "./sig";

describe("sig", () => {
  it("une listas en español", () => {
    expect(joinEs([])).toBe("");
    expect(joinEs(["V3"])).toBe("V3");
    expect(joinEs(["V3", "V7", "V9"])).toBe("V3, V7 y V9");
  });

  it("arma el mensaje de corte", () => {
    expect(cutMessage(["V3", "V7", "V9"], 42)).toBe("Para cortar aquí, cierre V3, V7 y V9; quedan sin agua 42 clientes.");
    expect(cutMessage(["V1"], 1)).toBe("Para cortar aquí, cierre V1; queda sin agua 1 cliente.");
  });

  it("ubica elementos por hoja e ID", () => {
    const net: Network = {
      ...EMPTY,
      nodes: { a: { uid: "a", id: "J-1", kind: "junction", pos: [0, 0], props: {} as never } },
      hydrants: { h: { uid: "h", id: "G-1", pos: [0, 0], node: "a", props: {} as never } },
    };
    expect(uidOf(net, "nudos", "J-1")).toBe("a");
    expect(uidOf(net, "grifos", "G-1")).toBe("h");
    expect(uidOf(net, "tramos", "J-1")).toBeNull();
  });

  it("calcula teselas visibles y respeta los límites de la ortofoto", () => {
    const cam = { center: [-71.25, -29.9] as [number, number], zoom: 16 };
    const all = visibleTiles(cam, { width: 512, height: 512 });
    expect(all.length).toBeGreaterThanOrEqual(4);
    expect(all.every((t) => t.z === 16 && t.size === 256)).toBe(true);
    const clipped = visibleTiles(cam, { width: 512, height: 512 }, [-71.2501, -29.9001, -71.2499, -29.8999]);
    expect(clipped.length).toBeLessThanOrEqual(4);
    expect(clipped.length).toBeGreaterThan(0);
    expect(tileUrl("/tiles/x/{z}/{x}/{y}.png", { z: 1, x: 2, y: 3, left: 0, top: 0, size: 256 })).toBe("/tiles/x/1/2/3.png");
  });
});
