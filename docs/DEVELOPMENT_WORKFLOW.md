# Sidekick Development Workflow

Every capability follows the same tight loop:

1. Add its held-out language, safety, postcondition, and latency cases.
2. Implement the smallest typed end-to-end slice.
3. Run focused unit and protocol tests.
4. Compile the Paper plugin.
5. Execute against the real Paper + FAWE sandbox.
6. Inspect trace timings and verified world state.
7. Fix the implementation, schema, router, prompt, or model.
8. Rerun focused tests and the full regression suite.

Useful commands:

```bash
make test
make metal-check
make companion-gate
make companion-deploy
docker compose logs -f mc-agent mc
```

Release floors are defined in `evals/release-gates.yaml`. Do not weaken a case
to make a change pass. Failed or flaky behavior becomes a permanent regression.

The runtime and plugin communicate only over the private authenticated
WebSocket. Do not publish port 8787 or add another execution path.
