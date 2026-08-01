# Tool Contract

`protocol/envelope.schema.json` and `protocol/tools.schema.json` are the
language-neutral contracts between the companion runtime and Paper plugin.

Every message includes protocol version, type, trace ID, sequence, timestamp,
optional job/deadline, and a typed payload. Every mutation includes a stable
action ID and idempotency key.

Completion has three distinct meanings:

- accepted: durable and queued
- executed: the native API operation completed
- verified: a tool-specific world probe confirmed the postcondition

`job.complete` payload fields:

| Field | Purpose |
| --- | --- |
| `ok` | overall success after verification |
| `message` | chat-facing reply (may be slightly richer) |
| `spoken_text` | short jargon-free sentence for a future TTS path (no timing/route names) |
| `verified` | world postcondition confirmed |
| `route` / `total_ms` | observability only — not for kids |

The plugin currently uses `message` for chat and ignores `spoken_text` until
TTS lands. The plugin must not report exact build success unless verification
passes.

Adding or changing a tool requires:

1. Update the canonical schema.
2. Add the native Java executor and capability advertisement.
3. Add runtime routing or skill access.
4. Add policy, idempotency, verification, and undo behavior.
5. Add offline, live-world, failure, and latency cases.
6. Rebuild the plugin and pass all release gates.

### Perception messages

| Type | Direction | Purpose |
| --- | --- | --- |
| `job.submit.observation` | plugin → companion | `FastObservationV1` (gaze/held/policy) |
| `observation.request` | companion → plugin | lazy Level-1 inspect by purpose |
| `observation.result` | plugin → companion | `SemanticSceneV1` or stale/busy failure |

Coordinates may exist in the trusted envelope for audit. Model context may only
include the compact semantic summary from `companion.perception.model_safe_summary`.

Models never receive a raw command, RCON, shell, or unrestricted tool.
