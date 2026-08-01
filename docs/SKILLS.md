# Companion skills (OSS contribution unit)

Skills narrow prompt context and tool allowlists so a cheap local model can
drive `/agent` reliably.

## Layout

```text
skills/<id>/
  SKILL.md       # optional human docs
  tools.json     # allowlist of core tool names
  policy.yaml    # budgets / max_steps
  prompt.md      # domain prompt injected into the system message
```

Seed layout: `skills/core/` (default kid-facing prompt + full allowlist).

## Adding a skill

1. Create `skills/my_skill/` with `tools.json`, `policy.yaml`, and `prompt.md`.
2. Only list tools that exist in the greenfield companion contract
   (`companion/` + `docs/TOOL_CONTRACT.md`).
3. Wire selection in the companion router if needed.
4. Run `make test` and `make companion-gate`.

## Layers

| Layer | Module | Gate |
| --- | --- | --- |
| Contracts | `companion/` + tool registry | unit tests |
| Native dispatch | Paper plugin WebSocket gateway | live e2e |
| Offline gate | `make companion-gate` | accuracy + latency |
| Live e2e | `make companion-live` | world effects |
| Skills | this directory | extend after gates are green |

Legacy `agent/skills/` trees are soft-retired; see [DEPRECATED.md](DEPRECATED.md).
