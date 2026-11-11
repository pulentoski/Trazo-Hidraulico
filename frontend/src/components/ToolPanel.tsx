import type { ReactElement } from "react";
import type { Tool } from "../state/store";
import { useEditor, writePref } from "../state/store";
import { Icon } from "./Icons";

export const TOOLS: { id: Tool; label: string; key: string; icon: () => ReactElement; hint: string }[] = [
  { id: "select", label: "Seleccionar", key: "V", icon: Icon.select, hint: "Clic: seleccionar · Mayús+arrastre: caja · arrastre: desplazar" },
  { id: "multiselect", label: "Selección múltiple", key: "B", icon: Icon.multi, hint: "Arrastre una caja o haga clic para agregar/quitar" },
  { id: "junction", label: "Nudo", key: "N", icon: Icon.junction, hint: "Clic en el mapa para ubicar un nudo de consumo" },
  { id: "pipe", label: "Tubería", key: "T", icon: Icon.pipe, hint: "Clic en nudo de inicio, clics para vértices, clic en nudo final · doble clic termina en nudo nuevo · Esc cancela" },
  { id: "tank", label: "Estanque", key: "E", icon: Icon.tank, hint: "Clic en el mapa para ubicar un estanque" },
  { id: "reservoir", label: "Reservorio", key: "R", icon: Icon.reservoir, hint: "Clic en el mapa para ubicar un reservorio (fuente de carga fija)" },
  { id: "move", label: "Mover", key: "M", icon: Icon.move, hint: "Arrastre nudos o vértices; se recalcula al soltar" },
  { id: "delete", label: "Eliminar", key: "X", icon: Icon.trash, hint: "Clic en un elemento para eliminarlo (pide confirmación)" },
  { id: "measure", label: "Medir", key: "D", icon: Icon.measure, hint: "Clics para medir distancias · doble clic o Esc reinicia" },
  { id: "client", label: "Cliente", key: "C", icon: Icon.client, hint: "Clic donde está el cliente: se conecta a la tubería más cercana (nudo cercano o nudo nuevo)" },
  { id: "shutoff", label: "Llave de corte", key: "L", icon: Icon.shutoff, hint: "Clic sobre una tubería para ubicar una llave · clic en una llave para seleccionarla" },
  { id: "hydrant", label: "Grifo", key: "G", icon: Icon.hydrant, hint: "Clic donde está el grifo: se conecta al nudo de consumo más cercano" },
  { id: "well", label: "Pozo", key: "W", icon: Icon.well, hint: "Clic donde está el pozo: se asocia al reservorio más cercano (si hay uno a menos de 50 m)" },
  { id: "feasibility", label: "Factibilidad", key: "F", icon: Icon.feasibility, hint: "Clic sobre una tubería: consumo y cota → simula la red con el cliente sin modificar el proyecto" },
];

export function ToolPanel() {
  const tool = useEditor((s) => s.tool);
  const setTool = useEditor((s) => s.setTool);
  const current = TOOLS.find((t) => t.id === tool);
  const collapsed = useEditor((s) => s.toolsCollapsed);
  const fold = () => { useEditor.getState().set({ toolsCollapsed: !collapsed }); writePref("toolsCollapsed", !collapsed); };
  return (
    <aside className={`tools ${collapsed ? "collapsed" : ""}`} aria-label="Herramientas">
      <button className="tools-fold" onClick={fold} aria-expanded={!collapsed}
        title={collapsed ? "Mostrar los nombres de las herramientas" : "Reducir la barra a íconos (más espacio para el mapa)"}>
        <svg viewBox="0 0 10 10" aria-hidden="true"><path d={collapsed ? "M3.5 2 6.5 5 3.5 8" : "M6.5 2 3.5 5 6.5 8"} /></svg>
        <span>{collapsed ? "" : "Plegar"}</span>
      </button>
      {TOOLS.map((t) => (
        <button key={t.id} className={tool === t.id ? "on" : ""} onClick={() => setTool(t.id)} title={`${t.label} (${t.key})`} aria-pressed={tool === t.id}
          aria-label={collapsed ? t.label : undefined}>
          <t.icon />
          <span>{t.label}</span>
          <kbd>{t.key}</kbd>
        </button>
      ))}
      {!collapsed && <div className="tool-hint">{current?.hint}</div>}
    </aside>
  );
}
