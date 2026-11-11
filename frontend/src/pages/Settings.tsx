// Configuración: criterios de diseño por defecto, unidades, tema y estado del mapa base.
import { PageHeader } from "../components/PageHeader";
import { fmt } from "../lib/format";
import { MapBaseSection } from "../components/MapBaseSettings";
import type { ThemePref } from "../state/store";
import { useEditor, writePref } from "../state/store";

const UNITS: [string, string, string][] = [
  ["Caudal y demanda", "L/s", "litros por segundo (EPANET UNITS LPS)"],
  ["Presión, cota, nivel y largo", "m", "metros de columna de agua / metros"],
  ["Diámetro y rugosidad D-W", "mm", "diámetro interior y ε en milímetros"],
  ["Velocidad", "m/s", ""],
  ["Pérdida unitaria", "m/km", "pérdida de carga por kilómetro de tubería"],
  ["Volumen", "m³", ""],
];

export function Settings() {
  const { themePref, profiles, defaultProfileId, set } = useEditor();
  const fallback = profiles.find((p) => p.id === defaultProfileId) ?? profiles[0];
  const setTheme = (v: ThemePref) => { set({ themePref: v }); writePref("theme", v); };
  const setProfile = (id: number) => { set({ defaultProfileId: id }); writePref("defaultProfileId", id); };

  return (
    <div className="page">
      <PageHeader />
      <main className="page-body narrow">
        <h1>Configuración</h1>

        <section className="card">
          <h2>Criterios de diseño por defecto</h2>
          <p className="muted small">Se asignan a los proyectos nuevos. Cada proyecto conserva su perfil.</p>
          {profiles.length === 0 ? <p className="muted">Cargando perfiles…</p> : (<>
            <label className="field"><span>Perfil</span>
              <select value={fallback?.id ?? ""} onChange={(e) => setProfile(Number(e.target.value))}>
                {profiles.map((p) => <option key={p.id} value={p.id}>{p.name} (v{p.version}){p.verified ? "" : " · no verificado"}</option>)}
              </select>
            </label>
            {fallback && (<>
              <table className="tbl compact">
                <tbody>
                  {fallback.criteria.map((c) => (
                    <tr key={c.key}><td>{c.label}</td>
                      <td className="num">{c.min != null ? `≥ ${fmt(c.min, 1)}` : ""}{c.max != null ? `≤ ${fmt(c.max, 1)}` : ""} {c.unit}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">{fallback.source}{fallback.verified ? "" : " "}{!fallback.verified && <span className="badge warn">no verificado</span>}</p>
            </>)}
          </>)}
        </section>

        <section className="card">
          <h2>Unidades</h2>
          <p className="muted small">El modelo trabaja en el sistema internacional; los .inp importados en otras unidades se convierten al abrirlos.</p>
          <table className="tbl compact">
            <tbody>{UNITS.map(([what, u, note]) => <tr key={what}><td>{what}</td><td className="mono">{u}</td><td className="muted">{note}</td></tr>)}</tbody>
          </table>
        </section>

        <section className="card">
          <h2>Tema</h2>
          <div className="seg plain" role="radiogroup" aria-label="Tema">
            {([["light", "Claro"], ["dark", "Oscuro"], ["system", "Según el sistema"]] as [ThemePref, string][]).map(([v, l]) => (
              <button key={v} role="radio" aria-checked={themePref === v} className={themePref === v ? "on" : ""} onClick={() => setTheme(v)}>{l}</button>
            ))}
          </div>
        </section>

        <MapBaseSection />
      </main>
    </div>
  );
}
