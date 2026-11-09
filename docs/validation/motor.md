# Motor hidráulico verificado

| Componente | Valor |
|---|---|
| Motor | OWA-EPANET 2.3.5 (único motor; solo en el backend) |
| Fuente compilada | github.com/OpenWaterAnalytics/EPANET, tag `v2.3.5` |
| SHA del commit del tag | `444725fbf16ab28b0470ef0ed281dc4849d49583` (verificado en el `Dockerfile`) |
| Compilación | CMake, `Release`, en la etapa `epanet-build` de `backend/Dockerfile` |
| Ejecutable de referencia | `runepanet` (reporta «Version 2.3.05») |
| Wheel Python | `owa-epanet==2.3.5` (fijado en `pyproject.toml` y `uv.lock`) |
| `EN_getversion` del wheel | `20305` (solo registro) |

`EN_getversion` **no** se usa como prueba de equivalencia entre el wheel y el ejecutable. La
equivalencia se demuestra con `backend/tests/test_reference_networks.py`: los resultados de la
API (wheel) y de `runepanet` (compilado) coinciden en todos los pasos de reporte de Net1, Net2 y
Net3 dentro de las [tolerancias](tolerancias.md).

La verificación de identidad (wheel 2.3.5, SHA del tag y banner de `runepanet`) se ejecuta en el
build de la imagen (`scripts/check_engine.py --build`) y en `tests/test_engine_version.py`. Cada
corrida guarda en `simulation_run.engine` la versión del wheel, el SHA y `EN_getversion`.
