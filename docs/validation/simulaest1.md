# SimulaEST1 — nivel horario del estanque: planilla vs EPANET

Generado por `backend/tests/test_eps_simulaest1.py`. Volumen al final de cada hora (m³).

- La planilla no limita el rebalse: desde la hora 1 supera los 200 m³ (máx. 209,5 m³).
- EPANET corta la entrada con el estanque lleno; por eso se compara también con el balance de la planilla limitado a la capacidad («planilla limitada»).
- Con el estanque lleno, EPANET mantiene cerrada la entrada hasta el siguiente paso hidráulico y el nivel baja según el consumo de ese intervalo: con paso de 60 min la diferencia puede llegar a consumo·1 h; con paso de 1 min es despreciable.
- Mientras el estanque no se llena la diferencia es menor que 0,1 m³ con ambos pasos.

| Paso | Hora | Planilla (I) | Planilla limitada | EPANET | EPANET − limitada |
|---:|---:|---:|---:|---:|---:|
| 60 min | 0 | 178.48 | 178.48 | 178.48 | +0.00 |
| 60 min | 1 | 209.47 | 200.00 | 198.47 | -1.53 |
| 60 min | 2 | 206.96 | 197.49 | 195.96 | -1.53 |
| 60 min | 3 | 204.45 | 194.99 | 193.46 | -1.53 |
| 60 min | 4 | 196.93 | 187.47 | 185.94 | -1.53 |
| 60 min | 5 | 184.40 | 174.93 | 173.40 | -1.53 |
| 60 min | 6 | 161.84 | 152.37 | 150.84 | -1.53 |
| 60 min | 7 | 160.23 | 150.77 | 149.24 | -1.53 |
| 60 min | 8 | 158.63 | 149.16 | 147.64 | -1.53 |
| 60 min | 9 | 157.03 | 147.56 | 146.04 | -1.53 |
| 60 min | 10 | 156.68 | 147.21 | 145.69 | -1.53 |
| 60 min | 11 | 158.84 | 149.37 | 147.84 | -1.53 |
| 60 min | 12 | 159.74 | 150.27 | 148.75 | -1.52 |
| 60 min | 13 | 160.64 | 151.18 | 149.65 | -1.52 |
| 60 min | 14 | 164.05 | 154.59 | 153.07 | -1.52 |
| 60 min | 15 | 172.48 | 163.01 | 161.49 | -1.52 |
| 60 min | 16 | 183.41 | 173.95 | 172.42 | -1.52 |
| 60 min | 17 | 196.85 | 187.38 | 185.86 | -1.52 |
| 60 min | 18 | 207.78 | 198.32 | 196.79 | -1.52 |
| 60 min | 19 | 177.70 | 168.23 | 166.71 | -1.52 |
| 60 min | 20 | 146.36 | 136.90 | 135.38 | -1.52 |
| 60 min | 21 | 152.28 | 142.82 | 141.30 | -1.52 |
| 60 min | 22 | 165.72 | 156.25 | 154.74 | -1.52 |
| 60 min | 23 | 189.18 | 179.72 | 178.20 | -1.52 |
| 1 min | 0 | 178.48 | 178.48 | 178.48 | +0.00 |
| 1 min | 1 | 209.47 | 200.00 | 199.93 | -0.07 |
| 1 min | 2 | 206.96 | 197.49 | 197.42 | -0.07 |
| 1 min | 3 | 204.45 | 194.99 | 194.92 | -0.07 |
| 1 min | 4 | 196.93 | 187.47 | 187.40 | -0.07 |
| 1 min | 5 | 184.40 | 174.93 | 174.86 | -0.07 |
| 1 min | 6 | 161.84 | 152.37 | 152.30 | -0.07 |
| 1 min | 7 | 160.23 | 150.77 | 150.70 | -0.07 |
| 1 min | 8 | 158.63 | 149.16 | 149.10 | -0.06 |
| 1 min | 9 | 157.03 | 147.56 | 147.50 | -0.06 |
| 1 min | 10 | 156.68 | 147.21 | 147.15 | -0.06 |
| 1 min | 11 | 158.84 | 149.37 | 149.31 | -0.06 |
| 1 min | 12 | 159.74 | 150.27 | 150.21 | -0.06 |
| 1 min | 13 | 160.64 | 151.18 | 151.12 | -0.06 |
| 1 min | 14 | 164.05 | 154.59 | 154.53 | -0.06 |
| 1 min | 15 | 172.48 | 163.01 | 162.95 | -0.06 |
| 1 min | 16 | 183.41 | 173.95 | 173.89 | -0.06 |
| 1 min | 17 | 196.85 | 187.38 | 187.32 | -0.06 |
| 1 min | 18 | 207.78 | 198.32 | 198.26 | -0.06 |
| 1 min | 19 | 177.70 | 168.23 | 168.18 | -0.06 |
| 1 min | 20 | 146.36 | 136.90 | 136.84 | -0.06 |
| 1 min | 21 | 152.28 | 142.82 | 142.76 | -0.06 |
| 1 min | 22 | 165.72 | 156.25 | 156.20 | -0.06 |
| 1 min | 23 | 189.18 | 179.72 | 179.66 | -0.06 |
