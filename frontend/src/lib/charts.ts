// Datos para gráficos: rutas entre nudos, curva de masas, escalas y CSV.
import type { SimulationResult } from "../api/types";
import { haversine } from "./geo";
import type { Network } from "./network";
import { linkCoords } from "./network";

export interface Series { name: string; values: (number | null)[]; color?: string; dashed?: boolean }

/** Ruta más corta (por largo) entre dos nudos (uids); devuelve los uids de nudos y tramos en orden. */
export function shortestRoute(net: Network, from: string, to: string): { nodes: string[]; links: string[]; dist: number[] } | null {
  const adj = new Map<string, { to: string; link: string; w: number }[]>();
  for (const l of Object.values(net.links)) {
    if (!net.nodes[l.from] || !net.nodes[l.to]) continue;
    const w = l.props.length_hydraulic_m ?? l.props.length_plan_m ?? haversine(net.nodes[l.from].pos, net.nodes[l.to].pos);
    (adj.get(l.from) ?? adj.set(l.from, []).get(l.from)!).push({ to: l.to, link: l.uid, w });
    (adj.get(l.to) ?? adj.set(l.to, []).get(l.to)!).push({ to: l.from, link: l.uid, w });
  }
  const dist = new Map<string, number>([[from, 0]]);
  const prev = new Map<string, { node: string; link: string }>();
  const done = new Set<string>();
  while (true) {
    let u: string | null = null;
    for (const [k, d] of dist) if (!done.has(k) && (u === null || d < dist.get(u)!)) u = k;
    if (u === null) return null;
    if (u === to) break;
    done.add(u);
    for (const e of adj.get(u) ?? []) {
      const nd = dist.get(u)! + e.w;
      if (nd < (dist.get(e.to) ?? Infinity)) { dist.set(e.to, nd); prev.set(e.to, { node: u, link: e.link }); }
    }
  }
  const nodes = [to];
  const links: string[] = [];
  while (nodes[0] !== from) {
    const p = prev.get(nodes[0])!;
    links.unshift(p.link);
    nodes.unshift(p.node);
  }
  return { nodes, links, dist: nodes.map((n) => dist.get(n)!) };
}

/** Consumo y bombeo acumulados (m³) por periodo: curva de masas. Bombeo = caudal de bombas (y de válvulas FCV
 * si no hay bombas); consumo = demanda de los nudos de consumo. */
export function massCurve(net: Network, res: SimulationResult): { consumption: number[]; pumping: number[]; regulation: number } {
  const times = res.times;
  const junctions = Object.values(net.nodes).filter((n) => n.kind === "junction").map((n) => n.id);
  let sources = Object.values(net.links).filter((l) => l.kind === "pump").map((l) => l.id);
  if (!sources.length) sources = Object.values(net.links).filter((l) => l.kind === "valve" && l.props.valve_type === "FCV").map((l) => l.id);
  const c: number[] = [0];
  const p: number[] = [0];
  for (let k = 0; k < times.length - 1; k++) {
    const dt = times[k + 1] - times[k];
    const dem = junctions.reduce((s, id) => s + Math.max(0, res.nodes[id]?.demand[k] ?? 0), 0);
    const pump = sources.reduce((s, id) => s + Math.max(0, res.links[id]?.flow[k] ?? 0), 0);
    c.push(c[k] + (dem * dt) / 1000);
    p.push(p[k] + (pump * dt) / 1000);
  }
  const diff = p.map((v, i) => v - c[i]);
  return { consumption: c, pumping: p, regulation: Math.max(...diff) - Math.min(...diff) };
}

/** Marcas «bonitas» para un eje (1, 2, 5 × 10ⁿ). */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) { min -= 1; max += 1; }
  const raw = (max - min) / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? pow * 10;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}

export function seriesCsv(xLabel: string, x: (number | string)[], series: Series[]): string {
  const esc = (v: unknown) => (v === null || v === undefined ? "" : typeof v === "number" ? String(v).replace(".", ",") : `"${String(v).replace(/"/g, '""')}"`);
  const lines = [[xLabel, ...series.map((s) => s.name)].map(esc).join(";")];
  x.forEach((xv, i) => lines.push([xv, ...series.map((s) => s.values[i])].map(esc).join(";")));
  return "﻿" + lines.join("\r\n") + "\r\n";
}

export function routeLengthM(net: Network, links: string[]): number {
  return links.reduce((s, u) => s + (net.links[u]?.props.length_hydraulic_m ?? 0), 0) || links.reduce((s, u) => {
    const l = net.links[u];
    if (!l) return s;
    const c = linkCoords(net, l);
    let d = 0;
    for (let i = 1; i < c.length; i++) d += haversine(c[i - 1], c[i]);
    return s + d;
  }, 0);
}
