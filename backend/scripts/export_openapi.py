"""Imprime el esquema OpenAPI de la API (JSON estable, ordenado)."""
import json
import sys

sys.path.insert(0, ".")
from app.main import app  # noqa: E402

print(json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True))
