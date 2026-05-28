# Public quickstart (preview)

This repository is **experimental and private** until the template corpus, eval loop, and
fine-tuned model are ready for open source. Use this as a checklist for the future public release.

## Prerequisites

- Docker Desktop (macOS) or Docker on Linux
- Copy `.env.example` → `.env` and set `AGENT_API_TOKEN`, `PLAYIT_SECRET_KEY`
- `secrets/rcon_password` for the Minecraft container

## Spin up

```bash
docker compose up -d
docker compose up -d --build mc-agent
./scripts/build-plugin.sh
```

## Validate

```bash
./scripts/validate-all.sh
python -m agent.eval template-ranking
```

## In-game

```
/agent build me a small chicken coop
/agent good
```

See [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for the full loop.
