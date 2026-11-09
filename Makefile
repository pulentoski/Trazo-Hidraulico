# Trazo Hidráulico — tareas de desarrollo y operación local.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE  := docker compose --env-file .env -f infra/compose.yml
PUBLIC   := $(COMPOSE) -f infra/compose.public.yml -f infra/compose.prod.yml
# Las pruebas escriben reportes en docs/validation con el dueño del repositorio.
HOST_UID ?= $(shell stat -c %u .)
HOST_GID ?= $(shell stat -c %g .)
export HOST_UID HOST_GID
# Cambios del Caddyfile (montado como archivo) recrean el proxy en make up / up-public.
CADDY_CONFIG_HASH := $(shell cat infra/caddy/Caddyfile infra/caddy/entrypoint.sh 2>/dev/null | sha256sum | cut -c1-16)
export CADDY_CONFIG_HASH

.PHONY: help env check-auth up up-public down logs ps build test test-backend test-frontend test-e2e reset-db gen-types backup \
        create-admin unlock-user reset-password actualizar-ip demo restore-test backup-now

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
	case "$${BASIC_AUTH_ENABLED:-false}" in \
	  false) ;; \
	  true) if [ -z "$${BASIC_AUTH_USER:-}" ] || [ -z "$${BASIC_AUTH_HASH:-}" ]; then \
	          echo "ERROR: basic auth activo pero faltan BASIC_AUTH_USER y/o BASIC_AUTH_HASH en .env." >&2; \
	          echo "  Genere el hash: docker run --rm -it caddy:2.11.9-alpine caddy hash-password" >&2; \
	          echo "  y guárdelo entre comillas simples: BASIC_AUTH_HASH='\$$2a\$$14\$$...'" >&2; \
	          echo "  El basic auth es opcional: la aplicación tiene su propio ingreso (BASIC_AUTH_ENABLED=false)." >&2; exit 1; fi ;; \
	  *) echo "ERROR: BASIC_AUTH_ENABLED debe ser true o false." >&2; exit 1 ;; \
	esac

up: check-auth ## Construye y levanta la pila; espera a que todo esté healthy
	$(COMPOSE) up -d --build --wait --wait-timeout 300
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.Status}}'
	@echo "Editor disponible en http://localhost:$$(grep -E '^HTTP_PORT=' .env | cut -d= -f2)"

up-public: check-auth ## Publica en SITE_ADDRESS (HTTPS) con límites, logs rotados y respaldo diario (docs/despliegue.md)
	@set -a; . ./.env; set +a; [ -n "$${SITE_ADDRESS:-}" ] || { echo "ERROR: defina SITE_ADDRESS en .env (dominio, https://IP o http://IP)." >&2; exit 1; }; \
	case "$$SITE_ADDRESS" in http://*) \
	  echo "ADVERTENCIA: modo HTTP sin cifrado (solo pruebas): contraseñas y sesiones viajan en texto plano." >&2; \
	  [ "$${COOKIE_SECURE:-true}" = false ] || { echo "ERROR: con SITE_ADDRESS=http://... defina COOKIE_SECURE=false en .env: el navegador descarta una cookie Secure recibida por HTTP y el ingreso no avanza." >&2; exit 1; } ;; \
	esac
	@set -a; . ./.env; set +a; mkdir -p "$${BACKUP_DIR:-/var/backups/trazo-hidraulico}" 2>/dev/null || true
	$(PUBLIC) up -d --build --wait --wait-timeout 300
	@$(PUBLIC) ps --format 'table {{.Service}}\t{{.Status}}'

actualizar-ip: ## Sin dominio: ajusta SITE_ADDRESS y PUBLIC_URL a la IP pública actual (deploy/actualizar-ip.sh)
	@deploy/actualizar-ip.sh

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

E2E_EMAIL ?= e2e@trazo.local
E2E_PASSWORD ?= Recorrido-e2e-2026
# BASE_URL: dirección a recorrer (en una instancia publicada, p. ej. https://IP; acepta el certificado interno).
# E2E_SHOTS: carpeta de capturas (por defecto docs/capturas).
BASE_URL ?= http://localhost:8080
E2E_SHOTS ?= docs/capturas
test-e2e: ## Recorrido visual con Playwright contra la pila levantada (make up; o BASE_URL=https://IP en una instancia)
	$(COMPOSE) exec -T api python -m app.cli ensure-user --email $(E2E_EMAIL) --password $(E2E_PASSWORD) --org "Recorrido e2e" --role admin
	docker build -q -t trazo-hidraulico/e2e:local e2e >/dev/null
	docker run --rm --network host --ipc=host -u $(HOST_UID):$(HOST_GID) -e HOME=/tmp -v $(CURDIR):/repo -w /repo \
	  -e E2E_EMAIL=$(E2E_EMAIL) -e E2E_PASSWORD=$(E2E_PASSWORD) -e BASE_URL=$(BASE_URL) -e E2E_SHOTS=$(E2E_SHOTS) \
	  trazo-hidraulico/e2e:local python3 e2e/recorrido.py

create-admin: ## Crea o actualiza el superadministrador (pide correo y contraseña; o EMAIL=, y TRAZO_ADMIN_PASSWORD en el entorno)
	@t=; [ -t 0 ] || t=-T; \
	TRAZO_ADMIN_EMAIL="$${TRAZO_ADMIN_EMAIL:-$(EMAIL)}" TRAZO_ADMIN_PASSWORD="$${TRAZO_ADMIN_PASSWORD:-$(PASSWORD)}" \
	  $(COMPOSE) exec $$t -e TRAZO_ADMIN_EMAIL -e TRAZO_ADMIN_PASSWORD api python -m app.cli create-admin

unlock-user: ## Quita el bloqueo por intentos fallidos (423) de una cuenta: make unlock-user EMAIL=...
	@[ -n "$(EMAIL)" ] || { echo "Uso: make unlock-user EMAIL=correo@dominio" >&2; exit 2; }
	$(COMPOSE) exec -T api python -m app.cli unlock-user --email "$(EMAIL)"

reset-password: ## Contraseña nueva para una cuenta (pedida por consola, sin eco): make reset-password EMAIL=...
	@[ -n "$(EMAIL)" ] || { echo "Uso: make reset-password EMAIL=correo@dominio" >&2; exit 2; }
	@t=; [ -t 0 ] || t=-T; $(COMPOSE) exec $$t -e TRAZO_NEW_PASSWORD api python -m app.cli reset-password --email "$(EMAIL)"

demo: ## Organización «Demo APR» con un usuario por rol y el proyecto APR Demo (solo entorno local; docs/demo.md)
	$(COMPOSE) exec -T api python -m app.cli seed-demo

backup-now: ## Respaldo inmediato con el servicio de respaldo de producción
	$(PUBLIC) run --rm backup now

restore-test: ## Restaura el último respaldo automático en una base temporal y verifica sus tablas
	$(PUBLIC) run --rm backup restore-test

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
