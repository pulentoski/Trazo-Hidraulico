# Gestión del APR

Página completa por proyecto: **`/proyecto/:id/gestion`** (botón «Gestión» en la barra superior del editor y en cada
proyecto del inicio). Reúne los datos del Resumen con más detalle, gráficos y los registros de operación de un APR.

## Filtros e indicadores

- **Período**: mes, trimestre, año (por defecto, 12 meses hasta el último dato registrado) o personalizado. Cada
  indicador se compara con el **período anterior** de igual largo (variación en %).
- **Sector** (atributo libre de clientes y tramos configurado en el Resumen, «Sector» por defecto) y **ruta** de
  lectura: se aplican a clientes, consumo, presión por zona, pérdidas por sector y reclamos.
- Cada indicador muestra valor, variación, semáforo (bueno / regular / malo), gráfico, tabla de detalle exportable
  (Excel o CSV) y «ver en el mapa» (abre el editor, encuadra y resalta los elementos; las fugas se ven como mapa de
  calor por tramo).
- **Metas**: umbrales por indicador, derecho de agua, rango de cloro libre, consumo típico de un cliente nuevo y tope
  de la capacidad remanente. Los valores sugeridos quedan marcados **«no verificado»** hasta revisarlos.
- **Estados vacíos**: cada indicador sin datos indica qué falta y cómo cargarlo (formulario, planilla o pestaña del
  editor).

## Pestañas

| Pestaña | Contenido |
|---|---|
| Operación | presión mínima, promedio y máxima por zona y hora (medida y del modelo); nivel del estanque; horas de bomba por día; caudal del pozo medido contra autorizado; energía (kWh y kWh/m³) |
| Clientes y consumo | activos, nuevos y bajas por mes (desde las lecturas); consumo por cliente, ruta y sector; promedio por arranque; dotación real (L/hab/día con los habitantes por vivienda del módulo de demanda); mayores consumidores y tramos de consumo |
| Pérdidas | agua no contabilizada mensual por sector (producción medida contra consumo facturado); fugas por mes, material y tramo; tramos críticos y mapa de calor |
| Activos y mantenimiento | inventario por material, DN, edad y estado; plan de renovación con costos; mantenciones programadas con estado (pendiente, hecha, atrasada), calendario, atrasadas y registro de cumplimiento |
| Cumplimiento | formatos **referenciales** («no verificado», no declaran cumplimiento normativo): extracción contra derecho de agua, continuidad (cortes y horas-cliente sin servicio, con clientes afectados calculados con los cuarteles), cloro residual libre contra rango y reclamos con tiempo de respuesta |
| Planificación | proyección de demanda a 10 y 20 años contra capacidad (pozo, estanque); **capacidad remanente** por simulación; historial de factibilidades; inversiones sugeridas (diagnóstico y renovación) |
| Equipo | usuarios y rol; actividad por usuario y fecha (registro de auditoría); tareas asignadas con estado |

### Capacidad remanente

Se agregan clientes de consumo típico de a uno (en pasos que se reducen a la mitad) en el nudo de consumo con más
margen de presión, con una simulación completa de período extendido en cada paso, hasta que algún nudo baja de la
presión mínima del perfil de diseño (un nudo que ya estaba bajo el mínimo no puede bajar más de 0,5 m). Entrega el
número de clientes, el primer cuello de botella (nudo y tramo con mayor pérdida unitaria) y los clientes por nudo.
Se guarda en caché por versión del modelo.

## Registros

Energía, cloro, cortes, reclamos, mantenciones/tareas y lecturas de clientes. Cada uno tiene formulario,
**plantilla Excel**, importación de Excel o CSV con **vista previa y errores por fila** (se importan las filas
válidas), exportación a Excel/CSV y viaja en el `.trazo`. También se cargan como hojas de la planilla «Desde Excel»
(`examples/apr-demo.xlsx` trae 12 meses de ejemplo). Las lecturas usan el ID o el N° de cliente; un mismo cliente y
mes se actualiza. Una mantención periódica avanza su próxima fecha al cumplirla y queda en el registro de
cumplimiento. Las factibilidades evaluadas en el editor quedan en el historial.

## Informe mensual

«Informe mensual» genera un HTML imprimible (PDF desde el navegador) y «Informe Excel» un libro con los indicadores
de cada pestaña y sus tablas principales, con fecha de emisión, período y versión del modelo, para la directiva.

## Coordenadas en el mapa

- **Buscador**: acepta direcciones (con mapa base) y coordenadas: lat/lon decimal (`-29.942, -71.145`), grados-
  minutos-segundos (`29°56'31"S 71°08'42"W`) o UTM (`292975 6685706`, `E 292975 N 6685706 19S`, `19H …`; huso 19S por
  defecto). Centra el mapa y marca el punto.
- **Crear por coordenadas**: con las herramientas nudo, estanque, reservorio, cliente, llave, grifo y pozo, botón
  «Ingresar coordenadas».
- **Editar coordenadas**: sección «Coordenadas» del panel del elemento (lat/lon o UTM); al mover, los tramos siguen
  a sus nudos (largos recalculados), el cliente se vuelve a proyectar sobre la tubería más cercana y la llave se ubica
  en el punto más cercano de su tubería.
- **Barra inferior** con la coordenada del cursor (lat/lon y UTM) y botón para copiarla.
- Funciona igual con Google Maps, OpenStreetMap y el lienzo neutro. Conversión UTM con las series de Krüger (WGS84),
  probada contra PROJ al centímetro.
