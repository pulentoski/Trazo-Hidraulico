# Análisis de `ModeloEstanque.xls`

Este documento sirve de referencia para la próxima etapa: simulación en periodo extendido con
estanque, bombeo y modulación horaria. Analiza las hojas `SimulaEST1`, `Proyecc10-30HospChamp` y
`CurvaMod`. `Hoja2` está vacía. No se cambió código.

**Cómo se leyó:** el `.xls` se convirtió a `.xlsx` con LibreOffice en un contenedor aislado. Luego se
extrajeron con `openpyxl` las fórmulas y los valores calculados de cada celda, los gráficos y los
comentarios. El libro arrastra nombres definidos rotos (`#REF!`), referencias a un libro externo
(`[1]`) y restos de configuración del Solver. Nada de eso lo usan las tres hojas analizadas.

Notación: Qmed = caudal medio, Qmd = caudal máximo diario, Qmh = caudal máximo horario.

---

## 1. `Proyecc10-30HospChamp`: proyección de población y caudales de diseño

Es una tabla anual de 2016 a 2033 (18 filas, años 0 a 17) para la «Alternativa A». Para cada año
calcula la población, el consumo, la producción y los caudales de diseño.

### Entradas

| Celda | Valor | Significado |
|---|---|---|
| `D27` | 400 | Clientes (arranques) del año base 2016 |
| `D8` | 5 hab/viv | Densidad adoptada |
| `D17` | (vacía) | Población de escuelas y jardines, se suma a la población base |
| `D16` | (vacía) | Conjunto habitacional futuro, en viviendas. Se incorpora el año 10 (2026) |
| `E27` | 160 L/hab/día | Dotación de consumo (constante en todos los años) |
| `G27:G44` | 18 % | Pérdidas |
| `I27:I44` | 1,5 | Coeficiente de máximo diario |
| `D18` / `D19` | 5 % / 3 % | Tasa de crecimiento anual: 5 % de 2017 a 2028 y 3 % desde 2029 |
| `L26` | 12 h | Horas de bombeo por día |
| `M26` | 1,5 | Coeficiente de máximo horario sobre Qmd |
| `N26` / `O26` | 15 % / 20 % | Volumen de regulación como fracción del volumen diario a Qmd |

### Fórmulas (fila de un año genérico)

| Columna | Fórmula | Resultado (2016) |
|---|---|---|
| C Población | año base: `D27·D8 + D17`; luego `C(n−1)·(1 + tasa)`; en 2026 se suma `D16·D8` | 2.000 hab |
| D Clientes | `C / D8` | 400 |
| F Consumo (m³/año) | `C · E / 1000 · días` (366 si el año es bisiesto) | 117.120 |
| H Producción (m³/año) | `F / (1 − pérdidas)` | 142.829 |
| J Qmed (L/s) | `H / días / 86400 · 1000` | 4,52 |
| K Qmd (L/s) | `J · 1,5` | 6,78 |
| L Caudal de bombeo (L/s) | `K · 24 / L26` (Qmd bombeado en 12 h) | 13,55 |
| M Qmh (L/s) | `K · M26` | 10,16 |
| N / O Regulación (m³) | `K · 86,4 · 0,15` y `K · 86,4 · 0,20` | 87,8 / 117,1 |

En 2033 resultan 4.164 habitantes, Qmd 14,10 L/s, Qmh 21,16 L/s, bombeo 28,21 L/s y
regulación de 183 a 244 m³.

### Observaciones

- **Datos ingresados que no se usan:** población actual `D6` = 7.870 hab (la base sale de
  clientes × densidad = 2.000), viviendas con arranque `D13` = 1.574 y dotación adoptada `D10` = 150
  L/hab/día (la tabla usa 160).
- **Pérdidas distintas:** aquí son 18 %; en `SimulaEST1` son 20 %.
- **Horizonte:** el nombre dice «10-30», pero la tabla llega solo a 17 años.

---

## 2. `CurvaMod`: curva de modulación horaria

