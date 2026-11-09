# Resultados de la prueba de ida y vuelta (.inp → BD → .inp)

Generado automáticamente por `tests/test_roundtrip_inp.py`. Se importa el `.inp` original, se guarda en PostGIS, se exporta con GET /export.inp y se simula el archivo exportado con `runepanet` y re-importado en la API. Ambos se comparan contra `runepanet` sobre el original, en todos los pasos de reporte.

| Caso | Variable | Valores comparados | Máx. diferencia absoluta | Máx. dif. relativa (ref > 10·atol) | Uso de la tolerancia | Resultado |
|---|---|---:|---:|---:|---:|---|
| Net1 (exportado, runepanet) | Presión (m) | 275 | 7.957e-06 | 8.449e-08 | 0.4 % | cumple |
| Net1 (exportado, runepanet) | Cota piezométrica (m) | 275 | 1.523e-05 | 5.177e-08 | 1.2 % | cumple |
| Net1 (exportado, runepanet) | Demanda (L/s) | 275 | 6.051e-06 | 6.981e-08 | 0.3 % | cumple |
| Net1 (exportado, runepanet) | Caudal (L/s) | 325 | 6.051e-06 | 1.269e-07 | 0.3 % | cumple |
| Net1 (exportado, runepanet) | Velocidad (m/s) | 325 | 5.941e-08 | 1.956e-07 | 0.1 % | cumple |
| Net1 (exportado, runepanet) | Pérdida de carga del tramo (m) | 325 | 3.809e-06 | 5.901e-08 | 0.1 % | cumple |
| Net1 (re-importado, API) | Presión (m) | 275 | 7.725e-06 | 8.202e-08 | 0.4 % | cumple |
| Net1 (re-importado, API) | Cota piezométrica (m) | 275 | 1.549e-05 | 5.254e-08 | 1.2 % | cumple |
| Net1 (re-importado, API) | Caudal (L/s) | 325 | 6.532e-06 | 9.494e-07 | 0.3 % | cumple |
| Net1 (re-importado, API) | Pérdida de carga del tramo (m) | 325 | 4.264e-06 | 2.074e-04 | 0.7 % | cumple |
| Net2 (exportado, runepanet) | Presión (m) | 2016 | 1.416e-05 | 5.553e-07 | 0.9 % | cumple |
| Net2 (exportado, runepanet) | Cota piezométrica (m) | 2016 | 1.306e-05 | 1.459e-07 | 1.2 % | cumple |
| Net2 (exportado, runepanet) | Demanda (L/s) | 2016 | 4.848e-05 | 2.022e-06 | 3.9 % | cumple |
| Net2 (exportado, runepanet) | Caudal (L/s) | 2240 | 4.964e-05 | 3.952e-05 | 4.8 % | cumple |
| Net2 (exportado, runepanet) | Velocidad (m/s) | 2240 | 6.915e-07 | 3.937e-05 | 0.7 % | cumple |
| Net2 (exportado, runepanet) | Pérdida de carga del tramo (m) | 2240 | 9.418e-06 | 9.259e-03 | 9.3 % | cumple |
| Net2 (re-importado, API) | Presión (m) | 2016 | 1.395e-05 | 5.530e-07 | 0.9 % | cumple |
| Net2 (re-importado, API) | Cota piezométrica (m) | 2016 | 1.333e-05 | 1.489e-07 | 1.2 % | cumple |
| Net2 (re-importado, API) | Caudal (L/s) | 2240 | 5.009e-05 | 3.923e-05 | 4.8 % | cumple |
| Net2 (re-importado, API) | Pérdida de carga del tramo (m) | 2240 | 9.712e-06 | 9.285e-03 | 9.5 % | cumple |
| Net3 (exportado, runepanet) | Presión (m) | 2425 | 7.250e-06 | 6.036e-07 | 0.5 % | cumple |
| Net3 (exportado, runepanet) | Cota piezométrica (m) | 2425 | 6.531e-06 | 1.484e-07 | 0.6 % | cumple |
| Net3 (exportado, runepanet) | Demanda (L/s) | 2425 | 3.727e-05 | 6.940e-05 | 1.5 % | cumple |
| Net3 (exportado, runepanet) | Caudal (L/s) | 2975 | 4.779e-05 | 6.940e-05 | 3.0 % | cumple |
| Net3 (exportado, runepanet) | Velocidad (m/s) | 2975 | 9.189e-07 | 4.960e-05 | 0.9 % | cumple |
| Net3 (exportado, runepanet) | Pérdida de carga del tramo (m) | 2975 | 4.696e-06 | 3.215e-03 | 4.7 % | cumple |
| Net3 (re-importado, API) | Presión (m) | 2425 | 7.160e-06 | 1.122e-06 | 0.5 % | cumple |
| Net3 (re-importado, API) | Cota piezométrica (m) | 2425 | 7.024e-06 | 1.531e-07 | 0.7 % | cumple |
| Net3 (re-importado, API) | Caudal (L/s) | 2975 | 4.765e-05 | 6.830e-05 | 3.0 % | cumple |
| Net3 (re-importado, API) | Pérdida de carga del tramo (m) | 2975 | 6.612e-06 | 3.080e-03 | 5.6 % | cumple |
