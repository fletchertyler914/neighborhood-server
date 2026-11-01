# Sidekick Architecture

The sidekick is a local, in-game control system. It is not a general chatbot
and does not expose an external AI-control interface.

```text
Player /agent
  -> Paper plugin context snapshot
  -> authenticated private WebSocket
  -> deterministic router or bounded local model compiler
  -> typed action
  -> Paper permission/claim/deadline validation
  -> native Bukkit or FAWE execution
  -> world postcondition verification
  -> short player response
```

## Trust boundary

The Python runtime is not trusted to mutate the world. The Paper plugin checks
the protocol schema, player identity, permissions, GriefPrevention claims,
deadlines, edit limits, admin-item restrictions, and idempotency before each
action. It journals action results so reconnects cannot repeat mutations.

RCON remains private for operator scripts and backups. It is never an agent
transport.

## Runtime

`companion/` is one async process:

- `routing.py` handles deterministic Tier S/A requests first.
- `templates.py` resolves high-confidence curated structures.
- `provider.py` uses Ollama's native API and validates structured output.
- `storage.py` persists jobs, actions, feedback, timings, and idempotency
  correlations in SQLite WAL.
- `app.py` owns the private WebSocket, health, and metrics endpoints.

No Redis, external queue, vector database, cloud fallback, or multi-agent
framework is required.

## Native gateway

`plugins/neighborhood-agent/` maintains the outbound connection and executes
typed actions. Direct FAWE API calls paste schematics without player
teleportation, selections, or text commands.

### Build Book (in-game explorer)

Kids browse the gold catalog with a chest GUI (`/builds`, `/menu`, or
Crafter’s Build Book item). The plugin reads the same mounted
`catalog.json` locally (categories, search, confirm), then pastes via the
existing native `paste_template` executor (claims, volume caps, verify,
undo). No companion WebSocket catalog API and no 3D preview.

## Perception (eyes)

Latency-first, two-level observation:

1. **FastObservationV1** on every `job.submit` — gaze, held block, policy,
   fingerprint (sub-tick).
2. **SemanticSceneV1** via private `observation.request` / `observation.result`
   — openings, surfaces, clearance, palette, nearby (lazy, purpose-specific).

Paper remains authoritative: native tools re-sense before mutation and reject
stale pose/geometry. The model receives only a coordinate-free summary such as
`looking_at=oak_planks; holding=quartz_block; opening=31×86 high`.

## Player response seam

When a job finishes, the runtime emits `job.complete` with both `message`
(chat) and `spoken_text` (short speakable sentence). TTS audio is intentionally
out of scope; clients may ignore `spoken_text` until a playback feature exists.

## Validation

`make test`, `make metal-check`, and `make companion-gate` enforce protocol,
runtime, model, safety, and latency requirements. A capability is complete only
after its real-world mutation is executed and its postcondition is verified.

Release checklist for family beta:

```bash
make companion-gate
make companion-live
make companion-live-dialogue
```

Honest SLOs on a warm Apple Silicon host: common ≤500ms; builds ~0.2–2s;
model path ~3–6s (Tier B median ≤4500ms / case ≤8000ms).