Son 24 coeficientes horarios (horas 0 a 23) que multiplican un consumo de referencia
(`D2` = 17 m³/h). La hoja calcula el consumo de cada hora, su promedio, el máximo y el mínimo, y
tiene dos gráficos «Curva de Modulación — Comportamiento horario del cliente».

| Hora | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Coef. | 0,3 | 0,2 | 0,1 | 0,1 | 0,3 | 0,5 | 0,9 | 1,5 | **1,6** | 1,5 | 1,45 | 1,35 |

| Hora | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Coef. | 1,4 | 1,4 | 1,3 | 1,1 | 1,0 | 0,9 | 1,0 | 1,2 | 1,25 | 1,2 | 0,9 | 0,5 |

- **Promedio de los coeficientes: 0,956, no 1** (suman 22,95). Un día modulado consume un 4,4 %
  menos que 24 horas al caudal de referencia.
- **Diferencias con la curva de `SimulaEST1`:** esa curva usa 1,5 en la hora 8 (aquí 1,6) y su
  promedio es 0,952.
- **Valores sueltos sin relación con la tabla:** `D1` = 15 L/s (que equivale a 54 m³/h, no a los 17
  m³/h de `D2`), `E2` = 6·1,25 e `I25` = 90/3,6.

---

## 3. `SimulaEST1`: balance horario del estanque con bombeo

Simula 24 horas de un estanque alimentado por una bomba de caudal fijo que se puede encender o
apagar hora a hora. El consumo sigue la curva de modulación. Según la nota de la celda `B38`, la idea
es modificar la columna F (horas de bombeo) y observar cómo se comporta el estanque.

### Entradas

| Celda | Valor | Significado |
|---|---|---|
| `N5`, `N2`, `O5` | 400 arranques, 5 hab/arranque, 160 L/hab/día | Población y dotación; replica la fila 2016 de la proyección |
| `Q5` | 20 % | Pérdidas |
| `S5` | 1,5 | Coeficiente de máximo diario |
| `V4` | 1,5 | Coeficiente de máximo horario |
| `E4` | 10 L/s (36 m³/h) | Caudal de la bomba |
| `J5` | 200 m³ | Volumen del estanque |
| `J6` | 3,5 m | Altura útil del estanque |
| `I8` | 150 m³ | Volumen inicial (según el comentario de la celda) |
| `C9:C32` | modulación | Coeficiente de consumo por hora |
| `F9:F32` | 36 o vacío | Bomba encendida (36 m³/h) o apagada en esa hora |

### Fórmulas

- **Caudales de referencia (fila 5):**
  - Consumo anual: `P5 = O5·N2·N5·366/1000` = 117.120 m³/año.
  - Producción: `R5 = P5/(1−Q5)` = 146.400 m³/año.
  - Qmed: `T5 = R5/365/86400·1000` = 4,64 L/s.
  - Qmd: `U5 = T5·S5` = 6,96 L/s.
  - Qmh: `V5 = U5·V4` = 10,45 L/s.
  - Qmd en m³ por día y por hora: `D2 = R6 = U5·86,4` = 601,6 m³/día, y `D5 = D2/24` = 25,07 m³/h.
- **Indicadores de bombeo:**
  - Relación bomba/consumo: `I4 = E4/D4` = 1,44.
  - Capacidad óptima de la bomba: `L4 = D4·24/12` = 13,93 L/s (Qmd bombeado en 12 h).
- **Balance horario (filas 9 a 32, Δt = 1 h):**
  - Consumo de la hora: `D = C · D5`.
  - Volumen en el estanque: `I(h) = I(h−1) + F(h) − D(h)`.
  - Nivel: `J(h) = I(h) · J6 / J5`, es decir volumen / área, con área = 200/3,5 = 57,14 m².
  - Columnas acumuladas: consumo E, bombeo G y diferencia `H = G − E` (curva de masas).
- **Resumen (filas 33 a 35):**
  - Totales: consumo 572,8 m³ y bombeo 612 m³ en 17 horas encendida.
  - Máximo y mínimo de las columnas H, I y J.
  - **Volumen de regulación por curva de masas:** `H35 = max(H) − min(H)` = 63,1 m³.
- **Gráfico:** consumo y bombeo acumulados por hora.

