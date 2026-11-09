import { describe, expect, it } from "vitest";
import type { ScenarioResult } from "../api/types";
import { affectedCsv, toCsv } from "./csv";

describe("CSV", () => {
  it("usa «;», coma decimal, BOM y escapa comillas y separadores", () => {
    const csv = toCsv([{ a: 'Casa "A"; norte', b: 1.5, c: null }], [
      { header: "Nombre", value: (r) => r.a }, { header: "Valor", value: (r) => r.b }, { header: "Vacío", value: (r) => r.c }]);
    expect(csv.startsWith("﻿")).toBe(true);
    expect(csv).toBe('﻿Nombre;Valor;Vacío\r\n"Casa ""A""; norte";1,5;\r\n');
  });

  it("exporta solo los clientes afectados del escenario", () => {
    const r = {
      scenario_name: "Corte sector norte", pressure_min: 15,
      clients: [
        { id: "C1", name: "Escuela", node: "J1", status: "activo", consumption_lps: 2, supplied: true, pressure: 30.2, below_min: false, affected: false },
        { id: "C2", name: "Almacén", node: "J2", status: "activo", consumption_lps: 1, supplied: false, pressure: null, below_min: false, affected: true },
        { id: "C3", name: null, node: "J3", status: "activo", consumption_lps: 0.5, supplied: true, pressure: 12.25, below_min: true, affected: true },
      ],
    } as unknown as ScenarioResult;
    const lines = affectedCsv(r).replace("﻿", "").trim().split("\r\n");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain("Bajo mínimo (15 m)");
    expect(lines[1]).toBe("Corte sector norte;C2;Almacén;J2;activo;1;no;;no");
    expect(lines[2]).toBe("Corte sector norte;C3;;J3;activo;0,5;sí;12,25;sí");
  });
});
