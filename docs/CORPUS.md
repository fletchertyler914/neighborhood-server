# NL Corpus Eval

The corpus is the source of truth for **NL → Intent → Tools → World state**. Every
prompt runs through the live orchestrator and LLM, mutates the world, and is
probed via RCON.

## Layout

```
agent/eval/corpus/
  *.yaml              # 612 prompts across 17 category files
  generate_corpus.py  # Regenerate YAML from intent templates
agent/eval/corpus_case.py
agent/eval/corpus_loader.py
agent/eval/corpus_runner.py
agent/eval/probes.py
agent/eval/triage.py
data/corpus-runs/<ts>/
  report.json
  envelopes.jsonl
  triage.md
```

## Quick commands

```bash
make generate-corpus   # rebuild YAML from templates (~612 cases)
make corpus-quick      # 30 prompts, live world (needs player online)
make corpus            # full corpus (~612 prompts, ~3h)
make triage            # cluster failures → triage.md
make corpus-export     # SFT + DPO JSONL from latest run
make corpus-baseline   # snapshot pass rate → agent/eval/corpus/baseline.json
```

## Authoring a case

```yaml
- id: house.cabin.casual.001
  category: house
  intent: build_small_cabin
  language_style: casual
  prompt: "yo gimme a tiny log cabin in front of me"
  expect:
    status: done
    max_steps: 14
    tool_any:
      - name: paste_template_at_player
        arguments_any:
          - { template_id: cabin_log }
      - name: build_house_at_player
    world_probe:
      kind: template_built
      anchor: player_forward
      sample_blocks: [oak_log, oak_planks]
      min_matches: 2
```

### `world_probe.kind`

| Kind | Validates |
| --- | --- |
| `template_built` | Sample blocks from schematic palette near anchor |
| `shape_built` | Platform / cylinder / sphere geometry |
| `mob_count` | Entities near anchor |
| `shaft_dug` | Air column below player |
| `setting` | Time / weather after admin tool |
| `inventory_has` | Item in player inventory |
| `none` | Skip world probe (info / multi-step / adversarial) |

## Sandbox

Cases run in an isolated grid starting at `(10000, -60, 10000)` with 48-block
stride. For each case the runner:

1. Teleports the player one block above the cell center to load the chunk.
2. Clears the cell box (`clear_box`) in `/fill` chunks below vanilla's block
   modification limit.
3. Restores a flat floor across the whole cell (`dirt` under `grass_block`) so
   eval runs do not leave void holes in the flat world.
4. Re-teleports the player onto the restored floor and waits for position settle
   before sending the prompt.
5. After the case, clears the expanded vertical build volume and restores the
   flat floor again.

`report.json` includes per-case `latency_ms` and a global `latency` block with
`p50_ms`, `p90_ms`, `mean_ms`, and `total_s` so timing regressions show up
alongside pass-rate ones.

## Environment

| Variable | Purpose |
| --- | --- |
| `AGENT_CORPUS_PLAYER` | Player name (auto-detected if online) |
| `AGENT_CORPUS_LIMIT` | Cap cases (dev/CI) |
| `AGENT_CORPUS_CATEGORY` | Filter to one category |
| `AGENT_EVAL_ALLOW_WORLD_MUTATION` | Required (set by Makefile) |

## Baseline

After a green run, save summary to `agent/eval/corpus/baseline.json` for regression
tracking on pass rate by category.

## Failure classification

`assert_corpus_expect` orders failures so the *cause* shows up in
`primary_failure`, not the symptom. When a tool returns `ok=False`
(`That position is not loaded`, schema validation failure, etc.) the case is
classified as `server_error` / `template_unresolved` even if the world probe
also failed because nothing was built — a tool that errored is the real
story. World-probe-only failures (e.g. wrong palette, missing target block)
remain `world_state_wrong`.
