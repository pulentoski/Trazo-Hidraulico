# Trazo Hidráulico — tareas de desarrollo y operación local.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE  := docker compose --env-file .env -f infra/compose.yml
# Las pruebas escriben reportes en docs/validation con el dueño del repositorio.
HOST_UID ?= $(shell stat -c %u .)
HOST_GID ?= $(shell stat -c %g .)
export HOST_UID HOST_GID

.PHONY: help env up down logs ps build test test-backend test-frontend reset-db gen-types

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

env: ## Crea .env desde .env.example con claves aleatorias (si no existe)
	@if [ ! -f .env ]; then \
	  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 24)/" \
	      -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$$(openssl rand -hex 24)/" .env.example > .env; \
	  chmod 600 .env; echo "Creado .env (claves aleatorias). Agrega tu key de Google Maps si la tienes."; \
	fi

up: env ## Construye y levanta la pila; espera a que todo esté healthy
	$(COMPOSE) up -d --build --wait --wait-timeout 300
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.Status}}'
	@echo "Editor disponible en http://localhost:$$(grep -E '^HTTP_PORT=' .env | cut -d= -f2)"

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
