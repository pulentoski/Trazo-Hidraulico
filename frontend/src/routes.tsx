// Rutas de la aplicación: públicas (ingreso, recuperación, invitación) y de trabajo, protegidas por <RequireAuth>.
import { useEffect } from "react";
import { Navigate, Outlet, createBrowserRouter, useLocation } from "react-router";
import { api } from "./api/client";
import { About } from "./pages/About";
import { Invitation, Login, Recover } from "./pages/Auth";
import { EditorPage } from "./pages/Editor";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { Organization } from "./pages/Organization";
import { Platform } from "./pages/Platform";
import { Profile } from "./pages/Profile";
import { PATHS } from "./paths";
import { Settings } from "./pages/Settings";
import { Shell } from "./pages/Shell";
import { useAuth } from "./state/auth";
import { useEditor } from "./state/store";

/** Guardián de rutas: sin sesión → /login?volver=…; con TOTP obligatorio sin configurar → /perfil. */
export function RequireAuth() {
  const { status, me, refresh } = useAuth();
  const location = useLocation();
  const set = useEditor((s) => s.set);
  useEffect(() => { if (status === "loading") void refresh(); }, [status, refresh]);
  useEffect(() => {
    if (status !== "ok" || !me || me.mfa_setup_required || me.mfa_pending) return;
    Promise.all([api.catalog(), api.profiles(), api.engine()])
      .then(([catalog, profiles, engine]) => set({ catalog, profiles, engine }))
      .catch(() => undefined);
  }, [status, me, set]);
  if (status === "loading") return <div className="loading">Cargando…</div>;
  const back = encodeURIComponent(location.pathname + location.search);
  if (status === "anon" || !me || me.mfa_pending) return <Navigate to={`${PATHS.login}?volver=${back}`} replace />;
  if (me.mfa_setup_required && location.pathname !== PATHS.profile) return <Navigate to={`${PATHS.profile}?mfa=1`} replace />;
  return <Outlet />;
}

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { path: PATHS.login, element: <Login /> },
      { path: PATHS.recover, element: <Recover /> },
      { path: PATHS.invitation, element: <Invitation /> },
      {
        element: <RequireAuth />,
        children: [
          { path: PATHS.home, element: <Home /> },
          { path: PATHS.profile, element: <Profile /> },
          { path: PATHS.organization, element: <Organization /> },
          { path: PATHS.admin, element: <Platform /> },
          { path: PATHS.settings, element: <Settings /> },
          { path: PATHS.about, element: <About /> },
          { path: "/proyecto/:id", element: <EditorPage /> },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