### Resultados del ejemplo

- El bombeo está apagado de 2:00 a 7:00 y de 19:00 a 21:00.
- El volumen va de 146,4 a **209,5 m³** y el nivel de 2,56 a **3,67 m**. Ambos superan la capacidad
  (200 m³ y 3,5 m): **la planilla no limita el rebalse ni el vaciado**.
- Se bombea más de lo que se consume (+39,2 m³/día). El ciclo no es estacionario y en varios días el
  estanque acumularía agua sin límite.

### Observaciones

- `P5` usa 366 días y `T5` divide por 365, lo que sobrestima los caudales en 0,27 %. La proyección
  usa el mismo número de días en ambas fórmulas.
- El consumo horario es coeficiente × Qmd, con coeficientes de promedio 0,952. El volumen diario
  consumido (572,8 m³) es menor que Qmd·24 (601,6 m³).

---

## 4. Correspondencia con EPANET (periodo extendido)

### 4.1 Tiempos — `[TIMES]`

```
DURATION            24:00     ; 72:00 o más para ver si el ciclo se repite
HYDRAULIC TIMESTEP  1:00      ; 0:15 da niveles más finos; la planilla usa pasos de 1 h
PATTERN TIMESTEP    1:00
REPORT TIMESTEP     1:00
START CLOCKTIME     0:00
```

La fila de la hora *h* de la planilla da el volumen al **final** de esa hora. EPANET informa al
inicio de cada paso, así que el nivel del estanque en t = h+1 corresponde a `I(h)`.

### 4.2 Modulación — `[PATTERNS]`

```
[PATTERNS]
 MOD   0.3 0.2 0.1 0.1 0.3 0.5 0.9 1.5 1.6 1.5 1.45 1.35
 MOD   1.4 1.4 1.3 1.1 1.0 0.9 1.0 1.2 1.25 1.2 0.9 0.5
```

- La demanda base de cada nudo es su parte del **Qmd en L/s**. La planilla trata todo el consumo
  como un solo punto; en la red hay que repartirlo, por ejemplo por clientes o viviendas de cada
  nudo, y el patrón es común a todos.
- **Hay que decidir qué hacer con el promedio distinto de 1:**
  - Usar los coeficientes tal cual reproduce la planilla (el volumen diario queda 4–5 % bajo
    Qmd·24).
  - Normalizarlos (dividir por el promedio) conserva el volumen diario de Qmd, pero eleva el
    máximo horario.
  - La interfaz debería mostrar el promedio del patrón y advertir cuando no es 1.
- **El máximo horario del patrón debe ser coherente con el coeficiente de diseño:** la curva tiene
  1,6 (o 1,5 en `SimulaEST1`) frente a Qmh = 1,5·Qmd. Conviene validarlo contra el perfil de
  criterios.
- **Pérdidas:** la planilla las suma a la producción (consumo/(1−p)). En EPANET se incluyen en la
  demanda base (factor 1/(1−p)) o se modelan como fuga con `[EMITTERS]` o `[LEAKAGE]` (2.3).

### 4.3 Estanque — `[TANKS]`

| Campo EPANET | Desde la planilla | Valor del ejemplo |
|---|---|---|
| Cota de fondo | No existe en la planilla; viene del proyecto | — |
| Nivel inicial | `I8 · J6 / J5` | 150 × 3,5 / 200 = **2,625 m** |
| Nivel mínimo | No existe (la planilla permite llegar a 0) | 0 m, o la reserva de incendio si se define |
| Nivel máximo | `J6` | **3,5 m** |
| Diámetro | estanque cilíndrico equivalente: √(4·J5 / (π·J6)) | **8,53 m** (área 57,14 m²) |
| Volumen mínimo | — | 0 |
| Curva de volumen | solo si el estanque no es prismático | — |

**Diferencia esperada:** al llenarse el estanque, EPANET corta la entrada (salvo que se permita el
rebalse con `can_overflow`) y deja de entregar al vaciarse. Por eso no reproducirá los 209,5 m³ de
la planilla, sino que se queda en 200 m³. Mientras el nivel esté dentro de sus límites, el balance
es el mismo: V(t+Δt) = V(t) + (Q_entra − Q_sale)·Δt.

