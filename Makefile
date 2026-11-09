# Trazo Hidráulico — tareas de desarrollo y operación local.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE  := docker compose --env-file .env -f infra/compose.yml
# Las pruebas escriben reportes en docs/validation con el dueño del repositorio.
HOST_UID ?= $(shell stat -c %u .)
HOST_GID ?= $(shell stat -c %g .)
export HOST_UID HOST_GID

.PHONY: help env check-auth up up-public down logs ps build test test-backend test-frontend test-e2e reset-db gen-types backup

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

env: ## Crea .env desde .env.example con claves aleatorias (si no existe)
	@if [ ! -f .env ]; then \
	  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 24)/" \
	      -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$$(openssl rand -hex 24)/" .env.example > .env; \
	  chmod 600 .env; echo "Creado .env (claves aleatorias). Agrega tu key de Google Maps si la tienes."; \
	fi

check-auth: env ## Verifica la configuración de basic auth en .env antes de arrancar
	@set -a; . ./.env; set +a; \
	case "$${BASIC_AUTH_ENABLED:-true}" in \
	  false) echo "Aviso: basic auth DESACTIVADO (BASIC_AUTH_ENABLED=false). Solo para desarrollo local." ;; \
	  true) if [ -z "$${BASIC_AUTH_USER:-}" ] || [ -z "$${BASIC_AUTH_HASH:-}" ]; then \
	          echo "ERROR: basic auth activo pero faltan BASIC_AUTH_USER y/o BASIC_AUTH_HASH en .env." >&2; \
	          echo "  Genere el hash: docker run --rm -it caddy:2.11.9-alpine caddy hash-password" >&2; \
	          echo "  y guárdelo entre comillas simples: BASIC_AUTH_HASH='\$$2a\$$14\$$...'" >&2; \
	          echo "  Para desarrollo local puede usar BASIC_AUTH_ENABLED=false (ver README)." >&2; exit 1; fi ;; \
	  *) echo "ERROR: BASIC_AUTH_ENABLED debe ser true o false." >&2; exit 1 ;; \
	esac

up: check-auth ## Construye y levanta la pila; espera a que todo esté healthy
	$(COMPOSE) up -d --build --wait --wait-timeout 300
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.Status}}'
	@echo "Editor disponible en http://localhost:$$(grep -E '^HTTP_PORT=' .env | cut -d= -f2)"

up-public: check-auth ## Publica en SITE_ADDRESS con HTTPS automático (ver README)
	@set -a; . ./.env; set +a; [ "$${BASIC_AUTH_ENABLED:-true}" = true ] || { echo "ERROR: para publicar, BASIC_AUTH_ENABLED debe ser true." >&2; exit 1; }
	$(COMPOSE) -f infra/compose.public.yml up -d --build --wait --wait-timeout 300
	@$(COMPOSE) -f infra/compose.public.yml ps --format 'table {{.Service}}\t{{.Status}}'

down: ## Detiene la pila (conserva datos)
	$(COMPOSE) down

logs: ## Sigue los logs de todos los servicios
	$(COMPOSE) logs -f --tail=200

ps: ## Estado de los servicios
	$(COMPOSE) ps

build: env ## Construye todas las imágenes
	$(COMPOSE) --profile test build

test: env test-backend test-frontend ## Ejecuta todas las pruebas dentro de contenedores
	@echo "✔ make test: todas las pruebas pasaron."

test-backend: env
	$(COMPOSE) up -d --build --wait db cache
	$(COMPOSE) --profile test build api-test
	$(COMPOSE) --profile test run --rm api-test

test-frontend: env
	$(COMPOSE) --profile test build web-test
	$(COMPOSE) --profile test run --rm web-test

test-e2e: ## Recorrido visual con Playwright contra la pila levantada (make up; requiere BASIC_AUTH_ENABLED=false)
	docker build -q -t trazo-hidraulico/e2e:local e2e >/dev/null
	docker run --rm --network host --ipc=host -u $(HOST_UID):$(HOST_GID) -e HOME=/tmp -v $(CURDIR):/repo -w /repo \
	  trazo-hidraulico/e2e:local python3 e2e/recorrido.py

backup: env ## Respaldo local: BD (pg_dump), imágenes Docker, git bundle y .env (ver infra/RESTAURAR.template.md)
	@infra/backup.sh

reset-db: env ## Borra el volumen de la base de datos y la recrea vacía
	$(COMPOSE) down
	-docker volume rm trazo-hidraulico_pgdata
	$(COMPOSE) up -d --build --wait --wait-timeout 300

gen-types: env ## Regenera openapi.json y los tipos TypeScript del frontend
	$(COMPOSE) build api
	docker run --rm --network none --entrypoint python trazo-hidraulico/api:local scripts/export_openapi.py > frontend/src/api/openapi.json
	docker build -q --target deps -t trazo-hidraulico/web-deps:local frontend >/dev/null
	docker run --rm --network none -u $(HOST_UID):$(HOST_GID) -v $(CURDIR)/frontend/src/api:/app/src/api \
	  trazo-hidraulico/web-deps:local ./node_modules/.bin/openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
	@echo "Tipos regenerados en frontend/src/api/schema.d.ts"
