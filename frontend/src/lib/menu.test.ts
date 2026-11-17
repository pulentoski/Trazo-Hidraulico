import { describe, expect, it } from "vitest";
import { placeMenu } from "../components/MenuButton";

const vp = { width: 1024, height: 700 };
describe("menú desplegable: no se corta en los bordes", () => {
  it("abre hacia abajo si cabe", () => {
    const p = placeMenu({ trigger: { left: 100, right: 180, top: 40, bottom: 74 }, menu: { width: 300, height: 400 }, viewport: vp });
    expect(p.up).toBe(false);
    expect(p.top).toBe(78);
    expect(p.left).toBe(100);
  });
  it("se corre a la izquierda si se saldría por la derecha", () => {
    const p = placeMenu({ trigger: { left: 900, right: 980, top: 40, bottom: 74 }, menu: { width: 300, height: 200 }, viewport: vp });
    expect(p.left + 300).toBeLessThanOrEqual(1024 - 8);
  });
  it("abre hacia arriba cerca del borde inferior y limita el alto", () => {
    const p = placeMenu({ trigger: { left: 10, right: 90, top: 640, bottom: 670 }, menu: { width: 200, height: 900 }, viewport: vp });
    expect(p.up).toBe(true);
    expect(p.top).toBeGreaterThanOrEqual(8);
    expect(p.maxHeight).toBeLessThanOrEqual(640);
  });
  it("alineado a la derecha del botón", () => {
    const p = placeMenu({ trigger: { left: 500, right: 600, top: 10, bottom: 40 }, menu: { width: 250, height: 100 }, viewport: vp, align: "right" });
    expect(p.left).toBe(350);
  });
});
