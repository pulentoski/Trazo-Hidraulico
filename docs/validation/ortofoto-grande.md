# Prueba de ortofoto grande

Fecha: 2026-11-10 23:05 · equipo: 8 CPU, 15 GB RAM · `make test-ortho-grande`

GeoTIFF sintético generado con GDAL (16700×16700 píxeles RGB, 5 cm/píxel, sin comprimir): **816 MB**.
Subida por partes a través de Caddy (con un corte simulado al 30 % y retoma desde la última parte confirmada),
procesamiento en el worker (gdalwarp → COG EPSG:3857, WEBP calidad 85 con overviews, GDAL_CACHEMAX y -wm de
256 MB) y teselas servidas por TiTiler.

| Medida | Valor |
|---|---|
| Resultado (JSON) | `{"size_mb": 816.8, "resume_at_mb": 272.0, "upload_s": 7.2, "upload_mb_s": 113.4, "parts": 51, "processing_s": 22.2, "tile_ms": {"13": 22, "16": 61, "19": 26}, "bounds": [-71.1471941, -29.9478335, -71.1383861, -29.9401626]}` |
| Duración total de la prueba | 40 s |
| Pico de memoria de procesos del worker (GDAL; anónima, muestreo 0,5 s) | 673 MB |
| Pico de memoria de procesos de la API (recepción de partes) | 150 MB |
| Pico del cgroup del worker con caché de disco (memory.peak) | 991 MB |
| Pico del cgroup de la API con caché de disco (memory.peak) | 1008 MB |
| Espacio libre tras la prueba | 116G |

La caché de disco (escritura del original y del COG) se cuenta en memory.peak, pero el kernel la libera cuando
falta memoria: el límite de memoria de cada contenedor debe cubrir la memoria de procesos con holgura.

Captura: [ortofoto-grande.png](../capturas/ortofoto-grande.png)
