import { Link } from "react-router";
import { PATHS } from "../paths";

export function NotFound() {
  return (
    <div className="page">
      <main className="page-body narrow">
        <h1>Página no encontrada</h1>
        <p className="muted">La dirección no corresponde a ninguna sección de Trazo Hidráulico.</p>
        <Link className="btn primary" to={PATHS.home}>Volver al menú</Link>
      </main>
    </div>
  );
}