### 4.4 Bombeo — fuente, bomba y horario (`[PUMPS]`, `[CONTROLS]`, `[RULES]`)

**Fuente de caudal fijo (reproduce la planilla, 10 L/s), con tres opciones:**

- Reservorio (pozo) → válvula FCV con consigna 10 L/s → estanque.
- Una bomba cuya curva entregue ~10 L/s en el punto de operación.
- Un nudo junto al estanque con demanda negativa −10 L/s y un patrón 0/1.

**Caso real (próxima etapa):** pozo como reservorio con la cota del nivel dinámico, y una bomba con
curva H-Q de 3 puntos en `[CURVES]`. El caudal pasa a depender de la altura y del nivel del
estanque. El objetivo de diseño es Qb = Qmd·24/N horas (columna L de la proyección).

**Horario de la columna F (apagada de 2:00 a 7:00 y de 19:00 a 21:00):**

```
[CONTROLS]
 LINK B1 CLOSED AT CLOCKTIME 2:00
 LINK B1 OPEN   AT CLOCKTIME 7:00
 LINK B1 CLOSED AT CLOCKTIME 19:00
 LINK B1 OPEN   AT CLOCKTIME 21:00
```

El horario también puede expresarse como un patrón de velocidad de la bomba (`PATTERN` 0/1 en
`[PUMPS]`). Es la forma más directa de pasar «columna F hora a hora» a EPANET.

**Mejora sobre la planilla:** controles por nivel, que evitan el rebalse que la planilla no detecta.

```
 LINK B1 CLOSED IF NODE E1 ABOVE 3.3
 LINK B1 OPEN   IF NODE E1 BELOW 1.5
```

Para combinar horario y nivel (por ejemplo, horas punta eléctricas) se usan `[RULES]`.

### 4.5 Proyección → escenarios de diseño

La proyección no es una entrada directa de EPANET: entrega los caudales de un **año de diseño**.

- Qmd del año elegido → demandas base repartidas en la red (más pérdidas).
- Qmh, igual a Qmd·1,5 o al máximo del patrón → revisión de presiones mínimas a la hora punta.
- Qb = Qmd·24/12 → selección de la bomba.
- Volumen de regulación → dimensionamiento del estanque. La planilla lo calcula de dos formas:
  porcentaje del volumen diario a Qmd (15–20 %, columnas N y O) y curva de masas con el horario de
  bombeo real (63,1 m³ en `SimulaEST1`). Ambas pueden convertirse en criterios del perfil
  (volumen del estanque ≥ volumen de regulación).

### 4.6 Cómo validar la próxima etapa contra la planilla

1. Armar la red mínima: reservorio, FCV de 10 L/s, estanque de 8,53 m de diámetro con nivel inicial
   2,625 m, una tubería corta y un nudo con demanda Qmd = 6,96 L/s y el patrón de `SimulaEST1`.
2. Simular 24 h con pasos de 1 h y el horario de la columna F.
3. Comparar el volumen del estanque, área × nivel, con `I9:I32` mientras el nivel esté dentro de 0 y
   3,5 m (diferencia esperada < 0,1 m³). En las horas en que la planilla supera 200 m³, verificar
   que EPANET corta la entrada.
4. Comparar el consumo acumulado (columna E) y el volumen de regulación (`H35` = 63,1 m³).

## 5. Datos a confirmar antes de implementar

- Dotación de diseño: 150 (`D10`) o 160 L/hab/día (la que usan ambas hojas).
- Pérdidas: 18 % (proyección) o 20 % (simulación).
- Población base: 7.870 habitantes (`D6`) o 2.000 (400 clientes × 5).
- Curva de modulación oficial (hora 8: 1,5 o 1,6) y si se normaliza a promedio 1.
- Cota de fondo del estanque, nivel mínimo o reserva de incendio, y si se permite rebalse.
- Curva H-Q de la bomba y nivel dinámico del pozo. `docs/referencias/ModeloPozo.xlsx` no se
  analizó porque no se pidió, pero probablemente contiene esos datos.
