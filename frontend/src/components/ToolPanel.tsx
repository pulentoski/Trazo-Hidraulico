import type { ReactElement } from "react";
import { useState } from "react";
import type { Tool } from "../state/store";
import { CoordInputDialog, POINT_TOOLS } from "./Coordinates";
import { useEditor, writePref } from "../state/store";
import { Icon } from "./Icons";

export type ToolGroup = "Selección" | "Red" | "Clientes" | "Análisis" | "Edición";

/** Herramientas en orden de uso, agrupadas; la tecla de cada una es su atajo (también en la tabla de docs/estilo.md). */
export const TOOLS: { id: Tool; label: string; key: string; icon: () => ReactElement; hint: string; group: ToolGroup }[] = [
  { group: "Selección", id: "select", label: "Seleccionar", key: "V", icon: Icon.select, hint: "Clic: seleccionar · Mayús+arrastre: caja · arrastre: desplazar" },
  { group: "Selección", id: "multiselect", label: "Selección múltiple", key: "B", icon: Icon.multi, hint: "Arrastre una caja o haga clic para agregar/quitar" },
  { group: "Selección", id: "move", label: "Mover", key: "M", icon: Icon.move, hint: "Arrastre nudos o vértices; se recalcula al soltar" },
  { group: "Red", id: "junction", label: "Nudo", key: "N", icon: Icon.junction, hint: "Clic en el mapa para ubicar un nudo de consumo" },
  { group: "Red", id: "pipe", label: "Tubería", key: "T", icon: Icon.pipe, hint: "Clic en nudo de inicio, clics para vértices, clic en nudo final · doble clic termina en nudo nuevo · Esc cancela" },
  { group: "Red", id: "tank", label: "Estanque", key: "E", icon: Icon.tank, hint: "Clic en el mapa para ubicar un estanque" },
  { group: "Red", id: "reservoir", label: "Reservorio", key: "R", icon: Icon.reservoir, hint: "Clic en el mapa para ubicar un reservorio (fuente de carga fija)" },
  { group: "Red", id: "well", label: "Pozo", key: "W", icon: Icon.well, hint: "Clic donde está el pozo: se asocia al reservorio más cercano (si hay uno a menos de 50 m)" },
  { group: "Red", id: "shutoff", label: "Válvula de corte", key: "L", icon: Icon.shutoff, hint: "Clic sobre una tubería para ubicar una válvula (llave) de corte · clic en una llave para seleccionarla" },
  { group: "Red", id: "hydrant", label: "Grifo", key: "G", icon: Icon.hydrant, hint: "Clic donde está el grifo: se conecta al nudo de consumo más cercano" },
  { group: "Clientes", id: "client", label: "Cliente", key: "C", icon: Icon.client, hint: "Clic donde está el cliente: se conecta a la tubería más cercana (nudo cercano o nudo nuevo)" },
  { group: "Análisis", id: "feasibility", label: "Factibilidad", key: "F", icon: Icon.feasibility, hint: "Clic sobre una tubería: consumo y cota → simula la red con el cliente sin modificar el proyecto" },
  { group: "Análisis", id: "measure", label: "Medir", key: "D", icon: Icon.measure, hint: "Clics para medir distancias · doble clic o Esc reinicia" },
  { group: "Edición", id: "delete", label: "Eliminar", key: "X", icon: Icon.trash, hint: "Clic en un elemento para eliminarlo (pide confirmación)" },
];

const GROUPS: ToolGroup[] = ["Selección", "Red", "Clientes", "Análisis", "Edición"];

export function ToolPanel() {
  const tool = useEditor((s) => s.tool);
  const setTool = useEditor((s) => s.setTool);
  const current = TOOLS.find((t) => t.id === tool);
  const collapsed = useEditor((s) => s.toolsCollapsed);
  const readOnly = useEditor((s) => s.readOnly);
  const [coordOpen, setCoordOpen] = useState(false);
  const fold = () => { useEditor.getState().set({ toolsCollapsed: !collapsed }); writePref("toolsCollapsed", !collapsed); };
  return (
    <aside className={`tools ${collapsed ? "collapsed" : ""}`} aria-label="Herramientas">
      <button className="tools-fold" onClick={fold} aria-expanded={!collapsed}
        title={collapsed ? "Mostrar los nombres de las herramientas" : "Reducir la barra a íconos (más espacio para el mapa)"}>
        {collapsed ? <Icon.chevronRight /> : <Icon.chevronLeft />}
        <span>{collapsed ? "" : "Plegar"}</span>
      </button>
      {GROUPS.map((g) => (
        <div key={g} className="tool-group" role="group" aria-label={g}>
          <p className="tool-group-title" aria-hidden="true">{g}</p>
          {TOOLS.filter((t) => t.group === g).map((t) => (
            <button key={t.id} className={tool === t.id ? "on" : ""} onClick={() => setTool(t.id)} title={`${t.label} (${t.key})`} aria-pressed={tool === t.id}
              aria-label={collapsed ? t.label : undefined} aria-keyshortcuts={t.key}>
              <span className="tool-icon"><t.icon /></span>
              <span className="tool-label">{t.label}</span>
              <kbd>{t.key}</kbd>
            </button>
          ))}
        </div>
      ))}
      {!collapsed && <div className="tool-hint">{current?.hint}</div>}
      {current && POINT_TOOLS.has(current.id) && !readOnly && (
        <button className="coord-tool" onClick={() => setCoordOpen(true)} title={`${current.label}: crear en una coordenada (lat/lon, GMS o UTM)`}
          aria-label={`Ingresar coordenadas (${current.label})`}>
          <Icon.pin />
          <span>Ingresar coordenadas</span>
        </button>
      )}
      {coordOpen && current && <CoordInputDialog tool={current.id} label={current.label} onClose={() => setCoordOpen(false)} />}
    </aside>
  );
}
