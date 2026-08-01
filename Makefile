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
        seed smoke eval test live-tools live-core metal-check bakeoff agent-gate full-validation \
        companion-gate companion-corpus companion-live companion-live-core \
        companion-live-templates companion-live-templates-all \
        companion-live-safety companion-live-dialogue companion-deploy \
        perception-fast perception-replay perception-live perception-report \
        perception-promote elite-gate \
        corpus corpus-quick triage feedback-report feedback-export \
        companion-feedback-export companion-triage training-data \
        train train-full deploy-model compare-models \
        plugin metrics health invite tunnels \
        format clean generate-corpus corpus-export

CORPUS_ENV = -e AGENT_EVAL_ALLOW_WORLD_MUTATION=1 \
  -e AGENT_API_TOKEN="$$(awk -F= '/^AGENT_API_TOKEN=/{print $$2}' .env 2>/dev/null || echo dev-change-me)" \
  -e AGENT_CORPUS_PLAYER="$${AGENT_CORPUS_PLAYER:-$$(./scripts/_detect_player.sh 2>/dev/null || true)}"

TRAIN_MODEL ?= neighborhood-qwen2.5-7b:v1
TRAIN_SFT ?= datasets/sft/train.jsonl
TRAIN_DPO ?= datasets/preferences/train.jsonl
TRAIN_MAX_LENGTH ?= 512

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
	@echo "  $(COLOR_GREEN)make tunnels$(COLOR_RESET)          Auto-create Java + Bedrock playit tunnels"
	@echo "  $(COLOR_GREEN)make invite$(COLOR_RESET)           Generate printable invite sheet from playit"
	@echo ""
	@echo "Validation (greenfield companion)"
	@echo "  $(COLOR_GREEN)make test$(COLOR_RESET)             Unit + contract tests (no live server needed)"
	@echo "  $(COLOR_GREEN)make metal-check$(COLOR_RESET)      Validate Metal/MLX residency for one model"
	@echo "  $(COLOR_GREEN)make companion-gate$(COLOR_RESET)   Offline sidekick accuracy/SLO gate"
	@echo "  $(COLOR_GREEN)make companion-corpus$(COLOR_RESET) Offline Wave 2 eighty_seed full corpus + buckets"
	@echo "  $(COLOR_GREEN)make companion-live$(COLOR_RESET)   Full live e2e (tools+safety+templates)"
	@echo "  $(COLOR_GREEN)make companion-live-core$(COLOR_RESET) Smoke live e2e"
	@echo "  $(COLOR_GREEN)make companion-live-templates$(COLOR_RESET) Curated template pastes"
	@echo "  $(COLOR_GREEN)make companion-live-templates-all$(COLOR_RESET) All 101 template pastes"
	@echo "  $(COLOR_GREEN)make companion-live-safety$(COLOR_RESET) Refusal / safety live cases"
	@echo "  $(COLOR_GREEN)make companion-live-dialogue$(COLOR_RESET) Compound + multi-turn clarify flows"
	@echo "  $(COLOR_GREEN)make companion-deploy$(COLOR_RESET) Build runtime + native plugin and restart Paper"
	@echo "  $(COLOR_GREEN)make companion-feedback-export$(COLOR_RESET) Export SQLite feedback → JSONL buckets"
	@echo "  $(COLOR_GREEN)make companion-triage$(COLOR_RESET)  Weekly feedback bucket summary + next steps"
	@echo "  $(COLOR_GREEN)make full-validation$(COLOR_RESET)  Paste every template + summon every mob"
	@echo ""
	@echo "Elite perception"
	@echo "  $(COLOR_GREEN)make perception-fast$(COLOR_RESET)   Schema + synthetic geometry + routing (<30s)"
	@echo "  $(COLOR_GREEN)make perception-live$(COLOR_RESET)   Targeted live perception CASE=<id>"
	@echo "  $(COLOR_GREEN)make perception-report$(COLOR_RESET) Latest failure bundles / latency deltas"
	@echo "  $(COLOR_GREEN)make perception-replay$(COLOR_RESET) Replay RUN=<id>"
	@echo "  $(COLOR_GREEN)make perception-promote$(COLOR_RESET) Promote RUN=<id> NAME=<name>"
	@echo "  $(COLOR_GREEN)make elite-gate$(COLOR_RESET)        Authoritative full release sequence"
	@echo ""
	@echo "Deprecated (old RCON orchestrator — see docs/DEPRECATED.md)"
	@echo "  make smoke / eval / live-tools / agent-gate / corpus*"
	@echo ""
	@echo "Observability"
	@echo "  $(COLOR_GREEN)make health$(COLOR_RESET)           Hit /health"
	@echo "  $(COLOR_GREEN)make metrics$(COLOR_RESET)          Hit /metrics"

