import { describe, expect, it } from "vitest";
import { compareCells, filterRows, paginate, sortRows, toNumber, toTime } from "./table";

describe("tabla común: orden", () => {
  it("texto A–Z sin distinguir tildes ni mayúsculas, con números naturales", () => {
    const r = sortRows(["N-10", "n-2", "Ñandú", "Árbol", "zeta", "N-1"], (x) => x, "text", 1);
    expect(r).toEqual(["Árbol", "N-1", "n-2", "N-10", "Ñandú", "zeta"]);
  });
  it("números con orden numérico real (no lexicográfico), también en texto es-CL", () => {
    expect(sortRows([10, 9, 100, -1, 2.5], (x) => x, "num", 1)).toEqual([-1, 2.5, 9, 10, 100]);
    expect(sortRows(["1.234,5", "99,9", "1.000", "5"], (x) => x, "num", -1)).toEqual(["1.234,5", "1.000", "99,9", "5"]);
    expect(toNumber("12,5 L/s")).toBe(12.5);
    expect(toNumber("—")).toBeNull();
  });
  it("vacíos al final en ambos sentidos", () => {
    expect(sortRows([3, null, 1, Number.NaN, 2], (x) => x, "num", 1)).toEqual([1, 2, 3, null, Number.NaN]);
    expect(sortRows([3, null, 1, 2], (x) => x, "num", -1)).toEqual([3, 2, 1, null]);
  });
  it("fechas ISO y dd-mm-aaaa", () => {
    expect(sortRows(["2026-03-01", "2025-12-31", "2026-01-15T10:00:00Z"], (x) => x, "date", 1))
      .toEqual(["2025-12-31", "2026-01-15T10:00:00Z", "2026-03-01"]);
    expect(toTime("17-11-26, 15:08")).toBe(new Date(2026, 10, 17, 15, 8).getTime());
    expect(compareCells("01/02/2026", "31/01/2026", "date")).toBeGreaterThan(0);
  });
  it("orden estable ante empates", () => {
    const rows = [{ k: 1, n: "a" }, { k: 0, n: "b" }, { k: 1, n: "c" }];
    expect(sortRows(rows, (r) => r.k, "num", 1).map((r) => r.n)).toEqual(["b", "a", "c"]);
  });
});

describe("tabla común: búsqueda y páginas", () => {
  it("busca todas las palabras, sin tildes", () => {
    const rows = [{ t: "Válvula reguladora sector norte" }, { t: "Estanque elevado" }, { t: "valvula de corte" }];
    expect(filterRows(rows, "VALVULA norte", (r) => [r.t]).length).toBe(1);
    expect(filterRows(rows, "válvula", (r) => [r.t]).length).toBe(2);
    expect(filterRows(rows, "  ", (r) => [r.t]).length).toBe(3);
  });
  it("pagina y acota la página", () => {
    const rows = Array.from({ length: 53 }, (_, i) => i);
    expect(paginate(rows, 0, 25).pages).toBe(3);
    expect(paginate(rows, 2, 25).rows).toEqual([50, 51, 52]);
    expect(paginate(rows, 9, 25).page).toBe(2);
    expect(paginate(rows, 0, 0).rows.length).toBe(53);
  });
});
