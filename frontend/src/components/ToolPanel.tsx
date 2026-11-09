import type { ReactElement } from "react";
import type { Tool } from "../state/store";
import { useEditor } from "../state/store";
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
];

export function ToolPanel() {
  const tool = useEditor((s) => s.tool);
  const setTool = useEditor((s) => s.setTool);
  const current = TOOLS.find((t) => t.id === tool);
  return (
    <aside className="tools" aria-label="Herramientas">
      {TOOLS.map((t) => (
        <button key={t.id} className={tool === t.id ? "on" : ""} onClick={() => setTool(t.id)} title={`${t.label} (${t.key})`} aria-pressed={tool === t.id}>
          <t.icon />
          <span>{t.label}</span>
          <kbd>{t.key}</kbd>
        </button>
      ))}
      <div className="tool-hint">{current?.hint}</div>
    </aside>
  );
}