bootstrap:
	./scripts/bootstrap.sh

up:
	docker compose pull mc playit
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
	docker run --rm -v "$(CURDIR)/plugins/neighborhood-agent:/workspace" \
	  -w /workspace gradle:8.12-jdk21 gradle jar --no-daemon
	docker compose stop mc
	docker cp plugins/neighborhood-agent/build/libs/NeighborhoodAgent.jar \
	  mc-lan:/data/plugins/NeighborhoodAgent.jar
	docker compose start mc

tunnels:
	./scripts/playit_setup.py

invite:
	./scripts/print_invite.py

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

live-core:
	PYTHONPATH=. python3 -m agent.eval.live_tools --player "$${AGENT_LIVE_TOOL_PLAYER:-$$(./scripts/_detect_player.sh)}"

metal-check:
	PYTHONPATH=. python3 scripts/validate_metal_inference.py \
	  --model "$${AGENT_METAL_MODEL:-gemma4:12b-mlx}"

bakeoff:
	@echo "Sequential bake-off (one model at a time, Metal preflight each slot)"
	PYTHONPATH=. python3 scripts/model_bakeoff.py --live \
	  --player "$${AGENT_BAKEOFF_PLAYER:-$$(./scripts/_detect_player.sh)}" \
	  --models "$${AGENT_BAKEOFF_MODELS:-gemma4:12b-mlx,ornith:35b}"

agent-gate:
	docker compose exec -T \
	  -e AGENT_API_TOKEN="$$(awk -F= '/^AGENT_API_TOKEN=/{print $$2}' .env)" \
	  -e AGENT_GATE_PLAYER="$${AGENT_GATE_PLAYER:-$$(./scripts/_detect_player.sh)}" \
	  mc-agent python -m agent.eval.agent_gate

companion-gate:
	PYTHONPATH=. LOCAL_LLM_BASE_URL="$${LOCAL_LLM_BASE_URL:-http://127.0.0.1:11434}" \
	  LOCAL_LLM_NUM_CTX=2048 LOCAL_LLM_NUM_PREDICT=192 \
	  AGENT_LOCAL_MODEL_TIMEOUT_SEC=8 \
	  python3 -m evals.run_offline --mode gate --limit 100

# Full grounded Wave 2 seed (all eighty_seed rows). Never truncates.
companion-corpus:
	PYTHONPATH=. python3 -m evals.run_offline --mode corpus --skip-model

# Live harnesses always target the operator account — never friends online.
AGENT_LIVE_PLAYER ?= firecrab93

companion-live:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite $${AGENT_LIVE_SUITE:-full}

companion-live-core:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite core

companion-live-templates:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite templates

companion-live-templates-all:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite templates-all

companion-live-safety:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite safety

companion-live-dialogue:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite dialogue

companion-deploy:
	docker run --rm -v "$(CURDIR)/plugins/neighborhood-agent:/workspace" \
	  -w /workspace gradle:8.12-jdk21 gradle jar --no-daemon
	docker compose up -d --build mc-agent
	docker compose stop mc
	docker cp plugins/neighborhood-agent/build/libs/NeighborhoodAgent.jar \
	  mc-lan:/data/plugins/NeighborhoodAgent.jar
	docker compose start mc

perception-fast:
	PYTHONPATH=. python3 -m pytest tests/test_perception_contract.py -q
	PYTHONPATH=. python3 -m evals.run_perception_offline --scenes 40

perception-live:
	AGENT_LIVE_PLAYER="$(AGENT_LIVE_PLAYER)" PYTHONPATH=. python3 -m evals.run_live --suite $${CASE:-perception}

perception-report:
	PYTHONPATH=. python3 -m evals.failure_bundles report

perception-replay:
	PYTHONPATH=. python3 -m evals.failure_bundles replay --run $${RUN:?set RUN=<id>}

perception-promote:
	PYTHONPATH=. python3 -m evals.failure_bundles promote --run $${RUN:?set RUN=<id>} --name $${NAME:?set NAME=<name>}

elite-gate:
	PYTHONPATH=. python3 -m evals.run_elite_gate

