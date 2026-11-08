#!/usr/bin/env bash
# Download the cleaned LongMemEval files (Sept 2025 release) into data/.
#   longmemeval_s_cleaned.json  ~50 sessions (~115k tokens) of history per question
#   longmemeval_oracle.json     only the evidence sessions: "perfect retrieval" reading ceiling
# The ~1.5M-token _m file is optional: bash scripts/download_data.sh m
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
BASE="https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main"
files=(longmemeval_s_cleaned.json longmemeval_oracle.json)
[[ "${1:-}" == "m" ]] && files+=(longmemeval_m_cleaned.json)
for f in "${files[@]}"; do
  if [[ -s "data/$f" ]]; then echo "already have data/$f"; continue; fi
  echo "downloading $f ..."
  curl -L --fail --retry 3 -o "data/$f.part" "$BASE/$f"
  mv "data/$f.part" "data/$f"
done
ls -lh data/
