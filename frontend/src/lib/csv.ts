// Exportación CSV (separador «;» y coma decimal: abre directo en Excel con configuración regional de Chile).
import type { CompareResult, ScenarioResult } from "../api/types";

export interface Column<T> { header: string; value: (row: T) => string | number | null | undefined }

function cell(v: string | number | null | undefined): string {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "";
  const s = typeof v === "number" ? String(Math.round(v * 1e6) / 1e6).replace(".", ",") : v;
  return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv<T>(rows: T[], columns: Column<T>[]): string {
  const lines = [columns.map((c) => cell(c.header)).join(";")];
  for (const r of rows) lines.push(columns.map((c) => cell(c.value(r))).join(";"));
  return "﻿" + lines.join("\r\n") + "\r\n";
}

type ClientState = ScenarioResult["clients"][number];

/** Clientes afectados de un escenario (sin suministro o bajo la presión mínima). */
export function affectedCsv(r: ScenarioResult): string {
  return toCsv<ClientState>(r.clients.filter((c) => c.affected), [
    { header: "Escenario", value: () => r.scenario_name },
    { header: "Cliente", value: (c) => c.id }, { header: "Nombre", value: (c) => c.name },
    { header: "Nudo", value: (c) => c.node }, { header: "Estado", value: (c) => c.status },
    { header: "Consumo (L/s)", value: (c) => c.consumption_lps },
    { header: "Suministro", value: (c) => (c.supplied ? "sí" : "no") },
    { header: "Presión (m)", value: (c) => c.pressure },
    { header: `Bajo mínimo (${String(r.pressure_min).replace(".", ",")} m)`, value: (c) => (c.below_min ? "sí" : "no") },
  ]);
}

export function compareCsv(r: CompareResult): string {
  return toCsv(r.rows, [
    { header: "Tipo", value: (x) => x.kind }, { header: "ID", value: (x) => x.id }, { header: "Nombre", value: (x) => x.name },
    { header: `Presión ${r.a.scenario_name} (m)`, value: (x) => x.a }, { header: `Presión ${r.b.scenario_name} (m)`, value: (x) => x.b },
    { header: "Diferencia (m)", value: (x) => x.diff },
    { header: `Suministro ${r.a.scenario_name}`, value: (x) => (x.supplied_a ? "sí" : "no") },
    { header: `Suministro ${r.b.scenario_name}`, value: (x) => (x.supplied_b ? "sí" : "no") },
  ]);
}

export function downloadText(filename: string, text: string, type = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
