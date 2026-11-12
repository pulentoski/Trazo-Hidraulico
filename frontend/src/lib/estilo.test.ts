import { describe, expect, it } from "vitest";
import { placeText } from "./format";
import { EMPTY } from "./network";
import type { Network } from "./network";
import { bornUids } from "../state/store";

describe("inicio: ubicación de la tarjeta", () => {
  it("formatea el centro en grados con hemisferio", () => {
    expect(placeText([-71.1413, -29.9399])).toMatch(/^29,94° S · 71,14° O$/);
    expect(placeText([2.35, 48.86])).toMatch(/N · 2,35° E$/);
    expect(placeText(null)).toBe("Sin ubicación");
  });
});

describe("mapa: elementos recién creados", () => {
  it("detecta solo los uid nuevos", () => {
    const a = { ...EMPTY, nodes: { n1: {} } } as unknown as Network;
    const b = { ...a, nodes: { n1: {}, n2: {} }, links: { l1: {} } } as unknown as Network;
    expect(bornUids(a, b).sort()).toEqual(["l1", "n2"]);
    expect(bornUids(b, b)).toEqual([]);
    expect(bornUids(b, a)).toEqual([]);  // borrar no es «nacer»
  });
});
