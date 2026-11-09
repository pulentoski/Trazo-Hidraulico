# Resultados de la batería QA hidráulica

Generado por `backend/tests/qa/` en cada `make test`. Cada caso compara la API contra `runepanet` ejecutado sobre el mismo `.inp` (verificado por SHA-256), o el modelo reimportado contra el original, con las [tolerancias](tolerancias.md) documentadas.

| Caso | Variable | Valores comparados | Máx. diferencia absoluta | Máx. dif. relativa (ref > 10·atol) | Uso de la tolerancia | Resultado |
|---|---|---:|---:|---:|---:|---|
| 1 · red base (2 L/s, DN 90) | Presión (m) | 2 | 2.214e-07 | 4.859e-08 | 0.0 % | cumple |
| 1 · red base (2 L/s, DN 90) | Cota piezométrica (m) | 2 | 2.214e-07 | 4.222e-09 | 0.0 % | cumple |
| 1 · red base (2 L/s, DN 90) | Demanda (L/s) | 2 | 1.192e-07 | 5.960e-08 | 0.0 % | cumple |
| 1 · red base (2 L/s, DN 90) | Caudal (L/s) | 1 | 1.192e-07 | 5.960e-08 | 0.0 % | cumple |
| 1 · red base (2 L/s, DN 90) | Velocidad (m/s) | 1 | 2.279e-07 | 6.165e-07 | 0.2 % | cumple |
| 1 · red base (2 L/s, DN 90) | Pérdida de carga del tramo (m) | 1 | 1.025e-08 | 1.859e-08 | 0.0 % | cumple |
| 2 · 10 L/s, DN 90 | Presión (m) | 2 | 4.357e-07 | 4.859e-08 | 0.0 % | cumple |
| 2 · 10 L/s, DN 90 | Cota piezométrica (m) | 2 | 3.430e-07 | 8.142e-09 | 0.0 % | cumple |
| 2 · 10 L/s, DN 90 | Demanda (L/s) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 2 · 10 L/s, DN 90 | Caudal (L/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 2 · 10 L/s, DN 90 | Velocidad (m/s) | 1 | 1.692e-07 | 9.157e-08 | 0.1 % | cumple |
| 2 · 10 L/s, DN 90 | Pérdida de carga del tramo (m) | 1 | 1.469e-07 | 1.351e-08 | 0.0 % | cumple |
| 3 · 10 L/s, DN 160 | Presión (m) | 2 | 2.336e-07 | 4.859e-08 | 0.0 % | cumple |
| 3 · 10 L/s, DN 160 | Cota piezométrica (m) | 2 | 2.336e-07 | 4.464e-09 | 0.0 % | cumple |
| 3 · 10 L/s, DN 160 | Demanda (L/s) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 3 · 10 L/s, DN 160 | Caudal (L/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 3 · 10 L/s, DN 160 | Velocidad (m/s) | 1 | 4.364e-07 | 7.467e-07 | 0.4 % | cumple |
| 3 · 10 L/s, DN 160 | Pérdida de carga del tramo (m) | 1 | 9.675e-08 | 1.470e-07 | 0.1 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Presión (m) | 2 | 1.458e-07 | 4.859e-08 | 0.0 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Cota piezométrica (m) | 2 | 1.853e-07 | 3.496e-09 | 0.0 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Demanda (L/s) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Caudal (L/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Velocidad (m/s) | 1 | 1.692e-07 | 9.157e-08 | 0.1 % | cumple |
| 4 · DDA, 5500 m, 10 L/s | Pérdida de carga del tramo (m) | 1 | 6.539e-07 | 3.282e-09 | 0.0 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Presión (m) | 2 | 4.929e-07 | 2.452e-07 | 0.0 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Cota piezométrica (m) | 2 | 2.545e-07 | 1.156e-08 | 0.0 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Demanda (L/s) | 2 | 2.629e-07 | 7.182e-08 | 0.0 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Caudal (L/s) | 1 | 2.629e-07 | 7.182e-08 | 0.0 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Velocidad (m/s) | 1 | 3.047e-07 | 4.504e-07 | 0.3 % | cumple |
| 5 · PDA, 5500 m, 10 L/s | Pérdida de carga del tramo (m) | 1 | 2.370e-06 | 7.649e-08 | 0.1 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Presión (m) | 2 | 2.919e-07 | 4.859e-08 | 0.0 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Cota piezométrica (m) | 2 | 3.845e-07 | 9.032e-09 | 0.0 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Demanda (L/s) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Caudal (L/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Velocidad (m/s) | 1 | 1.692e-07 | 9.157e-08 | 0.1 % | cumple |
| 6 · Darcy-Weisbach, 10 L/s, DN 90 | Pérdida de carga del tramo (m) | 1 | 6.372e-08 | 6.111e-09 | 0.0 % | cumple |
| 12 · largo manual 450 m | Presión (m) | 2 | 4.248e-07 | 4.859e-08 | 0.0 % | cumple |
| 12 · largo manual 450 m | Cota piezométrica (m) | 2 | 4.248e-07 | 8.142e-09 | 0.0 % | cumple |
| 12 · largo manual 450 m | Demanda (L/s) | 2 | 1.192e-07 | 5.960e-08 | 0.0 % | cumple |
| 12 · largo manual 450 m | Caudal (L/s) | 1 | 1.192e-07 | 5.960e-08 | 0.0 % | cumple |
| 12 · largo manual 450 m | Velocidad (m/s) | 1 | 2.279e-07 | 6.165e-07 | 0.2 % | cumple |
| 12 · largo manual 450 m | Pérdida de carga del tramo (m) | 1 | 4.132e-08 | 4.993e-08 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Presión (m) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Cota piezométrica (m) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Demanda (L/s) | 2 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Caudal (L/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Velocidad (m/s) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
| 10 · ida y vuelta .inp | Pérdida de carga del tramo (m) | 1 | 0.000e+00 | 0.000e+00 | 0.0 % | cumple |
