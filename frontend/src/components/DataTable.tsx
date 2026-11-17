// Tabla común del sistema (docs/estilo.md → Tablas): búsqueda, orden por cualquier columna (texto A–Z, números con
// orden numérico real y fechas), paginación y exportación a CSV. La lógica pura está en lib/table.ts.
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { downloadText, toCsv } from "../lib/csv";
import type { CellType, CellValue } from "../lib/table";
import { cellText, filterRows, paginate, sortRows } from "../lib/table";
import { Icon } from "./Icons";

export interface DataColumn<T> {
  key: string;
  label: ReactNode;
  /** Encabezado en texto (exportación y accesibilidad); por defecto, label si es texto. */
  header?: string;
  type?: CellType;
  /** Valor para ordenar, buscar y exportar. */
  value: (row: T) => CellValue;
  /** Contenido de la celda (por defecto, el valor). */
  render?: (row: T) => ReactNode;
  className?: string | ((row: T) => string);
  width?: number | string;
  sortable?: boolean;
  /** No se incluye en el CSV (p. ej. columnas de acciones). */
  noExport?: boolean;
  title?: string;
}

export interface DataTableProps<T> {
  rows: T[];
  columns: DataColumn<T>[];
  rowKey: (row: T, i: number) => string;
  /** Nombre del archivo CSV (sin extensión); sin él no se muestra Exportar. */
  exportName?: string;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string;
  rowTitle?: (row: T) => string | undefined;
  initialSort?: { key: string; dir?: 1 | -1 };
  pageSize?: number;
  search?: boolean;
  searchPlaceholder?: string;
  empty?: ReactNode;
  /** Controles extra a la izquierda de la barra (filtros, acciones). */
  toolbar?: ReactNode;
  label?: string;
  className?: string;
  compact?: boolean;
  /** Fila final fija (totales); no se ordena ni pagina. */
  footer?: ReactNode;
}

const SIZES = [25, 50, 100, 0];

