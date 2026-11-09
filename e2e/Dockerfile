# Imagen del recorrido e2e: navegadores de la imagen oficial + paquete Python de la misma versión.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
RUN pip install --no-cache-dir --break-system-packages playwright==1.64.1 \
 && python3 -c "import playwright.sync_api"
