import { useMemo, useState } from "react";
import { LINK_MODES, legendClasses, linkScale, linkValue, pressureScale } from "../lib/colors";
import { criteriaOf, useEditor, writePref } from "../state/store";

function initialOpen(): boolean {
  try { return JSON.parse(localStorage.getItem("trazo.legendOpen") ?? "true") !== false; } catch { return true; }
}

export function Legend() {
  const { linkMode, result, net, period, profiles, project, set, designParams: s_designParams } = useEditor();
  const [open, setOpenState] = useState(initialOpen);
  const setOpen = (v: boolean) => { setOpenState(v); writePref("legendOpen", v); };
  const profile = profiles.find((p) => p.id === project?.design_profile_id);
  const crit = criteriaOf(profile, s_designParams);
  const values = useMemo(() => Object.values(net.links)
    .map((l) => linkValue(linkMode, l, result?.links[l.id], period))
    .filter((v): v is number => v !== null), [net.links, linkMode, result, period]);
  const ls = linkScale(linkMode, crit, values);
  const classes = legendClasses(ls, values);
  const ps = pressureScale(crit);

  return (
    <div className={`legend ${open ? "" : "collapsed"}`} aria-label="Leyenda">
      <button className="legend-toggle" onClick={() => setOpen(!open)} aria-expanded={open} title={open ? "Plegar la leyenda" : "Mostrar la leyenda"}>{open ? "Leyenda ▾" : "Leyenda ▸"}</button>
      {open && (
        <>
          <label className="legend-row">
            <span>Tramos por</span>
            <select value={linkMode} onChange={(e) => { const v = e.target.value as typeof linkMode; set({ linkMode: v }); writePref("linkMode", v); }}>
              {LINK_MODES.map((m) => <option key={m.id} value={m.id}>{m.label} ({m.unit})</option>)}
            </select>
          </label>
          {classes.length ? (
            <ul className="swatches">
              {classes.map((c) => (
                <li key={c.label}><i style={{ background: c.color }} />{c.label}{linkMode === "headloss" && c.lower !== null && c.lower >= crit.headlossMax - 1e-9 ? " · sobre criterio" : ""}<b>{c.count}</b></li>
              ))}
            </ul>
          ) : <div className="legend-note">{linkMode === "diameter" ? "Sin tramos con diámetro." : "Sin resultados: simule para ver la escala."}</div>}
          <div className="legend-sub">Nudos por presión</div>
          <ul className="swatches dots">
            {ps.labels.map((l, i) => <li key={l}><i style={{ background: ps.colors[i] }} />{l}</li>)}
          </ul>
          {!profile?.verified && profile && <div className="legend-note">Criterios: {profile.name} — <em>no verificado</em></div>}
        </>
      )}
    </div>
  );
}
