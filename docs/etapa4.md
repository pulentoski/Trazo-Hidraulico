# Etapa 4: revisión visual, pozo y bombeo, registro de mediciones y diagnóstico

## Revisión visual (Playwright)

`make test-e2e` (fuera de `make test`) recorre la aplicación con Playwright contra la pila levantada
(`make up`, `BASIC_AUTH_ENABLED=false`): crea «APR Demo (e2e)» desde `examples/apr-demo.xlsx`; usa el menú, cada
herramienta, la importación Excel, una ortofoto (`e2e/fixtures/ortofoto.tif`), consultas, cuarteles,
factibilidad, escenarios, simulación de 24 h, gráficos, deslizador de hora, diagnóstico, mediciones, pozo y
exportaciones; toma capturas en tema claro y oscuro a 1440 y 1024 px en [docs/capturas/](capturas/), y falla
ante errores de consola o solicitudes fallidas (salvo teselas fuera de los límites de la ortofoto). La imagen
`e2e/Dockerfile` agrega el paquete Python `playwright==1.64.1` a `mcr.microsoft.com/playwright/python:v1.64.1-noble`.

Correcciones de la revisión:
- Pestañas inferiores desplazables (ya no se meten bajo el panel de propiedades).
- Controles superiores del mapa sin superposición: sin key de Google no se muestran la búsqueda de dirección
  ni los tipos de mapa; la búsqueda rápida queda a la izquierda.
- Barra superior compacta bajo 1280 px (íconos sin texto, sin el detalle de versión).
- Deslizador de hora bajo los botones de zoom (no tapa la leyenda) y aviso de mapa base cerrable.
- Formularios de la pestaña Simulación y de Consultas apilados en pantallas angostas; estado del diagnóstico
  sin mayúsculas en cada palabra; texto de detección de coordenadas actualizado.

## Pozo y bombeo (ModeloPozo.xlsx, hojas BombaPozo1 y PotenciaH)

Panel del pozo → «Datos de bombeo»: profundidad de la bomba, caudal de diseño, columna e impulsión (catálogo o
manual), llegada (cota o estanque), pérdidas singulares (5 %), rendimientos de bomba y motor, factor de potencia y
tensión. `GET /api/projects/{id}/wells/{pozo}/pump` calcula:

- pérdidas con la fórmula del proyecto (H-W de EPANET 10,667/1,852/4,871; D-W con Swamee-Jain; C-M);
- altura geométrica = cota de llegada − cota del nivel dinámico; altura manométrica = (geométrica + fricción)·(1 + %);
- potencia hidráulica γ·Q·H, al eje (/η bomba) en kW, HP (/0,7457) y C.V. (/0,7355);
- corriente trifásica I = P_eje/η_motor/(√3·V·cos φ);
- velocidad en cada tramo y advertencias (sumergencia, caudal autorizado, velocidad).

Con `conventions=planilla` (γ = 10.000 N/m³, π = 3,14, H-W 10,7/1,85/4,87, √3 = 1,732) se reproducen los valores
de la planilla: Hman 138,41 m, 12,30 kW, 24,4 A. Por defecto se usa γ = 9.810 N/m³ y π exacto: la potencia
resulta ~1,9 % menor. La planilla también calcula P/V (monofásica, sin factor de potencia), que no corresponde a
un motor trifásico; la ficha lo informa.

`report.html` entrega la ficha imprimible. `apply-curve` asigna a la bomba que sale del reservorio del pozo la
curva de 3 puntos (0; 1,33·H), (Q; H), (2·Q; 0) y al reservorio la cota del nivel dinámico.

## Registro de funcionamiento (mediciones)

Pestaña **Mediciones** (`/api/projects/{id}/measurements`): lecturas de medidor (m³ acumulados) en tramos,
bombas o pozos; presiones en nudos o clientes; niveles en estanques (m sobre el fondo) o pozos (m bajo el
terreno). Ingreso manual o por Excel/CSV con plantilla (todo o nada, errores por fila). La comparación toma el
valor del modelo a la misma hora del día y marca las diferencias que superan la tolerancia del proyecto
(caudal 10 %, presión 2 m, nivel 0,3 m; editables). Caso de prueba: las lecturas de BombaPozo1 (15,5 min) dan
15,49 L/s.

## Diagnóstico

Pestaña **Diagnóstico** (`/api/projects/{id}/diagnosis`), calculado después de cada simulación con reglas sobre
los resultados de EPANET (sin IA externa): estado general (cumple / cumple con observaciones / no cumple),
presión baja en la hora punta con el tramo causante (mayor pérdida en el camino desde la fuente), velocidades,
cuellos de botella, estado del estanque en el día (rango, rebalse, vaciado, balance diario) y funcionamiento de
las bombas. Cada afirmación enlaza a sus elementos y lleva los datos que la respaldan.

Las sugerencias se verifican simulando el modelo modificado antes de proponerlas: aumentar el DN del tramo con
más pérdida al siguiente del catálogo (paso a paso, hasta cumplir), cambiar el horario de la bomba o agregar
control por nivel. Si un cambio no basta, se informa. Se pueden aplicar con un clic.

El **informe técnico** (`/api/projects/{id}/report.html`, menú Planilla y SIG) reúne datos del proyecto,
criterios, diagnóstico, sugerencias, gráficos (estanques, nudo más desfavorable, bombas) y tablas de resultados.
