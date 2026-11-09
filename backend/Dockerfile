# syntax=docker/dockerfile:1
# ── Etapa 1: compilación de OWA-EPANET desde el tag oficial ─────────────
FROM python:3.12.16-slim-trixie AS epanet-build
ARG EPANET_TAG=v2.3.5
ARG EPANET_SHA=444725fbf16ab28b0470ef0ed281dc4849d49583
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${EPANET_TAG}" https://github.com/OpenWaterAnalytics/EPANET.git /src/epanet \
 && cd /src/epanet \
 && test "$(git rev-parse HEAD)" = "${EPANET_SHA}" \
    || (echo "SHA de EPANET inesperado: $(git rev-parse HEAD)" >&2; exit 1)
RUN cmake -S /src/epanet -B /build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build /build --parallel \
 && mkdir -p /out/bin /out/lib \
 && cp "$(find /build -type f -name runepanet | head -n1)" /out/bin/runepanet \
 && find /build -name 'libepanet2.so*' -exec cp -P {} /out/lib/ \; \
 && printf 'EPANET_TAG=%s\nEPANET_SHA=%s\nCMAKE_BUILD_TYPE=Release\n' "${EPANET_TAG}" "${EPANET_SHA}" > /out/BUILD_INFO \
 && ls -l /out/bin /out/lib

# ── Etapa 2: dependencias Python con uv (lockfile congelado) ─────────────
FROM python:3.12.16-slim-trixie AS deps
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS deps-test
RUN uv sync --frozen --no-install-project

# ── Etapa 3: imagen de ejecución ─────────────────────────────────────────
FROM python:3.12.16-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:${PATH}" \
    EPANET_BUILD_INFO=/opt/epanet/BUILD_INFO RUNEPANET=/usr/local/bin/runepanet
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=epanet-build /out/bin/runepanet /usr/local/bin/runepanet
COPY --from=epanet-build /out/lib/ /usr/local/lib/
COPY --from=epanet-build /out/BUILD_INFO /opt/epanet/BUILD_INFO
RUN ldconfig && runepanet 2>&1 | head -n 3 || true
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
# Verificación de compilación: wheel owa-epanet == 2.3.5 y runepanet operativo.
RUN python scripts/check_engine.py --build
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]

# ── Etapa 4: imagen de pruebas ───────────────────────────────────────────
FROM runtime AS test
USER root
COPY --from=deps-test /opt/venv /opt/venv
COPY pyproject.toml ./
COPY tests ./tests
USER app
CMD ["pytest"]
