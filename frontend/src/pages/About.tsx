import { PageHeader } from "../components/PageHeader";
import { useEditor } from "../state/store";

export function About() {
  const engine = useEditor((s) => s.engine);
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body narrow">
        <h1>Acerca de</h1>
        <section className="card">
          <h2>Trazo Hidráulico</h2>
          <p>Diseño y simulación de redes de agua potable sobre mapa.</p>
          <dl className="kv">
            <dt>Versión de la aplicación</dt><dd className="mono">{__APP_VERSION__}</dd>
          </dl>
        </section>
        <section className="card">
          <h2>Motor hidráulico</h2>
          {engine ? (
            <dl className="kv">
              <dt>Motor</dt><dd>OWA-EPANET {engine.wheel_version} (único motor, ejecutado en el servidor)</dd>
              <dt>Fuente</dt><dd>github.com/OpenWaterAnalytics/EPANET, tag <span className="mono">{engine.epanet_tag}</span></dd>
              <dt>SHA del tag</dt><dd className="mono break">{engine.epanet_sha ?? "—"}</dd>
              <dt>EN_getversion</dt><dd className="mono">{engine.en_getversion ?? "—"}</dd>
            </dl>
          ) : <p className="muted">Consultando el motor…</p>}
          <p className="muted small">Resultados validados contra el ejecutable runepanet compilado del mismo tag (docs/validation).</p>
        </section>
        <section className="card">
          <h2>Créditos</h2>
          <p className="credits">Daniel Ruz Moreno · pulentoski</p>
          <p className="muted small">OWA-EPANET (licencia MIT, Open Water Analytics) · Tipografía IBM Plex (SIL OFL).</p>
        </section>
      </main>
    </div>
  );
}
