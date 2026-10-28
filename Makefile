.DEFAULT_GOAL := help
COMPOSE := docker compose

help: ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up: ## Build and start the full stack (web on :8080, API on :8000)
	$(COMPOSE) up -d --build

down: ## Stop the stack (data volumes are kept)
	$(COMPOSE) down

reset: ## Stop the stack and delete all data volumes
	$(COMPOSE) down -v

logs: ## Follow logs for every service
	$(COMPOSE) logs -f

seed: ## Load synthetic data with planted rings and resolve it
	$(COMPOSE) run --rm api python -m graphy.scripts.seed_demo --people 400 --rings 4

build: ## Build the backend and web images
	docker build -t graphy-backend:dev backend
	docker build -t graphy-web:dev frontend

deps: ## Start only the databases, for running API and UI on the host
	$(COMPOSE) up -d neo4j postgres init

api: ## Run the API on the host with reload (needs `make deps`)
	cd backend && uv run uvicorn graphy.main:app --reload

ui: ## Run the UI dev server on :5173 (proxies /api to :8000)
	cd frontend && npm install && npm run dev

test: ## Backend lint and tests, frontend type-check
	cd backend && uv run ruff check . && uv run pytest -q
	cd frontend && npm run typecheck

helm-lint: ## Lint and render the Helm chart
	helm lint deploy/helm/graphy && helm template t deploy/helm/graphy > /dev/null

.PHONY: help up down reset logs seed build deps api ui test helm-lint
