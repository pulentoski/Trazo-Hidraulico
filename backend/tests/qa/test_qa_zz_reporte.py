"""Escribe el reporte de comparaciones de la batería QA (se ejecuta al final del paquete qa)."""
from tests.qa.common import QA


def test_reporte_qa(report_dir):
    assert QA.rows, "la batería QA no registró comparaciones"
    QA.write_markdown(report_dir / "resultados-qa.md", "Resultados de la batería QA hidráulica",
                      "Generado por `backend/tests/qa/` en cada `make test`. Cada caso compara la API contra "
                      "`runepanet` ejecutado sobre el mismo `.inp` (verificado por SHA-256), o el modelo "
                      "reimportado contra el original, con las [tolerancias](tolerancias.md) documentadas.")
    assert all(r.ok for r in QA.rows)
