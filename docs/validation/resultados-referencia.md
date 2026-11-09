# Resultados de la prueba de referencia (runepanet vs API)

Generado automáticamente por `tests/test_reference_networks.py` en cada `make test`.
Referencia: binario `.out` de `runepanet` (OWA-EPANET v2.3.5, SHA 444725f) sobre el `.inp` original, convertido a SI con las constantes internas de EPANET. Comparado con los resultados de la API (importación → base de datos → .inp generado → simulación) en todos los pasos de reporte. «Uso de la tolerancia» = máx(|Δ| / (atol + rtol·|ref|)); ≤ 100 % cumple.

| Caso | Variable | Valores comparados | Máx. diferencia absoluta | Máx. dif. relativa (ref > 10·atol) | Uso de la tolerancia | Resultado |
|---|---|---:|---:|---:|---:|---|
| Net1 | Presión (m) | 275 | 7.725e-06 | 8.202e-08 | 0.4 % | cumple |
| Net1 | Cota piezométrica (m) | 275 | 1.549e-05 | 5.254e-08 | 1.2 % | cumple |
| Net1 | Demanda (L/s) | 275 | 6.532e-06 | 2.072e-07 | 0.3 % | cumple |
| Net1 | Caudal (L/s) | 325 | 6.532e-06 | 9.494e-07 | 0.3 % | cumple |
| Net1 | Velocidad (m/s) | 325 | 4.999e-07 | 4.198e-05 | 0.5 % | cumple |
| Net1 | Pérdida de carga del tramo (m) | 325 | 4.264e-06 | 2.074e-04 | 0.7 % | cumple |
| Net2 | Presión (m) | 2016 | 1.395e-05 | 5.530e-07 | 0.9 % | cumple |
| Net2 | Cota piezométrica (m) | 2016 | 1.333e-05 | 1.489e-07 | 1.2 % | cumple |
| Net2 | Demanda (L/s) | 2016 | 4.850e-05 | 2.107e-05 | 3.9 % | cumple |
| Net2 | Caudal (L/s) | 2240 | 5.009e-05 | 3.923e-05 | 4.8 % | cumple |
| Net2 | Velocidad (m/s) | 2240 | 1.047e-06 | 3.961e-04 | 1.0 % | cumple |
| Net2 | Pérdida de carga del tramo (m) | 2240 | 9.712e-06 | 9.285e-03 | 9.5 % | cumple |
| Net3 | Presión (m) | 2425 | 7.160e-06 | 1.122e-06 | 0.5 % | cumple |
| Net3 | Cota piezométrica (m) | 2425 | 7.024e-06 | 1.531e-07 | 0.7 % | cumple |
| Net3 | Demanda (L/s) | 2425 | 3.752e-05 | 6.830e-05 | 1.5 % | cumple |
| Net3 | Caudal (L/s) | 2975 | 4.765e-05 | 6.830e-05 | 3.0 % | cumple |
| Net3 | Velocidad (m/s) | 2975 | 9.997e-07 | 3.080e-04 | 1.0 % | cumple |
| Net3 | Pérdida de carga del tramo (m) | 2975 | 6.612e-06 | 3.080e-03 | 5.6 % | cumple |
