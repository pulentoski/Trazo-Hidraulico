// Pantallas públicas: ingreso (con segundo factor), recuperación de contraseña e invitación.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { InvitationInfo } from "../api/types";
import { Brand } from "../components/PageHeader";
import { PATHS } from "../paths";
import { ROLE_LABEL, useAuth } from "../state/auth";
import { errorText } from "../state/projects";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <Brand />
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  );
}

function safeNext(v: string | null): string {
  return v && v.startsWith("/") && !v.startsWith("//") ? v : PATHS.home;
}

export function Login() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const refresh = useAuth((s) => s.refresh);
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.me().then((me) => { if (me.mfa_pending) setStep("mfa"); else navigate(safeNext(params.get("volver")), { replace: true }); })
      .catch(() => undefined);
  }, [navigate, params]);
  const done = async () => {
    const me = await refresh();
    navigate(me?.mfa_setup_required ? `${PATHS.profile}?mfa=1` : safeNext(params.get("volver")), { replace: true });
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (step === "password") {
        const r = await api.login(email, password);
        if (r.mfa_required) setStep("mfa");
        else await done();
      } else {
        await api.mfa(code);
        await done();
      }
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return (
    <Card title={step === "password" ? "Ingresar" : "Segundo factor"}>
      <form onSubmit={submit} className="auth-form">
        {step === "password" ? (<>
          <label className="field stacked"><span>Correo</span>
            <input type="email" autoComplete="username" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label className="field stacked"><span>Contraseña</span>
            <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        </>) : (
          <label className="field stacked"><span>Código de 6 dígitos de su aplicación de autenticación</span>
            <input inputMode="numeric" autoComplete="one-time-code" autoFocus required pattern="[0-9 ]{6,8}" value={code} onChange={(e) => setCode(e.target.value)} /></label>
        )}
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? "Verificando…" : step === "password" ? "Ingresar" : "Verificar"}</button>
        {step === "password" && <Link className="muted small" to={PATHS.recover}>¿Olvidó su contraseña?</Link>}
      </form>
    </Card>
  );
}

export function Recover() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (token) {
        if (pw !== pw2) throw new Error("Las contraseñas no coinciden.");
        await api.resetPassword(token, pw);
        setMsg("Contraseña actualizada. Ya puede ingresar.");
        setTimeout(() => navigate(PATHS.login), 1500);
      } else {
        const r = await api.recover(email);
        setMsg(r.email_enabled ? "Si el correo corresponde a una cuenta, recibirá un enlace para crear una contraseña nueva."
          : "Esta instalación no tiene correo saliente: pida al administrador de su organización un enlace de recuperación.");
      }
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return (
    <Card title={token ? "Nueva contraseña" : "Recuperar contraseña"}>
      <form onSubmit={submit} className="auth-form">
        {token ? (<>
          <label className="field stacked"><span>Contraseña nueva</span>
            <input type="password" autoComplete="new-password" required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          <label className="field stacked"><span>Repítala</span>
            <input type="password" autoComplete="new-password" required value={pw2} onChange={(e) => setPw2(e.target.value)} /></label>
          <p className="muted small">Al menos 10 caracteres, con letras y números.</p>
        </>) : (
          <label className="field stacked"><span>Correo</span>
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        )}
        {msg && <p className="ok-text" role="status">{msg}</p>}
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className="primary" disabled={busy || !!(msg && token)}>{token ? "Guardar contraseña" : "Enviar enlace"}</button>
        <Link className="muted small" to={PATHS.login}>Volver al ingreso</Link>
      </form>
    </Card>
  );
}

export function Invitation() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const refresh = useAuth((s) => s.refresh);
  const [info, setInfo] = useState<InvitationInfo | null>(null);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.invitation(token).then(setInfo).catch((e) => setError(errorText(e))); }, [token]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.acceptInvitation(token, name, pw);
      const me = await refresh();
      navigate(me?.mfa_setup_required ? `${PATHS.profile}?mfa=1` : PATHS.home, { replace: true });
    } catch (err) { setError(errorText(err)); }
  };
  return (
    <Card title="Invitación">
      {info ? (
        <form onSubmit={submit} className="auth-form">
          <p>Lo invitaron a <b>{info.org_name}</b> como <b>{ROLE_LABEL[info.role]}</b> ({info.email}).</p>
          {!info.existing_user && <label className="field stacked"><span>Su nombre</span><input required value={name} onChange={(e) => setName(e.target.value)} /></label>}
          <label className="field stacked"><span>{info.existing_user ? "Su contraseña actual" : "Contraseña"}</span>
            <input type="password" autoComplete={info.existing_user ? "current-password" : "new-password"} required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
          {!info.existing_user && <p className="muted small">Al menos 10 caracteres, con letras y números.</p>}
          {error && <p className="field-error" role="alert">{error}</p>}
          <button className="primary">Aceptar invitación</button>
        </form>
      ) : <p className={error ? "field-error" : "muted"}>{error ?? "Cargando…"}</p>}
    </Card>
  );
}
