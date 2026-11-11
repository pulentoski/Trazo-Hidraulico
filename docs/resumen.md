# Panel general del proyecto («Resumen») y paneles plegables

## Paneles plegables

- **Panel derecho**: cada bloque (Opciones hidráulicas, Criterios de diseño, Cota, Tubería, Resultados, Gestión…) es
  una sección plegable con flecha y animación corta. Por defecto queda abierta solo la sección más usada del panel
  (Opciones hidráulicas en el proyecto; Resultados en un elemento simulado, o su bloque principal si aún no hay
  resultados). Lo que cada usuario abre o cierra se recuerda en el navegador (`localStorage`, clave
  `trazo.sections.<usuario>`; sin almacenamiento disponible rige solo para la sesión). «Expandir todo / Contraer
  todo» actúa sobre las secciones visibles.
- **Barra de herramientas** («‹ Plegar»): se reduce a íconos. **Panel inferior** («Plegar»): queda solo la fila de
  pestañas. Ambos estados se recuerdan.
- Los selectores del panel derecho ocupan todo el ancho (etiqueta arriba) y todos muestran la opción completa como
  tooltip.

## Resumen

Primera pestaña del panel inferior al abrir un proyecto; también con el botón **Resumen** de la barra superior.
Usa la última simulación de la versión guardada (o la de un escenario de llaves) en la hora elegida; por defecto la
**hora punta** (mayor demanda total). Cada número subrayado abre su lista (a la derecha) y resalta y encuadra los
elementos en el mapa; cada ID de la lista selecciona el elemento.

| Bloque | Contenido |
|---|---|
| Clientes | total, activos, proyectados, N° de arranques (puntos de conexión distintos), por ruta y por sector |
| Red | km por material, diámetro, estado y antigüedad; válvulas, grifos, estanques y pozos |
| Clientes por tubería | tramos con más clientes (tramo del arranque o, si falta, la tubería más cercana de su nudo) |
| Presiones | mínima, máxima y promedio; nudos y clientes bajo la mínima, nudos sobre la máxima, hora más crítica |
| Zonas por presión | Voronoi de los nudos de consumo recortado al área operacional, por rango (< 15, 15–30, 30–50, 50–70, > 70 m.c.a., configurable): superficie y clientes por rango; capa en el mapa y GeoJSON |
| Clientes sobre cota | cota de terreno (del cliente o de su nudo) + presión mínima > cota piezométrica del nudo en la hora crítica; déficit en m |
| Mayores consumidores | top 10 o 20 con consumo y % del total, resaltables en el mapa |
| Consumo | diario y mensual de clientes activos, por sector y ruta; proyección a 10 y 20 años con el crecimiento del módulo de demanda |
| Área operacional | unión de red, nudos y clientes con un margen (50 m por defecto); km², capa y GeoJSON |
| Pérdidas y filtraciones | registro por tramo (fuga, rotura, reparación; caudal estimado; observación), manual o planilla «Pérdidas»; tramos con más eventos; agua no contabilizada por sector |
| Mantenimiento a futuro | vida útil por material (sugerida, «no verificado», editable), año de vencimiento por tramo, km que vencen en 5, 10 y 20 años, vencidos y en mal estado, plan de renovación por año con costo (precio por metro editable por material y DN) |
| Estanque y pozo | autonomía del estanque (volumen útil / consumo medio), horas de bomba al día, volumen bombeado contra el autorizado |
| Alertas | presión fuera de rango, clientes sobre cota, pozo sobre el caudal autorizado, estanque en nivel mínimo, tramos vencidos o en mal estado y criterios del motor; «ir» selecciona el elemento |

**Agua no contabilizada** = (producción − consumo facturado) / producción. La producción sale de lecturas acumuladas
de medidor (pestaña Mediciones, medición «medidor»): el medidor de un pozo abastece el sector «Total» y un
macromedidor en un tramo, el sector indicado en el atributo «Sector» del tramo (configurable). El sector de un
cliente es su atributo libre «Sector» (o el configurado). Sin datos, el bloque muestra «sin datos» y cómo cargarlos.

**Configurar…** edita los rangos de presión, el margen del área, el top de consumidores, el atributo de sector,
los medidores de producción, la vida útil y los precios. **PDF (imprimible)** abre el resumen en HTML (Imprimir →
Guardar como PDF) y **Excel** lo descarga con una hoja por bloque.

API: `GET /api/projects/{id}/summary?scenario=&period=&version=`, `summary.xlsx`, `summary.html`,
`summary/area.geojson`, `summary/zones.geojson`, `summary/settings` (GET/PUT/DELETE) y `leaks` (GET/POST,
`leaks/import`, `leaks/delete`, `leaks/template.xlsx`).

## Datos de ejemplo («APR Demo»)

`examples/apr-demo.xlsx` (regenerable con `backend/scripts/make_apr_demo.py`) incluye sectores «Alto» y «Bajo»,
dos clientes proyectados, un cliente en una loma (C-025, sobre cota), un consumidor industrial, tramos vencidos y
por vencer, la hoja **Mediciones** (lecturas diarias de octubre del pozo PZ-1 y del macromedidor de P-12) y la hoja
**Pérdidas** (8 eventos). Al crear un proyecto desde la planilla, esas hojas se registran en el proyecto.

Pruebas: `backend/tests/test_resumen.py` (cálculos con resultados conocidos y el resumen de la demostración) y
`make test-e2e` (capturas `resumen-*`, `paneles-plegados-*` y `paneles-desplegados-*` en tema claro y oscuro).