full-validation:
	PYTHONPATH=. python3 scripts/full_validation.py

generate-corpus:
	PYTHONPATH=. python3 agent/eval/corpus/generate_corpus.py

corpus:
	docker compose exec -T $(CORPUS_ENV) mc-agent \
	  python -m agent.eval.corpus_runner \
	  --orchestrator-url http://127.0.0.1:8787

corpus-gate:
	docker compose exec -T $(CORPUS_ENV) -e AGENT_CORPUS_MIN_PASS_RATE=0.9 mc-agent \
	  python -m agent.eval.corpus_runner \
	  --orchestrator-url http://127.0.0.1:8787

corpus-quick:
	docker compose exec -T $(CORPUS_ENV) -e AGENT_CORPUS_LIMIT=30 mc-agent \
	  python -m agent.eval.corpus_runner \
	  --orchestrator-url http://127.0.0.1:8787

triage:
	docker compose exec -T mc-agent python -m agent.eval.triage --run /app/data/corpus-runs/latest

corpus-baseline:
	PYTHONPATH=. python3 agent/eval/corpus/save_baseline.py --run data/corpus-runs/latest

corpus-export:
	PYTHONPATH=. python3 -m agent.training build-datasets --run data/corpus-runs/latest

feedback-report:
	PYTHONPATH=. python3 -m agent.training feedback --report

feedback-export:
	PYTHONPATH=. python3 -m agent.training feedback \
	  --sft-out datasets/sft/from-feedback.jsonl \
	  --dpo-out datasets/preferences/from-feedback.jsonl

companion-feedback-export:
	PYTHONPATH=. python3 scripts/export_companion_feedback.py

companion-triage:
	PYTHONPATH=. python3 scripts/companion_triage.py

training-data: corpus-export feedback-export
	PYTHONPATH=. python3 -m agent.training merge-datasets \
	  --sft datasets/sft/corpus.jsonl \
	  --sft datasets/sft/from-feedback.jsonl \
	  --dpo datasets/preferences/corpus.jsonl \
	  --dpo datasets/preferences/from-feedback.jsonl \
	  --sft-out $(TRAIN_SFT) \
	  --dpo-out $(TRAIN_DPO)

sample-diverse:
	PYTHONPATH=. python3 -m agent.training sample-diverse --run data/corpus-runs/latest

train: training-data
	PYTHONPATH=. python3 -m agent.training sample-diverse --run data/corpus-runs/latest || true
	PYTHONPATH=. python3 -m agent.training build-datasets --run data/corpus-runs/latest
	$(MAKE) training-data
	AGENT_TRAIN_DRY_RUN=1 PYTHONPATH=. python3 -m agent.training lora-finetune --dry-run \
	  --sft $(TRAIN_SFT) --dpo $(TRAIN_DPO) --out models/lora/v1 --max-length $(TRAIN_MAX_LENGTH)
	PYTHONPATH=. python3 -m agent.training ollama-register --model-name $(TRAIN_MODEL) --adapter models/lora/v1/adapter || true

train-full: training-data
	PYTHONPATH=. python3 -m agent.training sample-diverse --run data/corpus-runs/latest || true
	PYTHONPATH=. python3 -m agent.training build-datasets --run data/corpus-runs/latest
	$(MAKE) training-data
	PYTHONPATH=. python3 -m agent.training lora-finetune \
	  --sft $(TRAIN_SFT) --dpo $(TRAIN_DPO) --out models/lora/v1 --max-length $(TRAIN_MAX_LENGTH)
	PYTHONPATH=. python3 -m agent.training ollama-register --auto-merge --model-name $(TRAIN_MODEL) --adapter models/lora/v1/adapter

deploy-model:
	./scripts/deploy-model.sh $${OLLAMA_MODEL:-$(TRAIN_MODEL)}
	$(MAKE) compare-models

compare-models:
	docker compose exec -T $(CORPUS_ENV) -e AGENT_CORPUS_LIMIT=51 mc-agent \
	  python -m agent.training.compare_models --limit 51 \
	  --models qwen2.5:7b-instruct,$(TRAIN_MODEL)

health:
	@docker compose exec -T mc-agent python -c \
	  "import urllib.request, json; print(json.dumps(json.loads(urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=5).read()), indent=2))"

metrics:
	@docker compose exec -T mc-agent python -c \
	  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8787/metrics', timeout=5).read().decode())"

clean:
	rm -rf data/eval-runs/* || true
