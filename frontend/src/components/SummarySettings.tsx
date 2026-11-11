// Configuración del Resumen: rangos de presión, margen del área operacional, vida útil y precios de renovación,
// atributo de sector y medidores de producción. Valores sugeridos marcados «no verificado».
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SummarySettings } from "../api/types";
import { fmt, parseNum } from "../lib/format";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";
import { Modal } from "./Dialogs";

export function SummarySettingsDialog({ pid, materials, onClose, onSaved }: { pid: string; materials: string[]; onClose: () => void; onSaved: () => void }) {
  const toast = useEditor((s) => s.toast);
  const [st, setSt] = useState<SummarySettings | null>(null);
  const [ranges, setRanges] = useState("");
  useEffect(() => {
    api.summarySettings(pid).then((s) => { setSt(s); setRanges((s.pressure_ranges ?? []).map((x) => fmt(x, 0)).join("; ")); })
      .catch((e) => toast(errorText(e), "error"));
  }, [pid, toast]);
  if (!st) return null;
  const life = st.service_life ?? {};
  const mats = [...new Set([...materials, ...Object.keys(life)])].sort();
  const prices = st.prices ?? [];
  const meters = st.production_meters ?? [];
  const save = async () => {
    const r = ranges.split(/[;\s]+/).filter(Boolean).map((x) => parseNum(x));
    if (!r.length || r.some((x) => x === null) || r.some((x, i) => i > 0 && (x as number) <= (r[i - 1] as number))) {
      toast("Los límites de presión deben ser números crecientes separados por «;».", "error");
      return;
    }
    try {
      await api.saveSummarySettings(pid, { ...st, pressure_ranges: r as number[] });
      toast("Configuración del resumen guardada.");
      onSaved();
    } catch (e) { toast(errorText(e), "error"); }
  };
  const reset = async () => {
    try { await api.resetSummarySettings(pid); toast("Valores sugeridos restablecidos."); onSaved(); } catch (e) { toast(errorText(e), "error"); }
  };
  const num = (v: string, fallback: number) => parseNum(v) ?? fallback;
  return (
    <Modal title="Configuración del resumen" onClose={onClose} wide>
      <div className="settings-grid">
        <section>
          <h3>Presión y área</h3>
          <label className="field stacked"><span>Límites de los rangos de presión (m.c.a.)</span>
            <input value={ranges} onChange={(e) => setRanges(e.target.value)} placeholder="15; 30; 50; 70" /></label>
          <label className="field stacked"><span>Margen del área operacional (m)</span>
            <input inputMode="decimal" defaultValue={fmt(st.area_margin_m ?? 50, 0)} onBlur={(e) => setSt({ ...st, area_margin_m: num(e.target.value, st.area_margin_m ?? 50) })} /></label>
          <label className="field stacked"><span>Mayores consumidores</span>
            <select value={st.top_n ?? 10} onChange={(e) => setSt({ ...st, top_n: Number(e.target.value) as 10 | 20 })}><option value={10}>Top 10</option><option value={20}>Top 20</option></select></label>
          <label className="field stacked"><span>Atributo de sector (clientes y macromedidores)</span>
            <input value={st.sector_attribute ?? "Sector"} onChange={(e) => setSt({ ...st, sector_attribute: e.target.value })} /></label>
          <h3>Medidores de producción</h3>
          <p className="muted small">Vacío = automático: el medidor del pozo abastece «Total» y cada macromedidor, el sector de su tramo.</p>
          {meters.map((m, i) => (
            <div className="inline meter-row" key={i}>
              <input value={m.sector} onChange={(e) => setSt({ ...st, production_meters: meters.map((x, k) => (k === i ? { ...x, sector: e.target.value } : x)) })} aria-label="Sector" placeholder="Sector" />
              <select value={m.element_type} onChange={(e) => setSt({ ...st, production_meters: meters.map((x, k) => (k === i ? { ...x, element_type: e.target.value as "well" | "link" } : x)) })} aria-label="Tipo de medidor">
                <option value="well">Pozo</option><option value="link">Macromedidor (tramo)</option></select>
              <input value={m.element_id} onChange={(e) => setSt({ ...st, production_meters: meters.map((x, k) => (k === i ? { ...x, element_id: e.target.value } : x)) })} aria-label="ID" placeholder="ID" />
              <button className="ghost small" onClick={() => setSt({ ...st, production_meters: meters.filter((_, k) => k !== i) })} aria-label="Quitar medidor">✕</button>
            </div>))}
          <button className="small" onClick={() => setSt({ ...st, production_meters: [...meters, { sector: "Total", element_type: "well", element_id: "" }] })}>+ Medidor</button>
        </section>
        <section>
          <h3>Vida útil por material (años)</h3>
          <table className="tbl compact">
            <tbody>{mats.map((m) => (
              <tr key={m}><td>{m}</td><td className="num">
                <input className="cell-input" inputMode="numeric" defaultValue={life[m] ?? st.default_life ?? 50} aria-label={`Vida útil ${m}`}
                  onBlur={(e) => setSt({ ...st, service_life: { ...life, [m]: Math.round(num(e.target.value, life[m] ?? 50)) } })} /></td></tr>))}
              <tr><td className="muted">Otros materiales</td><td className="num">
                <input className="cell-input" inputMode="numeric" defaultValue={st.default_life ?? 50} aria-label="Vida útil por defecto"
                  onBlur={(e) => setSt({ ...st, default_life: Math.round(num(e.target.value, st.default_life ?? 50)) })} /></td></tr>
            </tbody>
          </table>
          <label className="check small"><input type="checkbox" checked={!!st.life_verified} onChange={(e) => setSt({ ...st, life_verified: e.target.checked })} />
            Vida útil verificada (desmarcado = valores sugeridos «no verificado»)</label>
          <h3>Costo de renovación (CLP por metro)</h3>
          <table className="tbl compact">
            <thead><tr><th>Material</th><th className="num">DN hasta</th><th className="num">CLP/m</th><th /></tr></thead>
            <tbody>{prices.map((p, i) => (
              <tr key={i}>
                <td><input className="cell-input wide" value={p.material ?? "*"} aria-label="Material del precio"
                  onChange={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, material: e.target.value || "*" } : x)) })} /></td>
                <td className="num"><input className="cell-input" inputMode="numeric" defaultValue={p.dn_max} aria-label="DN máximo"
                  onBlur={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, dn_max: Math.round(num(e.target.value, p.dn_max)) } : x)) })} /></td>
                <td className="num"><input className="cell-input" inputMode="numeric" defaultValue={p.price_m} aria-label="Precio por metro"
                  onBlur={(e) => setSt({ ...st, prices: prices.map((x, k) => (k === i ? { ...x, price_m: num(e.target.value, p.price_m) } : x)) })} /></td>
                <td><button className="ghost small" onClick={() => setSt({ ...st, prices: prices.filter((_, k) => k !== i) })} aria-label="Quitar precio">✕</button></td>
              </tr>))}</tbody>
          </table>
          <button className="small" onClick={() => setSt({ ...st, prices: [...prices, { material: "*", dn_max: 110, price_m: 60000 }] })}>+ Precio</button>
          <p className="muted small">«*» = cualquier material. Se usa la fila del material (o «*») con el menor «DN hasta» que cubra el DN del tramo.</p>
          <label className="check small"><input type="checkbox" checked={!!st.prices_verified} onChange={(e) => setSt({ ...st, prices_verified: e.target.checked })} />
            Precios verificados</label>
        </section>
      </div>
      <div className="modal-actions">
        <button className="ghost" onClick={() => void reset()}>Valores sugeridos</button>
        <span className="tabs-spacer" />
        <button className="ghost" onClick={onClose}>Cancelar</button>
        <button className="primary" onClick={() => void save()}>Guardar</button>
      </div>
    </Modal>
  );
}
