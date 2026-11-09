"""Regenera app/data/catalogo_modelopozo.json desde docs/referencias/ModeloPozo.xlsx.

Uso (en la imagen de pruebas, que incluye openpyxl):
  python scripts/extract_catalog_pozo.py /ruta/ModeloPozo.xlsx
"""
import sys

from app.data.modelopozo import JSON_PATH, read_sheet, to_json

rows = read_sheet(sys.argv[1])
JSON_PATH.write_text(to_json(rows) + "\n", encoding="utf-8")
print(f"{len(rows)} combinaciones escritas en {JSON_PATH} ({sum(1 for r in rows if r.review)} para revisión)")
