# Tolerancias de validación del motor

Las pruebas `test_reference_networks.py` (referencia) y `test_roundtrip_inp.py` (ida y vuelta)
comparan **todos los nudos y tramos en todos los pasos de reporte** de Net1, Net2 y Net3
(repositorio oficial OWA-EPANET, tag `v2.3.5`).

Criterio por valor: `|a − b| ≤ atol + rtol · |referencia|`

| Variable | Unidad | atol | rtol |
|---|---|---:|---:|
| Presión | m | 1·10⁻³ | 1·10⁻⁵ |
| Cota piezométrica | m | 1·10⁻³ | 1·10⁻⁶ |
| Demanda | L/s | 1·10⁻³ | 1·10⁻⁵ |
| Caudal | L/s | 1·10⁻³ | 1·10⁻⁵ |
| Velocidad | m/s | 1·10⁻⁴ | 1·10⁻⁵ |
| Pérdida de carga del tramo | m | 1·10⁻⁴ | 1·10⁻⁴ |

## Fundamento

- **Precisión del archivo `.out`**: EPANET guarda los resultados en REAL4 (float32, ~7 cifras
  significativas). Una cota de 300 m tiene una resolución de ~3·10⁻⁵ m; un caudal de 1000 L/s,
  de ~6·10⁻⁵ L/s. Las tolerancias quedan un orden de magnitud por sobre ese ruido y dos o más
  por debajo de cualquier diferencia con relevancia de ingeniería (1 mm de presión, 1 mL/s).
- **Conversión de unidades**: las redes de ejemplo están en unidades US (GPM, pies, psi). Se
  convierten a SI con las mismas constantes internas de EPANET (`src/types.h`: `MperFT = 0.3048`,
  `PSIperFT = 0.4333`, `LPSperCFS = 28.317`, `GPMperCFS = 448.831`), de modo que la referencia y la
  API representan exactamente el mismo modelo interno.
- **Pérdida de carga**: para tuberías el motor informa la pérdida unitaria (m/km = ΔH/L·1000).
  En tramos muy cortos (Net3 tiene tramos de 0,30 m y 3,05 m) esa división amplifica por 1000/L
  la resolución float32 de las cotas, lo que produce saltos de ~10⁻³ m/km sin significado
  hidráulico. Por eso la comparación se hace sobre la **pérdida total del tramo** (m), que es la
  magnitud que el motor resuelve. Bombas y válvulas ya se informan en m.
- **Precisión de importación**: al importar, la estructura de la red se lee con los getters del
  toolkit (doble precisión). El `.inp` en SI que escribe `EN_saveinpfile` usa 4 decimales; por eso
  las curvas y los controles simples se reescriben con los valores de doble precisión del toolkit.
  Sin esta corrección, Net3 mostraba diferencias de 2·10⁻³ L/s en caudal (6·10⁻³ L/s usando el
  `.inp` SI del propio EPANET); con ella bajan a 5·10⁻⁵ L/s, nivel float32.

## Resultados obtenidos

Se regeneran en cada `make test`:

- [resultados-referencia.md](resultados-referencia.md): runepanet vs API.
- [resultados-ida-y-vuelta.md](resultados-ida-y-vuelta.md): `.inp` exportado (runepanet y API) vs original.
