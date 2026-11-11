// Tamaño del panel inferior: altura arrastrable (con mínimo y máximo), plegado, normal o maximizado. Se recuerda
// por usuario (localStorage, con try/catch: sin almacenamiento vale solo para la sesión).
import { useCallback, useEffect, useRef, useState } from "react";

export const DEFAULT_H = 290;
export const MIN_H = 140;
const TOP_BAR = 52;
const MAP_MIN = 160;

export const maxH = () => Math.max(MIN_H, (typeof window !== "undefined" ? window.innerHeight : 900) - TOP_BAR - MAP_MIN);
export const clampH = (h: number) => Math.round(Math.min(maxH(), Math.max(MIN_H, h)));

interface Saved { height: number; maximized: boolean; collapsed: boolean }
const key = (user: string) => `trazo.bottomPanel.${user || "anon"}`;

function read(user: string): Saved | null {
  try {
    const v = JSON.parse(localStorage.getItem(key(user)) ?? "null");
    return v && typeof v.height === "number" ? v as Saved : null;
  } catch {
    return null;
  }
}

function write(user: string, v: Saved): void {
  try { localStorage.setItem(key(user), JSON.stringify(v)); } catch { /* sin almacenamiento */ }
}

export function usePanelSize(user: string, collapsed: boolean, setCollapsed: (v: boolean) => void) {
  const [height, setHeight] = useState(DEFAULT_H);
  const [maximized, setMax] = useState(false);
  const [dragging, setDragging] = useState(false);
  const loadedFor = useRef<string | null>(null);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const s = read(user);
    loadedFor.current = user;
    setHeight(clampH(s?.height ?? DEFAULT_H));
    setMax(s?.maximized ?? false);
    if (s && s.collapsed !== collapsed) setCollapsed(s.collapsed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  useEffect(() => {
    if (loadedFor.current === user) write(user, { height, maximized, collapsed });
  }, [user, height, maximized, collapsed]);

  // Al achicar la ventana, la altura se mantiene dentro del máximo.
  useEffect(() => {
    const on = () => setHeight((h) => clampH(h));
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);

  const setSize = useCallback((p: { height?: number; maximized?: boolean; collapsed?: boolean }) => {
    if (p.height !== undefined) { setHeight(clampH(p.height)); setMax(false); }
    if (p.maximized !== undefined) setMax(p.maximized);
    if (p.collapsed !== undefined) setCollapsed(p.collapsed);
  }, [setCollapsed]);

  const startDrag = useCallback((e: React.PointerEvent<HTMLElement>) => {
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    const y0 = e.clientY;
    const h0 = sectionRef.current?.getBoundingClientRect().height ?? DEFAULT_H;
    setDragging(true);
    const move = (ev: PointerEvent) => setHeight(clampH(h0 + (y0 - ev.clientY)));
    const up = () => {
      setDragging(false);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }, []);

  return { height, maximized, setSize, startDrag, dragging, sectionRef };
}
