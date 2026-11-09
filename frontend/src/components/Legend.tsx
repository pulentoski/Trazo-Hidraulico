import { useMemo, useState } from "react";
import { LINK_MODES, classify, linkScale, pressureScale } from "../lib/colors";
import type { Labels } from "../state/store";
import { criteriaOf, useEditor, writePref } from "../state/store";

function initialOpen(): boolean {
  try { return JSON.parse(localStorage.getItem("trazo.legendOpen") ?? "true") !== false; } catch { return true; }
}

const LABEL_OPTS: { key: keyof Labels; label: string }[] = [
  { key: "nodeIds", label: "ID nudos" }, { key: "linkIds", label: "ID tramos" }, { key: "dn", label: "DN" },
  { key: "pressure", label: "Presión" }, { key: "flow", label: "Caudal" }, { key: "velocity", label: "Velocidad" },
  { key: "headloss", label: "Pérdida unit." },
];

export function Legend() {
  const { linkMode, labels, result, net, period, profiles, project, set } = useEditor();
  const [open, setOpenState] = useState(initialOpen);
  const setOpen = (v: boolean) => { setOpenState(v); writePref("legendOpen", v); };
  const profile = profiles.find((p) => p.id === project?.design_profile_id);
  const crit = criteriaOf(profile);
  const values = useMemo(() => Object.values(net.links).map((l) => {
    if (linkMode === "diameter") return l.props.inner_diameter_mm ?? 0;
    const r = result?.links[l.id];
    if (!r) return 0;
    return Math.abs(linkMode === "flow" ? r.flow[period] : linkMode === "velocity" ? r.velocity[period] : r.headloss[period]);
  }), [net.links, linkMode, result, period]);
  const ls = linkScale(linkMode, crit, values);
  const ps = pressureScale(crit);
  const counts = new Array(ls.colors.length).fill(0);
  if (result || linkMode === "diameter") for (const v of values) counts[classify(v, ls.breaks)]++;

  return (
    <div className={`legend ${open ? "" : "collapsed"}`}>
      <button className="legend-toggle" onClick={() => setOpen(!open)}>{open ? "Leyenda ▾" : "Leyenda ▸"}</button>
      {open && (
        <>
          <label className="legend-row">
            <span>Tramos por</span>
            <select value={linkMode} onChange={(e) => { const v = e.target.value as typeof linkMode; set({ linkMode: v }); writePref("linkMode", v); }}>
              {LINK_MODES.map((m) => <option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}
            </select>
          </label>
          <ul className="swatches">
            {ls.labels.map((l, i) => (
              <li key={l}><i style={{ background: ls.colors[i] }} />{l}{linkMode === "headloss" && i >= 4 ? " · sobre criterio" : ""}<b>{counts[i] || ""}</b></li>
            ))}
          </ul>
          <div className="legend-sub">Nudos por presión</div>
          <ul className="swatches dots">
            {ps.labels.map((l, i) => <li key={l}><i style={{ background: ps.colors[i] }} />{l}</li>)}
          </ul>
          <div className="legend-sub">Etiquetas</div>
          <div className="chips">
            {LABEL_OPTS.map((o) => (
              <label key={o.key} className={labels[o.key] ? "on" : ""}>
                <input type="checkbox" checked={labels[o.key]} onChange={(e) => {
                  const next = { ...labels, [o.key]: e.target.checked };
                  set({ labels: next });
                  writePref("labels", next);
                }} />{o.label}
              </label>
            ))}
          </div>
          {!profile?.verified && profile && <div className="legend-note">Criterios: {profile.name} — <em>no verificado</em></div>}
        </>
      )}
    </div>
  );
}
