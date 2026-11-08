#!/usr/bin/env bash
# Stage 0: run the baselines on a fixed subset, grade them, and write results/REPORT.md.
# Shows a dry-run estimate first and asks before spending anything.
# Default backend keeps a few local Claude Code processes alive and clears the
# conversation between calls (subscription, no API credits). full_context on the _s data (~165k tokens per
# question) is the heavy upper reference, so it only runs when asked.
#
#   bash scripts/run_baselines.sh
#   FULL=1 bash scripts/run_baselines.sh           # also run full_context on the full history
#   BACKEND=api bash scripts/run_baselines.sh      # pay-per-token API (needs ANTHROPIC_API_KEY)
#   MODEL=claude-haiku-5-5 bash scripts/run_baselines.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8   # Windows consoles (cp949) cannot print some characters
export PYTHONUNBUFFERED=1     # show progress live even when output goes to a log file
BACKEND="${BACKEND:-claude-code-session}"

SUBSET="${SUBSET:-subsets/dev42.json}"
MODEL="${MODEL:-claude-sonnet-5-5}"
EFFORT="${EFFORT:-medium}"
S=data/longmemeval_s_cleaned.json
O=data/longmemeval_oracle.json

[[ -f "$S" && -f "$O" ]] || { echo "data missing: run  bash scripts/download_data.sh"; exit 1; }
[[ -f "$SUBSET" ]] || python -m memlab.subset --data "$S" --out "$SUBSET"

# name | system | data | extra params
RUNS=(
  "no_memory|no_memory|$S|"
  "raw_search_k10|raw_search|$S|--param top_k=10"
  "oracle_full|full_context|$O|"
)
[[ "${FULL:-0}" == "1" ]] && RUNS+=("full_context|full_context|$S|")

echo "== dry run (no API calls) =="
for r in "${RUNS[@]}"; do
  IFS='|' read -r name sys data extra <<<"$r"
  # shellcheck disable=SC2086
  python -m memlab.run --system "$sys" --data "$data" --subset "$SUBSET" --model "$MODEL" $extra --dry-run
done

[[ "$BACKEND" == "api" ]] || echo "(backend $BACKEND: the \$ figures are API-equivalent; nothing is billed, it uses the subscription's usage limit)"
read -r -p "Run these for real with $MODEL via $BACKEND? [y/N] " ok
[[ "$ok" == [yY] ]] || { echo "stopped before any model call"; exit 0; }
[[ "$BACKEND" != "api" || -n "${ANTHROPIC_API_KEY:-}" ]] || { echo "set ANTHROPIC_API_KEY first"; exit 1; }

for r in "${RUNS[@]}"; do
  IFS='|' read -r name sys data extra <<<"$r"
  name="$name@${MODEL#claude-}-$EFFORT"   # one result folder per model and effort, e.g. raw_search_k10@sonnet-5-5-medium
  # shellcheck disable=SC2086
  python -m memlab.run --system "$sys" --data "$data" --subset "$SUBSET" --model "$MODEL" \
    --effort "$EFFORT" --backend "$BACKEND" --name "$name" $extra
  python -m memlab.evaluate "results/$name" --judge-backend "$BACKEND"
done
python -m memlab.report results
