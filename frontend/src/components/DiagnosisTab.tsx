// Pestaña «Diagnóstico»: interpretación automática de la última simulación (reglas sobre los resultados de EPANET).
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DiagnosisResult, Suggestion } from "../api/types";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

const ICON = { ok: "✔", warning: "▲", problem: "✖" } as const;

export function DiagnosisTab() {
  const { project, result, net, focus, toast, commit, catalog, options } = useEditor();
  const [d, setD] = useState<DiagnosisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const version = result?.model_version;
  useEffect(() => {
    if (!project || !version) return;
    let alive = true;
    setBusy(true);
    api.diagnosis(project.id, version).then((r) => alive && setD(r)).catch((e) => alive && toast(errorText(e), "error"))
      .finally(() => alive && setBusy(false));
    return () => { alive = false; };
  }, [project, version, toast]);
  if (!project) return null;
  if (!result) return <p className="muted pad">Simule el modelo para obtener el diagnóstico.</p>;

  const go = (type: string, id: string) => {
    const pool = { node: net.nodes, link: net.links, client: net.clients, well: net.wells, hydrant: net.hydrants, shutoff: net.shutoffs }[type];
    const hit = pool && Object.values(pool).find((x) => x.id === id);
    if (hit) focus([hit.uid]);
  };
  const apply = (s: Suggestion) => {
    const a = s.action as { links?: { link: string; dn_to: number }[]; pump?: string; schedule?: number[]; level_control?: { tank: string; on_below: number; off_above: number } };
    commit((n) => {
      const links = { ...n.links };
      for (const [k, l] of Object.entries(links)) {
        const ch = a.links?.find((x) => x.link === l.id);
        if (ch) {
          const item = catalog.find((c) => c.material === l.props.material && c.pipe_class === l.props.pipe_class && c.dn === ch.dn_to);
          if (item) links[k] = { ...l, props: { ...l.props, dn: item.dn, inner_diameter_mm: item.inner_diameter_mm, catalog_pipe_id: item.id,
            inner_diameter_source: "catalogo", roughness: options.headloss === "D-W" ? item.dw_roughness_mm : options.headloss === "C-M" ? item.manning_n : item.hw_c } };
        }
        if (a.pump && l.id === a.pump) {
          links[k] = { ...links[k], props: { ...links[k].props, ...(a.schedule ? { schedule: a.schedule } : {}), ...(a.level_control ? { level_control: a.level_control } : {}) } };
        }
      }
      return { ...n, links };
    });
    toast("Sugerencia aplicada: se guarda y simula automáticamente.");
  };
  const refs = (rs: { type: string; id: string }[]) => rs.map((r) => (
    <button key={`${r.type}-${r.id}`} className="ref-chip" onClick={() => go(r.type, r.id)} title="Ver en el mapa">{r.id}</button>
  ));
  return (
    <div className="diag-tab">
      <div className="toolbar">
        {d && <span className={`diag-status ${d.status === "cumple" ? "ok" : d.status === "no cumple" ? "bad" : "warn"}`}>{d.status[0].toUpperCase() + d.status.slice(1)}</span>}
        {busy && <span className="muted small">Analizando y verificando sugerencias…</span>}
        <a className="btn small" href={api.reportUrl(project.id, version)} target="_blank" rel="noreferrer">Informe técnico (imprimir)</a>
      </div>
      {d && (<>
        <p className="diag-summary">{d.summary.text}</p>
        <ul className="diag-list">
          {d.items.map((i, k) => (
            <li key={k} className={i.severity}><b>{ICON[i.severity]}</b> {i.text} {refs(i.refs ?? [])}</li>
          ))}
        </ul>
        <h4>Sugerencias</h4>
        {d.suggestions.length === 0 ? <p className="muted small">Sin sugerencias: no hay problemas que se resuelvan con un cambio verificado.</p> : (
          <ul className="diag-list">
            {d.suggestions.map((s, k) => (
              <li key={k} className="suggestion"><b>💡</b> {s.text} {refs(s.refs ?? [])}
                <div className="muted small">{s.verification}</div>
                <button className="small" onClick={() => apply(s)}>Aplicar</button></li>
            ))}
          </ul>
        )}
      </>)}
    </div>
  );
}
