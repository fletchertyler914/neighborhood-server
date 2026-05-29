# Fine-Tuning Loop (SFT + DPO)

Continuous improvement pipeline fed by corpus pass/fail signals and `/agent good|bad`
feedback.

## End-to-end flow

```text
make corpus           → data/corpus-runs/<ts>/report.json + envelopes.jsonl
make triage           → triage.md (failure buckets + fix hints)
make feedback-report  → count /agent good|bad rows captured so far
make training-data    → corpus + feedback → datasets/sft/train.jsonl + datasets/preferences/train.jsonl
make train            → dry-run LoRA wiring against merged qwen2.5 data
make train-full       → real LoRA → GGUF → ollama create neighborhood-qwen2.5-7b:v1
make deploy-model     → set OLLAMA_MODEL and compare trained qwen2.5 vs stock qwen2.5
```

## Dataset formats

**SFT** (`datasets/sft/corpus.jsonl`):

```json
{"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", "tool_calls": [...]}, {"role": "tool", ...}], "meta": {...}}
```

**DPO** (`datasets/preferences/corpus.jsonl`):

```json
{"prompt": "build a cabin", "chosen": [...], "rejected": [...], "meta": {...}}
```

DPO pairs are built when the same prompt (cluster key) has both passing and
failing traces — typically after `sample-diverse` resamples failures at
temperatures `0.0`, `0.3`, `0.7`, or after players rate related live jobs with
`/agent good` and `/agent bad <reason>`.

## LoRA training

Requires optional deps:

```bash
pip install torch transformers peft trl datasets accelerate bitsandbytes
```

Dry-run (no GPU, validates paths):

```bash
AGENT_TRAIN_DRY_RUN=1 python -m agent.training lora-finetune --dry-run
```

Full train (CUDA 4-bit or MPS bf16 autodetected):

```bash
python -m agent.training lora-finetune \
  --sft datasets/sft/corpus.jsonl \
  --dpo datasets/preferences/corpus.jsonl \
  --out models/lora/v1
```

Defaults: base `Qwen/Qwen2.5-7B-Instruct`, LoRA r=16, 1 epoch SFT + 1 epoch DPO.

## Ollama registration

Merge adapter → GGUF (llama.cpp), then:

```bash
python -m agent.training ollama-register \
  --gguf models/ollama/neighborhood-q4.gguf \
  --model-name neighborhood-qwen2.5-7b:v1
```

Set in `.env`:

```bash
OLLAMA_MODEL=neighborhood-qwen2.5-7b:v1
```

Stock `qwen2.5:7b-instruct` remains the live default. The promotion gate is now
strictly stock qwen2.5 vs `neighborhood-qwen2.5-7b:v1`; other off-the-shelf
models were rejected during May 2026 screening.

## Strategy: eval-first, fine-tune later

Through May 2026 we found that nearly every "model failure" surfaced by the
corpus traced back to evaluation harness bugs: stale absolute coordinates from
prior cells, sandbox cleared the floor under the player, animal-pen prompts
mis-routed to generic templates, and tool-execution failures mis-classified
as `world_state_wrong`. Fixing those harness issues moved targeted categories
from `22/40` and `28/50` passes to `40/40` and `46/50` without touching the
model. Until corpus + probes are clean, fine-tuning would mostly memorize
harness noise.

The pipeline (corpus → triage → SFT/DPO export → LoRA → ollama register →
compare) is wired end-to-end so we can flip to training the moment we have
real model failures left to fix.

## Baseline (May 2026)

After triage fixes (float coord coercion, UUID player bind, build-anchor
inference, sandbox safe-pad, animal-pen routing):

| Run | Scope | Pass rate | Notes |
| --- | --- | --- | --- |
| `20260528T223140Z` | `corpus-quick` (30) | **100%** | Adversarial slice only |
| Full corpus | 612 prompts | **89.2%** single run; **96.4%** merged best-of with failed-case rerun |
| `audit_*_shape` | shape category (40) | **40/40** | Up from 22/40 after sandbox + grounding fixes |
| `audit_*_animal_pen` | animal_pen category (50) | **46/50** | Up from 28/50 after pen routing + default block fixes |

**Train dry-run (`models/lora/v1/`):** 15 SFT rows from quick run, 0 DPO pairs
(all quick-run cases passed — run `sample-diverse` after a corpus with failures).

**Model decision:** keep stock `qwen2.5:7b-instruct` live. It scored **51/51**
on a corrected balanced corpus sample. `llama3.1:8b` and `qwen2.5-coder:7b`
failed primarily by returning no tool calls; `deepseek-r1:8b` was disqualified
on latency after needing several minutes per prompt even with prompt-mode tool
fallback. `qwen2.5:3b-instruct` was faster but degraded info-query and
multi-step build accuracy and increased `server_error` rates, so the 7B stays.

**`neighborhood-qwen2.5-7b:v1`:** promotion pending real LoRA + GGUF merge.
`make compare-models` compares only stock qwen2.5 and the trained qwen2.5 tag,
and now reports p50 / p90 / mean / total latency per model so a "wins on
quality but doubles latency" regression cannot sneak through.

## Feedback loop (in-game)

Players rate jobs with `/agent good` and `/agent bad <reason>`. Export with:

```bash
make feedback-export
```

`make training-data` merges feedback exports with corpus exports into:

- `datasets/sft/train.jsonl`
- `datasets/preferences/train.jsonl`

These merged files are the default inputs for `make train` and
`make train-full`.

## Hardware notes

| Backend | Notes |
| --- | --- |
| CUDA + 4-bit | Recommended for 7B full LoRA |
| Apple MPS | bf16, smaller batch; use `--max-samples` for smoke |
| CPU | Dry-run only; not practical for 7B training |
