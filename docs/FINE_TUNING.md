# Fine-Tuning Loop (SFT + DPO)

Continuous improvement pipeline fed by corpus pass/fail signals and `/agent good|bad`
feedback.

## End-to-end flow

```text
make corpus          → data/corpus-runs/<ts>/report.json + envelopes.jsonl
make triage          → triage.md (failure buckets + fix hints)
python -m agent.training sample-diverse --run data/corpus-runs/latest
make corpus-export   → datasets/sft/corpus.jsonl + datasets/preferences/corpus.jsonl
make train           → models/lora/latest/ (dry-run by default)
python -m agent.training ollama-register --model-name neighborhood-qwen2.5-7b:v1
make compare-models  → data/corpus-runs/compare_report.md
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
temperatures `0.0`, `0.3`, `0.7`.

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

Stock `qwen2.5:7b-instruct` remains the safe default until compare-models shows
a win on your hardware.

## Baseline (May 2026)

After triage fixes (float coord coercion, UUID player bind):

| Run | Scope | Pass rate | Notes |
| --- | --- | --- | --- |
| `20260528T223140Z` | `corpus-quick` (30) | **100%** | Adversarial slice only |
| Full corpus | 612 prompts | **89.2%** single run (`20260529T003011Z`); **96.4%** merged best-of with failed-case rerun |

**Train dry-run (`models/lora/v1/`):** 15 SFT rows from quick run, 0 DPO pairs
(all quick-run cases passed — run `sample-diverse` after a corpus with failures).

**`neighborhood-qwen2.5-7b:v1`:** registration pending GGUF merge (`make train`
prints llama.cpp one-liner). `make compare-models` skips missing Ollama tags and
compares only installed models.

## Feedback loop (in-game)

Players rate jobs with `/agent good` and `/agent bad <reason>`. Export with:

```bash
python -m agent.training feedback \
  --sft-out datasets/sft/from-feedback.jsonl \
  --dpo-out datasets/preferences/from-feedback.jsonl
```

Merge feedback JSONL with corpus JSONL before training for best results.

## Hardware notes

| Backend | Notes |
| --- | --- |
| CUDA + 4-bit | Recommended for 7B full LoRA |
| Apple MPS | bf16, smaller batch; use `--max-samples` for smoke |
| CPU | Dry-run only; not practical for 7B training |
