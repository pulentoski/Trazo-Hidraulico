# Etapa 3: formato .trazo, demanda sanitaria, simulación de 24 h y gráficos

Referencia: [docs/referencias/analisis-planillas.md](referencias/analisis-planillas.md) (planilla ModeloEstanque).

## Formato .trazo

`GET /api/projects/{id}/export.trazo` entrega un zip con:

- `modelo.inp`: el .inp completo (coordenadas y vértices en el UTM del proyecto, [TAGS] y [LABELS]); se abre
  en EPANET.
- `trazo.json` (`format: "trazo"`, `format_version: 1`): proyecto (nombre, SRID, perfil, parámetros de diseño,
  proyección de demanda), opciones y secciones del modelo, escenarios de llaves, red completa en GeoJSON
  (clientes, llaves, grifos, pozos, atributos de gestión y libres, origen de las cotas, vértices), consultas
  guardadas, cuarteles de corta (informativo), eventos de pérdidas, mediciones (`measurements`: lecturas de medidor,
  presiones y niveles; opcional al importar), registros de Gestión, configuración del Resumen (rangos de presión,
  margen del área operacional, vida útil, precios, sectores y medidores) y las ortofotos (nombre, fecha, fuente,
  georreferencia, archivo world, puntos de control, opacidad, visibilidad y resolución pedida).
- Con `?ortofotos=true` (menú «Exportar .trazo con ortofotos») también los archivos originales en
  `ortofotos/<id>/` (sin recomprimir); el zip se arma en disco y puede pesar lo mismo que las imágenes.

`POST /api/projects/import-trazo` crea un proyecto desde el JSON (sin pérdida: las pruebas exportan, importan y
vuelven a exportar con el mismo contenido, el mismo .inp, los mismos eventos y configuración, y las ortofotos con
los mismos datos y archivos idénticos, que se vuelven a procesar). Las ortofotos sin archivo en el .trazo quedan
informadas en las notas. Admite hasta `ORTHO_MAX_MB`. Si falta el JSON, importa el .inp.

## Importación .inp

- Se conservan [VERTICES], [TAGS] (atributo reservado `__tag`, se vuelve a escribir en [TAGS]) y [LABELS]
  (rótulos en EPSG:4326, se reproyectan al exportar).
- Coordenadas: UTM (rango métrico), lat/lon (rango geográfico y distancias coherentes con los largos de las
  tuberías) o locales (se escalan alrededor del centro configurado). Ejemplo:
  `examples/networks/etiquetas-latlon.inp`.

## Demanda sanitaria

Pestaña **Demanda** (`/api/projects/{id}/demand/projection`). Entradas: población o arranques × habitantes por
vivienda, población adicional, tramos de tasa de crecimiento, incorporaciones de viviendas, horizonte,
dotación, pérdidas, coeficientes de día y hora de máximo consumo, horas de bombeo y % de regulación. La tabla
anual (población, clientes, consumo, producción, Qmedio, QMD, QMH, caudal de bombeo y volumen de regulación)
reproduce la hoja «Proyecc10-30HospChamp» (probado en 2016, 2017, 2026 y 2033). Se exporta a Excel.
Todo queda **no verificado**; los valores por defecto salen de los parámetros de diseño del proyecto.

Escenarios de demanda (base, año actual, año horizonte): crean una versión con `DEMAND MULTIPLIER` = población
del año / población del año que representa el modelo (opcionalmente × coeficiente de día máximo). Escalan
nudos y clientes por igual.

## Simulación de 24 h

- Pestaña **Simulación**: período extendido (duración, paso hidráulico, de patrón y de reporte) y curvas de
  modulación de 24 coeficientes con promedio, advertencia si no es 1 (`W_PATTERN_MEAN`) y botón «Normalizar».
  La curva por defecto (`OPTIONS PATTERN`) se crea desde CurvaMod normalizada.
- Estanques: cota de fondo, niveles, diámetro o volumen útil (calcula el diámetro equivalente).
- Bombas y válvulas de control: horario por hora (controles `AT CLOCKTIME`), control por nivel de estanque
  (`IF NODE … BELOW/ABOVE`) o ambos (reglas); curva H-Q de 1 o 3 puntos (`[CURVES]`). En la planilla, columnas
  «Curva H-Q», «Horario» («0-1; 7-16; 22-23») y «Control: estanque / Enciende bajo / Apaga sobre» de Bombas.
- Alertas: estanque lleno (rebalse) o vacío/bajo el mínimo — se detecta también cuando ocurre entre dos
  reportes —, bomba fuera de su curva (no alcanza la altura o supera el caudal máximo) y presión bajo el mínimo
  en la hora punta.
- Referencia SimulaEST1 (`backend/tests/test_eps_simulaest1.py`, detalle en
  [validation/simulaest1.md](validation/simulaest1.md)): 200 m³, 10 L/s con el horario de la columna F. Antes del
  primer rebalse coincide con la planilla (< 0,1 m³). La planilla no limita el rebalse (209,5 m³); EPANET corta
  la entrada, así que se compara con el balance limitado a la capacidad. Con paso de 60 min, tras llenarse
  EPANET mantiene cerrada la entrada hasta el paso siguiente y el nivel baja hasta consumo·paso; con 1 min la
  diferencia es despreciable.

## Gráficos

Pestaña **Gráficos** (SVG propio, sin dependencias, tema claro y oscuro): nivel y volumen del estanque,
presión de un nudo o cliente con la línea del mínimo, caudal de un tramo o bomba, curva de masas (consumo
contra bombeo, con el volumen de regulación) y perfil de presiones en la ruta más corta entre dos nudos.
Cada gráfico se exporta a PNG y sus datos a CSV. El deslizador de hora sobre el mapa actualiza colores y
etiquetas.

## Factibilidad

Si aumentar el DN del cuello de botella hace factible al cliente, el botón «Agregar cliente y aplicar mejora»
agrega el cliente y cambia ese tramo (ambas partes, si es el que se dividió) al DN sugerido del catálogo.

## Demo

`examples/apr-demo.xlsx` («APR Demo»): curva MOD (CurvaMod normalizada), bomba con curva de 3 puntos y horario
de 14 h, 24 h con paso hidráulico de 5 min. El nivel del estanque varía entre ~1,4 y 4,0 m.
