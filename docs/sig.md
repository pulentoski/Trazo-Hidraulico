# SIG de agua potable (etapa 2)

Referencia funcional: SIG RURAL 3.0 (el manual no está en `docs/referencias`; se siguió la descripción del
encargo). Cada elemento gráfico tiene atributos consultables, alimenta el modelo EPANET y se construye y
actualiza desde planillas Excel.

## Planilla

Hojas: Nudos, Tramos, Estanques, Reservorios, Válvulas, Grifos, Pozos, Bombas, Clientes (+ «Instrucciones» y,
en la exportación, «Modelo» con opciones hidráulicas y secciones del .inp para una ida y vuelta sin pérdida).
La definición de columnas está en `backend/app/sig/spec.py`.

- Fila 1 encabezados, fila 2 descripción y unidad, datos desde la fila 3. Columnas grises = calculadas.
- Coordenadas: Latitud/Longitud (WGS84) o Este/Norte UTM (huso elegido al importar; por defecto el del proyecto).
- Tramos y bombas: nudo inicial y final por ID; vértices opcionales «lat lon; lat lon» (o «E N; E N»).
- Válvulas: clase «corte» (tramo + posición o coordenadas → tramo más cercano) o «control» (PRV, FCV… entre nudos).
- Clientes: coordenadas (se conectan a la tubería y al nudo de consumo más cercanos), o el ID del nudo o tramo.
- Pozos: «Reservorio asociado»; si el reservorio no tiene carga, se usa cota del pozo − nivel dinámico.
- Diámetro interior y rugosidad vacíos se toman del catálogo (material + DN + clase).
- IDs vacíos los genera el sistema (prefijo + número, nunca repetido). Las IDs son únicas por tipo y la base lo
  garantiza con restricciones `UNIQUE (version_id, label)`.

Importación (`POST /api/projects/{id}/sig/import/preview` y `/apply`): nuevos, modificados campo por campo,
sin cambios, eliminados (opcional) y errores por fila. Aplicar es atómico y crea una versión `import`;
con `base_version` desactualizada responde 409. Proyecto nuevo: `POST /api/projects/import-excel`.

## Ortofotos

Subida por partes reanudable (la que usa el editor): `POST /api/projects/{id}/orthophotos/uploads` (nombre,
tamaño y metadatos; verifica el límite `ORTHO_MAX_MB`, el cupo de la organización y ~3 veces el tamaño libre en
disco, si no responde 507 con un mensaje claro) y `PUT …/orthophotos/{oid}/upload?offset=N` con cada parte
(binaria, 16 MB). Si la parte no empieza donde terminó la anterior responde 409 con el `offset` desde el que
seguir; `GET …/upload` dice cuánto se recibió. Al completar se valida la firma del archivo y se encola. Estados:
`uploading` (subiendo, con `upload_offset`), `uploaded` (falta ubicarla con puntos de control), `pending`,
`processing`, `ready` o `error` con su motivo. La subida directa `POST /api/projects/{id}/orthophotos` sigue
disponible para archivos chicos.

El worker (`python -m app.workers.ortho`, GDAL de Debian 3.10.3) reproyecta a EPSG:3857 con memoria acotada
(`GDAL_CACHEMAX`, `gdalwarp -wm`) y genera `cog.tif` (WEBP calidad 85 para color de 8 bits, DEFLATE en otros
casos; con overviews) en el volumen `ortho`. «Reducir resolución» (`target_res_cm`: 10, 20 o 50 cm/píxel) remuestrea
al procesar. Antes de procesar verifica de nuevo el espacio libre.

Imágenes sin referencia: **asistente de ubicación** (pestaña Capas → «Ubicar en el mapa»): la foto a la
izquierda y el mapa a la derecha (o la ortofoto existente, o el lienzo); cada punto se marca con un clic en la
foto y otro en el mapa, o escribiendo latitud/longitud o UTM Este/Norte con huso. API: `POST …/gcps` con ≥ 2 puntos
(similitud: escala, giro y posición) o ≥ 3 (afín); devuelve el error de cada punto y el RMS en metros, el punto de
mayor error y las esquinas de la imagen (vista previa con opacidad ajustable). Con `save` guarda los puntos sin
procesar (para retomar después) y con `apply` los guarda y encola el proceso. Con 2 puntos (o 3 en el ajuste
afín) la ubicación pasa exacta por ellos: el error se puede medir desde el punto siguiente.

Prueba de una ortofoto de ~800 MB (subida, procesamiento, teselas, tiempos y memoria): `make test-ortho-grande`
→ [validation/ortofoto-grande.md](validation/ortofoto-grande.md).

Teselas: Caddy reescribe `/tiles/<uuid>/<z>/<x>/<y>.png` a TiTiler fijando el archivo
(`url=/data/ortho/<uuid>/cog.tif`); el cliente nunca controla la ruta. TiTiler corre sin privilegios, sistema de
archivos de solo lectura, volumen en solo lectura y en una red interna sin salida a Internet.

`make backup` incluye `ortofotos.tar.gz`; `RESTAURAR.md` explica cómo devolverlo al volumen.

## Cuarteles de corta

`GET /api/projects/{id}/sectors`. Cada válvula de corte operativa divide su tubería; los cuarteles son las
componentes conexas resultantes. Válvulas a cerrar = las que tienen un lado dentro y otro fuera. Se informan
también los clientes que quedan sin fuente aguas abajo. Las válvulas «inoperativas» se ignoran.
Exportación: `GET …/sectors/{C-01}/export?fmt=xlsx|csv`.

## Consultas y búsqueda

`POST /api/projects/{id}/query` con `{element, where: {logic: and|or, conditions: [{field, op, value}]}}`
(los grupos pueden anidarse). Campos: los de la hoja, atributos libres y `cuartel`. Suma de metros (tramos) o
consumo (clientes). Consultas guardadas en `/queries`; exportación en `/query/export?fmt=xlsx|csv` (Excel con el
formato de la plantilla, reimportable). Búsqueda: `GET …/search?q=`.

## Grifos

`POST /api/projects/{id}/hydrants/fire`: por grifo, presión con el caudal de incendio en su nudo (mínima del
periodo) y caudal disponible a la presión residual mínima (bisección, hasta 200 L/s). Valores por defecto
16 L/s y 5 m: referenciales, no verificados.

## Exportaciones

- DXF R12 en UTM del proyecto: capas `AP_DN<diámetro>`, `AP_BOMBAS`, `VALVULAS`, `CLIENTES`, `ESTANQUES`,
  `RESERVORIOS`, `NUDOS`, `GRIFOS`, `POZOS`, `TEXTO_ID`.
- GeoPackage 1.2 (UTM del proyecto): una capa por hoja con todos los atributos, más `cuarteles`.
