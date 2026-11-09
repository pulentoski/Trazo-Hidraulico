# Catálogo ModeloPozo: filas para revisión

Fuente: `docs/referencias/ModeloPozo.xlsx`, hoja «D=Interiores». 62 combinaciones material × clase × DN con diámetro interior; 24 marcadas para revisión. Se cargan igual (no verificadas); este reporte se regenera en cada `make test`.

| Material | Clase | DN | Interior (mm) | Celda | Fórmula | Observación |
|---|---|---:|---:|---|---|---|
| Acero | PN10 | 40 | 40 | D5 |  | interior igual al DN: confirmar que es el diámetro interior real |
| PEAD | PN16 | 40 | 73.6 | M5 | `=90-8.2-8.2` | calculado sobre 90 mm, no sobre el DN 40; interior ≥ DN en un plástico (DN = diámetro exterior): 73.6 mm |
| Acero | PN10 | 50 | 50 | D6 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 65 | 65 | D8 |  | interior igual al DN: confirmar que es el diámetro interior real |
| PEAD | PN16 | 65 | 73.6 | M8 | `=90-8.2-8.2` | calculado sobre 90 mm, no sobre el DN 65; interior ≥ DN en un plástico (DN = diámetro exterior): 73.6 mm |
| AC | PN10 | 75 | 75 | C9 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 80 | 80 | D10 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 90 | 90 | C11 |  | interior igual al DN: confirmar que es el diámetro interior real |
| PVC | PN10 | 90 | 75 | H11 |  | difiere más de 6 % del típico SDR 26 (83.1 mm) |
| AC | PN10 | 100 | 100 | C12 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 100 | 100 | D12 |  | interior igual al DN: confirmar que es el diámetro interior real |
| PVC | PN10 | 100 | 81.4 | H12 |  | difiere más de 6 % del típico SDR 26 (92.3 mm) |
| AC | PN10 | 110 | 110 | C13 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 125 | 125 | C14 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 125 | 125 | D14 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 150 | 150 | C16 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 150 | 150 | D16 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 200 | 200 | C18 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 200 | 200 | D18 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 250 | 250 | C19 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 300 | 300 | C22 |  | interior igual al DN: confirmar que es el diámetro interior real |
| Acero | PN10 | 300 | 300 | D22 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 350 | 350 | C24 |  | interior igual al DN: confirmar que es el diámetro interior real |
| AC | PN10 | 400 | 400 | C26 |  | interior igual al DN: confirmar que es el diámetro interior real |

## Combinaciones disponibles

| Material y clase | DN disponibles |
|---|---:|
| AC PN10 | 11 |
| Acero PN10 | 12 |
| FFD PN10 | 7 |
| HA PN10 | 1 |
| PEAD PN10 | 15 |
| PEAD PN16 | 3 |
| PVC PN10 | 13 |
