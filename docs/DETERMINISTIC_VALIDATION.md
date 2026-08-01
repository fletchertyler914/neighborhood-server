# Deterministic Validation Gates

The sidekick validates:

```text
player prompt -> route -> typed action -> plugin policy -> native execution -> world probe
```

The language-neutral contracts are in `protocol/`. Runtime route and model
outputs are validated with Pydantic; the Paper plugin independently validates
tool arguments and safety policy before execution.

`evals/release-gates.yaml` defines the fixed accuracy, safety, and latency
floors. `evals/run_offline.py` evaluates 100 held-out language cases
sequentially against one resident model. Results include raw per-case routes,
arguments, latency, and failures.

Run:

```bash
make test
make metal-check
make perception-fast
make companion-gate
make elite-gate
```

Perception floors (synthetic scenes, fast/deep latency, stale observation,
claims, tick health) live under the `perception:` key in
`evals/release-gates.yaml`.

Live gates must inspect resulting world state. A successful command return is
not sufficient. Templates and contextual builds also require undo, stale-world
protection where applicable, and GriefPrevention checks.
