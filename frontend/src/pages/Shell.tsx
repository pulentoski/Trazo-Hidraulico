// Marco común a todas las rutas: tema, datos de referencia (catálogo, perfiles, motor) y avisos.
import { useEffect } from "react";
import { Outlet } from "react-router";
import { api } from "../api/client";
import { Toasts } from "../components/Dialogs";
import { resolveTheme, useEditor } from "../state/store";

export function Shell() {
  const themePref = useEditor((s) => s.themePref);
  const theme = useEditor((s) => s.theme);
  const set = useEditor((s) => s.set);

  useEffect(() => {
    set({ theme: resolveTheme(themePref) });
    if (themePref !== "system") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => set({ theme: resolveTheme("system") });
    mq?.addEventListener("change", on);
    return () => mq?.removeEventListener("change", on);
  }, [themePref, set]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    Promise.all([api.catalog(), api.profiles(), api.engine()])
      .then(([catalog, profiles, engine]) => set({ catalog, profiles, engine }))
      .catch(() => useEditor.getState().toast("No fue posible conectar con la API.", "error"));
  }, [set]);

  return (
    <>
      <Outlet />
      <Toasts />
    </>
  );
}
