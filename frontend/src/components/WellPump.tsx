// Pozo y bombeo: datos de diseño (columna, impulsión, rendimientos) y cálculo de altura, potencia y corriente.
import { useState } from "react";
import { api } from "../api/client";
import type { CatalogPipe, PumpCalc, PumpLine, WellPumpDesign } from "../api/types";
import { fmt } from "../lib/format";
import type { EWell } from "../lib/network";
import { flushPending } from "../state/live";
import { errorText, openProject } from "../state/projects";
import { useEditor } from "../state/store";
import { Help, NumField } from "./Fields";
import { Section } from "./Section";

export const DEFAULT_DESIGN: WellPumpDesign = {
  pump_depth_m: 40, design_flow_lps: 8, minor_loss_pct: 5, pump_efficiency: 0.75, motor_efficiency: 0.9,
  power_factor: 0.85, voltage_v: 380, arrival_elevation_m: null, arrival_tank: null,
  column: { material: null, dn: null, pipe_class: null, inner_diameter_mm: 100, length_m: 40, roughness: null },
  impulsion: { material: null, dn: null, pipe_class: null, inner_diameter_mm: 100, length_m: 100, roughness: null },
};

function LineEditor({ title, line, catalog, onChange }: { title: string; line: PumpLine; catalog: CatalogPipe[]; onChange: (l: PumpLine) => void }) {
  const key = line.material && line.dn ? `${line.material}|${line.pipe_class ?? ""}|${line.dn}` : "";
  return (
    <Section id={`pozo.${title.toLowerCase()}`} title={title}>
      <label className="field"><span>Tubería (catálogo)</span>
        <select value={key} onChange={(e) => {
          const c = catalog.find((x) => `${x.material}|${x.pipe_class}|${x.dn}` === e.target.value);
          if (c) onChange({ ...line, material: c.material, pipe_class: c.pipe_class, dn: c.dn, inner_diameter_mm: c.inner_diameter_mm, roughness: c.hw_c });
          else onChange({ ...line, material: null, pipe_class: null, dn: null });
        }}>
          <option value="">— manual</option>
          {catalog.map((c) => <option key={c.id} value={`${c.material}|${c.pipe_class}|${c.dn}`}>{c.material} {c.pipe_class} DN {c.dn}</option>)}
        </select></label>
      <div className="grid2">
        <NumField label="D interior" unit="mm" digits={1} value={line.inner_diameter_mm} onCommit={(v) => v && onChange({ ...line, inner_diameter_mm: v })} />
        <NumField label="Largo" unit="m" digits={1} value={line.length_m} onCommit={(v) => v !== null && onChange({ ...line, length_m: v })} />
      </div>
    </Section>
  );
}

