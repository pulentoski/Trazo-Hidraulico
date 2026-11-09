// Perfil: contraseña, segundo factor (TOTP) y sesiones activas.
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import type { MfaSetup, SessionOut } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";
import { useEditor } from "../state/store";

export function Profile() {
  const { me, refresh } = useAuth();
  const toast = useEditor((s) => s.toast);
  const [params] = useSearchParams();
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const load = useCallback(() => api.sessions().then(setSessions).catch(() => undefined), []);
  useEffect(() => { void load(); }, [load]);
  if (!me) return null;
  const run = async (f: () => Promise<unknown>, ok: string) => {
    try { await f(); toast(ok); await refresh(); } catch (e) { toast(errorText(e), "error"); }
  };
  return (
    <div className="page">
      <PageHeader />
      <main className="page-body narrow">
        {(params.get("mfa") || me.mfa_setup_required) && !me.mfa_enabled && (
          <p className="notice warn">Su rol exige el segundo factor: configúrelo para continuar.</p>
        )}
        <section className="card">
          <h2>Mi cuenta</h2>
          <dl className="kv"><dt>Correo</dt><dd>{me.email}</dd><dt>Nombre</dt><dd>{me.name || "—"}</dd>
            <dt>Organizaciones</dt><dd>{me.orgs.map((o) => `${o.name} (${ROLE_LABEL[o.role]})`).join(" · ") || "—"}</dd>
            {me.is_superadmin && <><dt>Plataforma</dt><dd>Superadministrador</dd></>}</dl>
        </section>
        <section className="card">
          <h2>Cambiar contraseña</h2>
          <form className="auth-form" onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.changePassword(cur, pw); setCur(""); setPw(""); void load(); }, "Contraseña actualizada: se cerraron sus otras sesiones."); }}>
            <label className="field stacked"><span>Contraseña actual</span><input type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} /></label>
            <label className="field stacked"><span>Contraseña nueva</span><input type="password" autoComplete="new-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
            <button className="primary">Guardar</button>
          </form>
        </section>
        <section className="card">
          <h2>Segundo factor (TOTP)</h2>
          {me.mfa_enabled ? (<>
            <p className="ok-text">Activo.</p>
            <form className="auth-form" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget.elements.namedItem("pw") as HTMLInputElement; void run(() => api.mfaDisable(f.value), "Segundo factor desactivado."); }}>
              <label className="field stacked"><span>Contraseña para desactivarlo</span><input name="pw" type="password" required /></label>
              <button>Desactivar</button>
            </form>
          </>) : setup ? (
            <form className="auth-form" onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.mfaEnable(code); setSetup(null); }, "Segundo factor activado."); }}>
              <p>Escanee el código con su aplicación (Google Authenticator, Microsoft Authenticator, FreeOTP…) o ingrese la clave a mano.</p>
              <div className="qr" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} />
              <p className="mono small">{setup.secret}</p>
              <label className="field stacked"><span>Código de 6 dígitos</span><input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
              <button className="primary">Activar</button>
            </form>
          ) : <button className="primary" onClick={async () => { try { setSetup(await api.mfaSetup()); } catch (e) { toast(errorText(e), "error"); } }}>Configurar</button>}
        </section>
        <section className="card">
          <h2>Sesiones activas</h2>
          <table className="tbl compact">
            <thead><tr><th>Dispositivo</th><th>IP</th><th>Última actividad</th><th></th></tr></thead>
            <tbody>{sessions.map((s) => (
              <tr key={s.id}><td className="small">{s.current ? "Esta sesión · " : ""}{(s.user_agent ?? "").slice(0, 60)}</td><td>{s.ip ?? "—"}</td>
                <td>{new Date(s.last_seen_at).toLocaleString("es-CL")}</td>
                <td>{!s.current && <button className="small ghost" onClick={async () => { await api.closeSession(s.id); void load(); }}>Cerrar</button>}</td></tr>
            ))}</tbody>
          </table>
          <button onClick={async () => { await api.logoutAll(); window.location.assign(PATHS.login); }}>Cerrar todas las sesiones</button>
        </section>
      </main>
    </div>
  );
}
