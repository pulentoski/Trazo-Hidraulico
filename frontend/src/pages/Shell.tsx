// Marco común a todas las rutas: tema, datos de referencia (catálogo, perfiles, motor) y avisos.
import { useEffect } from "react";
import { Outlet } from "react-router";
import { onRateLimitNotice } from "../api/http";
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

  const animations = useEditor((s) => s.animations);
  useEffect(() => {
    onRateLimitNotice((t) => useEditor.getState().toast(t));
    return () => onRateLimitNotice(null);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    document.documentElement.dataset.anim = animations ? "on" : "off";
  }, [animations]);

  return (
    <>
      <Outlet />
      <Toasts />
    </>
  );
}
