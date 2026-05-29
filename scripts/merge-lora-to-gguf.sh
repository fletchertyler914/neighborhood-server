#!/usr/bin/env bash
set -euo pipefail

ADAPTER_DIR="${1:-models/lora/v1/adapter}"
OUT_GGUF="${2:-models/ollama/neighborhood-qwen2.5-7b_v1.gguf}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-${HOME}/src/llama.cpp}"
QUANT="${OLLAMA_QUANT:-Q4_K_M}"

mkdir -p "$(dirname "$OUT_GGUF")"

if [[ ! -d "$ADAPTER_DIR" ]]; then
  echo "adapter dir not found: $ADAPTER_DIR" >&2
  exit 2
fi

CONVERT="${LLAMA_CPP_DIR}/convert_lora_to_gguf.py"
if [[ ! -f "$CONVERT" ]]; then
  CONVERT="${LLAMA_CPP_DIR}/convert-lora-to-gguf.py"
fi
if [[ ! -f "$CONVERT" ]]; then
  cat >&2 <<EOF
llama.cpp converter not found.

Install/build llama.cpp, then run:
  git clone https://github.com/ggerganov/llama.cpp "$LLAMA_CPP_DIR"
  python3 -m pip install -r "$LLAMA_CPP_DIR/requirements.txt"

Expected one of:
  $LLAMA_CPP_DIR/convert_lora_to_gguf.py
  $LLAMA_CPP_DIR/convert-lora-to-gguf.py
EOF
  exit 3
fi

RAW_GGUF="${OUT_GGUF%.gguf}.raw.gguf"
python3 "$CONVERT" "$ADAPTER_DIR" --outfile "$RAW_GGUF"

QUANT_BIN="${LLAMA_CPP_DIR}/build/bin/llama-quantize"
if [[ ! -x "$QUANT_BIN" ]]; then
  QUANT_BIN="${LLAMA_CPP_DIR}/quantize"
fi
if [[ -x "$QUANT_BIN" ]]; then
  "$QUANT_BIN" "$RAW_GGUF" "$OUT_GGUF" "$QUANT"
else
  cp "$RAW_GGUF" "$OUT_GGUF"
  echo "quantize binary not found; wrote unquantized GGUF to $OUT_GGUF" >&2
fi

echo "$OUT_GGUF"
