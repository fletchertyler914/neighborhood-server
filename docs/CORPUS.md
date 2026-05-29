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
stride. Each cell is cleared before and after the case.

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