export function WellPump({ w }: { w: EWell }) {
  const { project, catalog, net, revision, savedRevision, toast } = useEditor();
  const [calc, setCalc] = useState<PumpCalc | null>(null);
  const [busy, setBusy] = useState(false);
  const d = w.props.pump_design ?? null;
  const set = (patch: Partial<WellPumpDesign> | null) => useEditor.getState().commit((n) => {
    const cur = n.wells[w.uid];
    const next = patch === null ? null : { ...(cur.props.pump_design ?? DEFAULT_DESIGN), ...patch };
    return { ...n, wells: { ...n.wells, [w.uid]: { ...cur, props: { ...cur.props, pump_design: next } } } };
  });
  const tanks = Object.values(net.nodes).filter((x) => x.kind === "tank");
  const dirty = revision !== savedRevision;
  const run = async () => {
    if (!project) return;
    setBusy(true);
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios.");
      setCalc(await api.pumpCalc(project.id, w.id));
    } catch (e) { toast(errorText(e), "error"); } finally { setBusy(false); }
  };
  const applyCurve = async () => {
    if (!project) return;
    try {
      if (!(await flushPending())) throw new Error("No se pudieron guardar los cambios.");
      const r = await api.applyWellCurve(project.id, w.id);
      await openProject(project.id);
      toast(`Curva de 3 puntos aplicada a la bomba ${r.pump} y cota del nivel dinámico al reservorio (versión ${r.version}).`);
    } catch (e) { toast(errorText(e), "error"); }
  };
  if (!d) return <button className="small" onClick={() => set({})}>+ Datos de bombeo del pozo</button>;
  return (
    <>
      <Section id="pozo.bombeo" title="Bombeo" primary extra={<Help text="Datos de la hoja BombaPozo1: profundidad de la bomba, caudal de diseño, columna e impulsión, cota de llegada y rendimientos. Cálculo con γ = 9.810 N/m³, π exacto y la fórmula de pérdidas del proyecto." />}>
        <div className="grid2">
          <NumField label="Profundidad de la bomba" unit="m" value={d.pump_depth_m} onCommit={(v) => v !== null && set({ pump_depth_m: v })} />
          <NumField label="Caudal de diseño" unit="L/s" value={d.design_flow_lps} onCommit={(v) => v && set({ design_flow_lps: v })} />
        </div>
        <label className="field"><span>Llegada</span>
          <select value={d.arrival_tank ?? ""} onChange={(e) => set({ arrival_tank: e.target.value || null })}>
            <option value="">Cota indicada</option>{tanks.map((t) => <option key={t.uid} value={t.id}>Estanque {t.id} (rebalse)</option>)}
          </select></label>
        {!d.arrival_tank && <NumField label="Cota de llegada" unit="m" value={d.arrival_elevation_m} allowNull onCommit={(v) => set({ arrival_elevation_m: v })} />}
        <div className="grid2">
          <NumField label="Pérdidas singulares" unit="%" value={d.minor_loss_pct} onCommit={(v) => v !== null && set({ minor_loss_pct: v })} />
          <NumField label="Rend. bomba" value={d.pump_efficiency} onCommit={(v) => v && set({ pump_efficiency: Math.min(1, v) })} />
          <NumField label="Rend. motor" value={d.motor_efficiency} onCommit={(v) => v && set({ motor_efficiency: Math.min(1, v) })} />
          <NumField label="Factor de potencia" value={d.power_factor} onCommit={(v) => v && set({ power_factor: Math.min(1, v) })} />
          <NumField label="Tensión trifásica" unit="V" digits={0} value={d.voltage_v} onCommit={(v) => v && set({ voltage_v: v })} />
        </div>
      </Section>
      <LineEditor title="Columna" line={d.column} catalog={catalog} onChange={(l) => set({ column: l })} />
      <LineEditor title="Impulsión" line={d.impulsion} catalog={catalog} onChange={(l) => set({ impulsion: l })} />
      <div className="toolbar">
        <button className="small primary" disabled={busy} onClick={() => void run()}>{busy ? "Calculando…" : dirty ? "Guardar y calcular" : "Calcular"}</button>
        {project && <a className="btn small" href={api.wellReportUrl(project.id, w.id)} target="_blank" rel="noreferrer">Ficha (imprimir)</a>}
        <button className="small ghost" onClick={() => set(null)}>Quitar</button>
      </div>
      {calc && (
        <fieldset className="results">
          <legend>Resultado</legend>
          {calc.segments.map((s) => <p key={s.name} className="small">{s.name}: {fmt(s.velocity_ms, 2)} m/s · pérdida {fmt(s.headloss_m, 3)} m</p>)}
          <p className="small">H geométrica {fmt(calc.geometric_head_m, 2)} m · fricción {fmt(calc.friction_loss_m, 2)} m</p>
          <p><b>H manométrica {fmt(calc.manometric_head_m, 2)} m</b></p>
          <p className="small">Potencia hidráulica {fmt(calc.hydraulic_power_kw, 2)} kW · al eje <b>{fmt(calc.shaft_power_kw, 2)} kW</b> ({fmt(calc.shaft_power_hp, 1)} HP · {fmt(calc.shaft_power_cv, 1)} C.V.)</p>
          <p className="small">Corriente trifásica <b>{fmt(calc.current_a, 1)} A</b> a {fmt(d.voltage_v, 0)} V</p>
          {calc.warnings.map((x, i) => <p key={i} className="warn-text small">{x}</p>)}
          <p className="small">Curva sugerida: {calc.curve_points.map(([q, h]) => `${fmt(q, 1)} L/s – ${fmt(h, 1)} m`).join(" · ")}</p>
          <button className="small" onClick={() => void applyCurve()} title="La bomba que sale del reservorio del pozo toma esta curva; el reservorio, la cota del nivel dinámico">Aplicar curva a la bomba</button>
        </fieldset>
      )}
    </>
  );
}