export function DataTable<T>(props: DataTableProps<T>) {
  const { rows, columns, rowKey, exportName, onRowClick, rowClassName, rowTitle, initialSort, search = true, empty, toolbar,
    label, className, compact, footer } = props;
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(initialSort ? { key: initialSort.key, dir: initialSort.dir ?? 1 } : null);
  const [size, setSize] = useState(props.pageSize ?? (rows.length > 200 ? 100 : 50));
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [q, sort, size]);
  const shown = useMemo(() => {
    const f = filterRows(rows, q, (r) => columns.map((c) => cellText(c.value(r))));
    const col = sort && columns.find((c) => c.key === sort.key);
    return col ? sortRows(f, col.value, col.type ?? "text", sort.dir) : f;
  }, [rows, q, sort, columns]);
  const pg = paginate(shown, page, size);
  const headerText = (c: DataColumn<T>) => c.header ?? (typeof c.label === "string" ? c.label : c.key);
  const exportCsv = () => downloadText(`${exportName}.csv`, toCsv(shown, columns.filter((c) => !c.noExport).map((c) => ({
    header: headerText(c), value: (r: T) => { const v = c.value(r); return v instanceof Date ? v.toISOString() : typeof v === "boolean" ? (v ? "sí" : "no") : v; },
  }))));
  const clickSort = (c: DataColumn<T>) => {
    if (c.sortable === false) return;
    setSort((s) => (s?.key === c.key ? (s.dir === 1 ? { key: c.key, dir: -1 } : null) : { key: c.key, dir: 1 }));
  };
  const showBar = search || !!exportName || !!toolbar;
  return (
    <div className={`dt ${compact ? "compact" : ""} ${className ?? ""}`}>
      {showBar && (
        <div className="dt-bar" role="toolbar" aria-label="Controles de la tabla">
          {toolbar}
          {search && (
            <label className="dt-search"><Icon.search />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={props.searchPlaceholder ?? "Buscar…"}
                aria-label="Buscar en la tabla" title={label ? `Buscar en ${label}` : undefined} /></label>
          )}
          <span className="dt-count muted small" aria-live="polite">
            {q ? `${shown.length} de ${rows.length}` : `${rows.length}`} {rows.length === 1 ? "fila" : "filas"}</span>
          {exportName && (
            <button type="button" className="small ghost" onClick={exportCsv} disabled={!shown.length}
              title="Exportar a CSV las filas visibles (con la búsqueda y el orden actuales)"><Icon.download /><span>Exportar</span></button>
          )}
        </div>
      )}
      {rows.length === 0 ? (empty ?? <p className="muted pad">Sin datos.</p>) : shown.length === 0 ? (
        <p className="muted pad">Ninguna fila coincide con «{q}».</p>
      ) : (
        <div className="dt-scroll">
          <table className="tbl" data-table-label={label}>
            <thead>
              <tr>
                {columns.map((c) => {
                  const on = sort?.key === c.key;
                  const can = c.sortable !== false;
                  return (
                    <th key={c.key} className={`${c.type === "num" ? "num" : ""} ${can ? "sortable" : ""} ${on ? "sorted" : ""}`}
                      style={c.width ? { width: c.width } : undefined} title={c.title}
                      aria-sort={on ? (sort.dir === 1 ? "ascending" : "descending") : can ? "none" : undefined}>
                      {can ? (
                        <button type="button" className="th-sort" onClick={() => clickSort(c)}
                          title={`Ordenar por ${headerText(c)}${c.type === "num" ? " (numérico)" : c.type === "date" ? " (fecha)" : " (A–Z)"}`}>
                          <span>{c.label}</span>
                          <span className="sort-ind" aria-hidden="true">{on ? (sort.dir === 1 ? <Icon.arrowUp /> : <Icon.arrowDown />) : <Icon.sort />}</span>
                        </button>
                      ) : c.label}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {pg.rows.map((r, i) => (
                <tr key={rowKey(r, i)} className={`${onRowClick ? "clickable" : ""} ${rowClassName?.(r) ?? ""}`}
                  onClick={onRowClick ? () => onRowClick(r) : undefined} title={rowTitle?.(r)}>
                  {columns.map((c) => (
                    <td key={c.key} className={`${c.type === "num" ? "num" : ""} ${typeof c.className === "function" ? c.className(r) : c.className ?? ""}`}>
                      {c.render ? c.render(r) : cellText(c.value(r)) || "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            {footer && <tfoot>{footer}</tfoot>}
          </table>
        </div>
      )}
      {shown.length > Math.min(...SIZES.filter(Boolean)) && (
        <div className="dt-pager" role="navigation" aria-label="Páginas de la tabla">
          <label className="small muted">Filas por página
            <select value={size} onChange={(e) => setSize(Number(e.target.value))} data-fixed-title="1">
              {SIZES.map((s) => <option key={s} value={s}>{s || "Todas"}</option>)}
            </select></label>
          <span className="spacer" />
          <button type="button" className="small ghost icon-btn" disabled={pg.page === 0} onClick={() => setPage(0)} aria-label="Primera página"><Icon.first /></button>
          <button type="button" className="small ghost icon-btn" disabled={pg.page === 0} onClick={() => setPage(pg.page - 1)} aria-label="Página anterior"><Icon.chevronLeft /></button>
          <span className="small">Página {pg.page + 1} de {pg.pages}</span>
          <button type="button" className="small ghost icon-btn" disabled={pg.page >= pg.pages - 1} onClick={() => setPage(pg.page + 1)} aria-label="Página siguiente"><Icon.chevronRight /></button>
          <button type="button" className="small ghost icon-btn" disabled={pg.page >= pg.pages - 1} onClick={() => setPage(pg.pages - 1)} aria-label="Última página"><Icon.last /></button>
        </div>
      )}
    </div>
  );
}
