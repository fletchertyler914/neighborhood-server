# Neighborhood Minecraft Server — common one-liners.
#
# Run `make help` to see the full list. The targets are wrappers around
# scripts/ and docker compose so contributors don't have to memorize the
# exact incantations.

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# Pretty colors (off when piped).
ifneq (,$(findstring xterm,${TERM}))
COLOR_GREEN := \033[32m
COLOR_DIM   := \033[2m
COLOR_RESET := \033[0m
endif

.PHONY: help bootstrap up down logs status restart \
        seed smoke eval test live-tools full-validation \
        plugin metrics health \
        format clean

help:
	@echo "Neighborhood Minecraft Server"
	@echo ""
	@echo "Setup"
	@echo "  $(COLOR_GREEN)make bootstrap$(COLOR_RESET)        Detect host deps and write secrets/.env"
	@echo "  $(COLOR_GREEN)make up$(COLOR_RESET)               Start mc-lan + mc-agent + sidecars"
	@echo "  $(COLOR_GREEN)make down$(COLOR_RESET)             Stop the stack"
	@echo "  $(COLOR_GREEN)make restart$(COLOR_RESET)          docker compose restart everything"
	@echo "  $(COLOR_GREEN)make logs$(COLOR_RESET)             Tail mc-agent + mc-lan logs"
	@echo "  $(COLOR_GREEN)make status$(COLOR_RESET)           docker compose ps + /health"
	@echo ""
	@echo "Content"
	@echo "  $(COLOR_GREEN)make seed$(COLOR_RESET)             Build all schematics in-world (one-time)"
	@echo "  $(COLOR_GREEN)make plugin$(COLOR_RESET)           Build the NeighborhoodAgent Paper plugin"
	@echo ""
	@echo "Validation"
	@echo "  $(COLOR_GREEN)make test$(COLOR_RESET)             Unit + contract tests (no live server needed)"
	@echo "  $(COLOR_GREEN)make smoke$(COLOR_RESET)            26 NL prompts → live LLM → orchestrator"
	@echo "  $(COLOR_GREEN)make eval$(COLOR_RESET)             19-case strict spec eval (vs baseline)"
	@echo "  $(COLOR_GREEN)make live-tools$(COLOR_RESET)       Live RCON tool integration tests"
	@echo "  $(COLOR_GREEN)make full-validation$(COLOR_RESET)  Paste every template + summon every mob"
	@echo ""
	@echo "Observability"
	@echo "  $(COLOR_GREEN)make health$(COLOR_RESET)           Hit /health"
	@echo "  $(COLOR_GREEN)make metrics$(COLOR_RESET)          Hit /metrics"

bootstrap:
	./scripts/bootstrap.sh

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=80

status:
	@docker compose ps
	@echo ""
	@$(MAKE) -s health

seed:
	./scripts/seed-templates.sh

plugin:
	./scripts/build-plugin.sh

test:
	PYTHONPATH=. python3 -m pytest tests/ -q --ignore=tests/integration

smoke:
	./scripts/agent-smoke.sh

eval:
	docker compose exec -T \
	  -e AGENT_API_TOKEN="$$(awk -F= '/^AGENT_API_TOKEN=/{print $$2}' .env)" \
	  mc-agent python -m agent.eval.cli run spec \
	  --orchestrator-url http://127.0.0.1:8787 \
	  --compare-baseline /app/agent/eval/baseline.strict.json \
	  --player "$$(./scripts/_detect_player.sh)" \
	  --uuid "$$(uuidgen)"

live-tools:
	./scripts/live-tool-tests.sh

full-validation:
	PYTHONPATH=. python3 scripts/full_validation.py

health:
	@docker compose exec -T mc-agent python -c \
	  "import urllib.request, json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=5).read()), indent=2))"

metrics:
	@docker compose exec -T mc-agent python -c \
	  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8787/metrics', timeout=5).read().decode())"

clean:
	rm -rf data/eval-runs/* || true
