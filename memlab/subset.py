"""Make a fixed, stratified subset of LongMemEval question ids.

    python -m memlab.subset --data data/longmemeval_s_cleaned.json --out subsets/dev42.json

Default: 6 questions from each of the six question types plus 6 abstention questions (42).
The seed is fixed so every run of every system is measured on the same questions.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from .data import CATEGORIES, load_raw
from .io import write_json
from .io import utf8_stdout


def make_subset(raw: list[dict], per_type: int, abstention: int, seed: int) -> list[str]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in raw:
        qid = str(r["question_id"])
        by_cat["abstention" if qid.endswith("_abs") else r["question_type"]].append(qid)
    rng = random.Random(seed)
    ids: list[str] = []
    for cat in CATEGORIES:
        n = abstention if cat == "abstention" else per_type
        pool = sorted(by_cat.get(cat, []))
        ids += rng.sample(pool, min(n, len(pool)))
    return ids


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/longmemeval_s_cleaned.json")
    ap.add_argument("--per-type", type=int, default=6)
    ap.add_argument("--abstention", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="subsets/dev42.json")
    args = ap.parse_args(argv)
    ids = make_subset(load_raw(args.data), args.per_type, args.abstention, args.seed)
    write_json(args.out, {"source": Path(args.data).name, "seed": args.seed, "per_type": args.per_type,
                          "abstention": args.abstention, "question_ids": ids})
    print(f"{len(ids)} question ids → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
