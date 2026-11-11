"""Lectura y escritura de la planilla (.xlsx) y de CSV por hoja.

Formato de cada hoja: fila 1 = encabezados, fila 2 = descripción y unidad (se omite al leer), datos desde la
fila 3. Las columnas no reconocidas se conservan como atributos libres del elemento.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .spec import INSTRUCTIONS_SHEET, MODEL_SHEET, SHEET_BY_NAME, SHEETS, Col, Sheet, norm
from .tables import Row

MAX_ROWS = 50000
VALIDATION_ROWS = 5000
HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
DESC_FILL = PatternFill("solid", fgColor="DDEBF7")
COMPUTED_FILL = PatternFill("solid", fgColor="EDEDED")


class WorkbookError(ValueError):
    """El archivo no se puede leer como planilla."""


# ── Escritura ──────────────────────────────────────────────────────────────

def _desc(c: Col) -> str:
    unit = f" [{c.unit}]" if c.unit else ""
    extra = " (calculado)" if c.computed else (" (obligatorio)" if c.required else "")
    return f"{c.desc}{unit}{extra}".strip() or "—"


def _cell_value(c: Col, v: Any) -> Any:
    v = c.label_of(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _instructions(ws, zone_label: str) -> None:
    lines = [
        ("Trazo Hidráulico — planilla de datos del SIG de agua potable", True),
        ("", False),
        ("Cada hoja es un tipo de elemento. Fila 1: encabezados; fila 2: descripción y unidad (no la borre ni "
         "escriba datos en ella); datos desde la fila 3.", False),
        ("Coordenadas: Latitud/Longitud (WGS84) o Este/Norte UTM. Si ambas están, manda Latitud/Longitud. "
         f"El huso UTM se elige al importar (proyecto: {zone_label}).", False),
        ("Tramos y bombas: Nudo inicial y Nudo final por ID; vértices opcionales «lat lon; lat lon» (o «E N; E N»).",
         False),
        ("Clientes: coordenadas, o el ID del nudo (o del tramo) que los abastece. Sin nudo se conectan al más "
         "cercano.", False),
        ("Válvulas: Clase «corte» (sobre un tramo: Tramo + Posición, o coordenadas) o «control» (PRV, FCV…, "
         "entre Nudo inicial y Nudo final).", False),
        ("IDs: vacío = el sistema genera uno único. Si el ID ya existe en el proyecto, se actualizan solo las "
         "columnas presentes en la hoja.", False),
        ("Columnas adicionales (no reconocidas) se guardan como atributos libres del elemento y se exportan "
         "de vuelta.", False),
        ("Importar: el sistema muestra una vista previa (nuevos, modificados campo por campo, sin cambios, "
         "eliminados y errores por fila). Aplicar es todo o nada y crea una versión nueva del proyecto.", False),
        ("La hoja «Modelo» guarda las opciones hidráulicas y las secciones del .inp (patrones, curvas, controles); "
         "puede omitirse.", False),
        ("Las columnas grises son calculadas: se exportan pero no se importan.", False),
        ("", False),
        ("Hojas y columnas", True),
    ]
    for text, bold in lines:
        ws.append([text])
        if bold:
            ws.cell(ws.max_row, 1).font = Font(bold=True, size=12 if ws.max_row == 1 else 11)
    for s in SHEETS:
        ws.append([s.name])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        for c in s.cols:
            opts = ""
            if c.choices:
                opts = " Valores: " + ", ".join(c.choices.values()) + ("" if c.strict else " (u otro)") + "."
            ws.append(["", c.header, _desc(c) + opts])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 110
    for row in ws.iter_rows(min_row=1, max_row=13):
        row[0].alignment = Alignment(wrap_text=False)


def write_workbook(rows: dict[str, list[Row]] | None, *, zone_label: str,
                   model_rows: list[tuple[str, str]] | None = None, only: list[str] | None = None) -> bytes:
    """Plantilla (rows=None) o exportación con datos. `only` limita las hojas (exportación de una consulta)."""
    wb = Workbook()
    ws0 = wb.active
    ws0.title = INSTRUCTIONS_SHEET
    _instructions(ws0, zone_label)
    for s in SHEETS:
        if only is not None and s.key not in only:
            continue
        ws = wb.create_sheet(s.name)
        data = (rows or {}).get(s.key, [])
        attr_keys: list[str] = []
        for r in data:
            for k in r.attributes:
                if k not in attr_keys:
                    attr_keys.append(k)
        headers = [c.header for c in s.cols] + attr_keys
        ws.append(headers)
        ws.append([_desc(c) for c in s.cols] + ["Atributo libre"] * len(attr_keys))
        for i, c in enumerate(s.cols, start=1):
            h = ws.cell(1, i)
            h.font = Font(bold=True, color="FFFFFF")
            h.fill = COMPUTED_FILL if c.computed else HEADER_FILL
            if c.computed:
                h.font = Font(bold=True, color="595959")
            d = ws.cell(2, i)
            d.font = Font(italic=True, size=9, color="404040")
            d.fill = DESC_FILL
            d.alignment = Alignment(wrap_text=True, vertical="top")
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(28, len(c.header) + 6))
            if c.choices or c.kind == "bool":
                labels = list(c.choices.values()) if c.choices else ["sí", "no"]
                if labels and len(",".join(labels)) < 250:
                    dv = DataValidation(type="list", formula1='"' + ",".join(labels) + '"', allow_blank=True,
                                        errorStyle="stop" if c.strict else "warning",
                                        error="Elija un valor de la lista", errorTitle=c.header)
                    dv.add(f"{get_column_letter(i)}3:{get_column_letter(i)}{VALIDATION_ROWS}")
                    ws.add_data_validation(dv)
            elif c.kind in ("float", "int", "lat", "lon", "east", "north") and not c.computed:
                dv = DataValidation(type="decimal" if c.kind != "int" else "whole", operator="between",
                                    formula1="-1000000000", formula2="1000000000", allow_blank=True,
                                    error="Ingrese un número", errorTitle=c.header)
                dv.add(f"{get_column_letter(i)}3:{get_column_letter(i)}{VALIDATION_ROWS}")
                ws.add_data_validation(dv)
        for j, k in enumerate(attr_keys, start=len(s.cols) + 1):
            ws.cell(1, j).font = Font(bold=True)
            ws.cell(2, j).font = Font(italic=True, size=9, color="404040")
            ws.column_dimensions[get_column_letter(j)].width = max(12, len(k) + 4)
        ws.cell(1, 1).comment = Comment("Datos desde la fila 3. La fila 2 describe cada columna.", "Trazo")
        ws.row_dimensions[2].height = 45
        ws.freeze_panes = "B3"
        for r in data:
            vals = []
            for c in s.cols:
                vals.append(r.id if c.key == "id" else _cell_value(c, r.values.get(c.key)))
            vals += [r.attributes.get(k) for k in attr_keys]
            ws.append(vals)
    if model_rows is not None:
        ws = wb.create_sheet(MODEL_SHEET)
        ws.append(["Clave", "Valor"])
        ws.append(["Opciones hidráulicas (JSON) y secciones del .inp en texto", ""])
        for k, v in model_rows:
            ws.append([k, v])
        ws.column_dimensions["A"].width = 24
        ws.column_dimensions["B"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def write_csv(sheet: Sheet, rows: list[Row]) -> bytes:
    attr_keys: list[str] = []
    for r in rows:
        for k in r.attributes:
            if k not in attr_keys:
                attr_keys.append(k)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([c.header for c in sheet.cols] + attr_keys)
    for r in rows:
        vals = []
        for c in sheet.cols:
            v = r.id if c.key == "id" else _cell_value(c, r.values.get(c.key))
            vals.append("" if v is None else (str(v).replace(".", ",") if isinstance(v, float) else v))
        vals += ["" if r.attributes.get(k) is None else r.attributes.get(k) for k in attr_keys]
        w.writerow(vals)
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ── Lectura ────────────────────────────────────────────────────────────────

@dataclass
class RawRow:
    number: int  # número de fila en el archivo (1 = encabezados)
    cells: dict[str, Any]  # clave de columna → valor crudo
    attributes: dict[str, Any]


@dataclass
class RawSheet:
    sheet: Sheet
    columns: list[str]  # claves de columnas reconocidas presentes
    attr_columns: list[str]
    rows: list[RawRow] = field(default_factory=list)
    errors: list[tuple[int | None, str]] = field(default_factory=list)


def _header_map(sheet: Sheet) -> dict[str, Col]:
    out: dict[str, Col] = {}
    for c in sheet.cols:
        out[norm(c.header)] = c
        if c.unit:
            out[norm(f"{c.header} ({c.unit})")] = c
            out[norm(f"{c.header} [{c.unit}]")] = c
        out[norm(c.key.strip("_"))] = c
        for a in c.aliases:
            out[norm(a)] = c
    return out


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def parse_table(sheet: Sheet, table: list[list[Any]], *, first_row: int = 1) -> RawSheet:
    """Tabla (lista de filas) → filas crudas por clave. Omite la fila de descripción de la plantilla."""
    if not table:
        return RawSheet(sheet, [], [], errors=[(None, "La hoja está vacía (falta la fila de encabezados).")])
    hmap = _header_map(sheet)
    headers = [_clean(h) for h in table[0]]
    cols: list[tuple[int, str, bool]] = []  # (índice, clave o nombre de atributo, es_atributo)
    seen: set[str] = set()
    errors: list[tuple[int | None, str]] = []
    for i, h in enumerate(headers):
        if h is None:
            continue
        c = hmap.get(norm(h))
        key = c.key if c else str(h)
        if key in seen:
            errors.append((first_row, f"La columna «{h}» está repetida."))
            continue
        seen.add(key)
        cols.append((i, key, c is None))
    if "id" not in seen:
        errors.append((first_row, "Falta la columna ID."))
    out = RawSheet(sheet, [k for _, k, a in cols if not a and not (sheet.col(k) and sheet.col(k).computed)],
                   [k for _, k, a in cols if a], errors=errors)
    id_desc = norm(_desc(sheet.cols[0]))
    for n, raw in enumerate(table[1:], start=first_row + 1):
        vals = [_clean(v) for v in raw]
        if not any(v is not None for v in vals):
            continue
        if n == first_row + 1 and vals and vals[0] is not None and norm(vals[0]) == id_desc:
            continue  # fila de descripción de la plantilla
        if len(out.rows) >= MAX_ROWS:
            out.errors.append((n, f"La hoja supera {MAX_ROWS} filas; el resto no se leyó."))
            break
        cells: dict[str, Any] = {}
        attrs: dict[str, Any] = {}
        for i, key, is_attr in cols:
            v = vals[i] if i < len(vals) else None
            if is_attr:
                attrs[key] = v
            else:
                col = sheet.col(key)
                if col is not None and col.computed:
                    continue
                cells[key] = v
        out.rows.append(RawRow(n, cells, attrs))
    return out


# Hojas de registros del proyecto (no son elementos del modelo): mediciones y eventos de pérdidas.
# Hojas de registros del proyecto (no son elementos de la red): se importan aparte al crear el proyecto.
AUX_SHEETS = {norm(x) for x in ("Mediciones", "Pérdidas", "Energía", "Cloro", "Cortes", "Reclamos", "Mantenciones",
                                "Lecturas")}


def read_workbook(content: bytes) -> tuple[dict[str, RawSheet], list[tuple[str, str]] | None, list[str]]:
    """Lee un .xlsx: hojas reconocidas, hoja «Modelo» (si está) y avisos (hojas ignoradas)."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - cualquier error de formato
        raise WorkbookError("El archivo no es una planilla .xlsx válida.") from exc
    sheets: dict[str, RawSheet] = {}
    model: list[tuple[str, str]] | None = None
    notes: list[str] = []
    try:
        for ws in wb.worksheets:
            title = ws.title.strip()
            if norm(title) == norm(INSTRUCTIONS_SHEET):
                continue
            if norm(title) == norm(MODEL_SHEET):
                model = []
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i < 2 or not row or row[0] is None:
                        continue
                    model.append((str(row[0]).strip(), "" if len(row) < 2 or row[1] is None else str(row[1])))
                continue
            sheet = SHEET_BY_NAME.get(norm(title))
            if sheet is None and norm(title) in AUX_SHEETS:
                continue  # registros del proyecto: se importan al crear un proyecto desde la planilla
            if sheet is None:
                notes.append(f"Hoja «{title}» ignorada (no corresponde a un tipo de elemento).")
                continue
            table = []
            for row in ws.iter_rows(values_only=True):
                table.append(list(row))
                if len(table) > MAX_ROWS + 3:
                    break
            sheets[sheet.key] = parse_table(sheet, table)
    finally:
        wb.close()
    return sheets, model, notes


def read_csv(sheet: Sheet, content: bytes) -> RawSheet:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    sample = text[:4000]
    delim = ";" if sample.count(";") >= sample.count(",") and ";" in sample else ","
    table: list[list[Any]] = []
    for row in csv.reader(io.StringIO(text), delimiter=delim):
        table.append([_csv_value(v, delim) for v in row])
        if len(table) > MAX_ROWS + 3:
            break
    return parse_table(sheet, table)


def _csv_value(v: str, delim: str) -> Any:  # noqa: ARG001 - el tipo lo decide cada columna al importar
    s = v.strip()
    return s or None
