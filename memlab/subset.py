"""Make a fixed, stratified subset of LongMemEval question ids.

    python -m memlab.subset --data data/longmemeval_s_cleaned.json --out subsets/dev42.json

Default: 6 questions from each of the six question types plus 6 abstention questions (42).
--total N instead samples N questions in proportion to the full set's type mix, and --exclude
leaves out the ids of another subset (e.g. a fresh dev100 that shares nothing with dev42):

    python -m memlab.subset --total 100 --exclude subsets/dev42.json --out subsets/dev100.json

The seed is fixed so every run of every system is measured on the same questions.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from .data import CATEGORIES, load_raw
from .io import read_json, write_json
from .io import utf8_stdout


def _by_category(raw: list[dict]) -> dict[str, list[str]]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for r in raw:
        qid = str(r["question_id"])
        by_cat["abstention" if qid.endswith("_abs") else r["question_type"]].append(qid)
    return by_cat


def proportional_counts(sizes: dict[str, int], total: int) -> dict[str, int]:
    """Split total across categories in proportion to their size (largest remainder)."""
    full = sum(sizes.values())
    exact = {c: total * n / full for c, n in sizes.items()}
    counts = {c: int(x) for c, x in exact.items()}
    for c in sorted(exact, key=lambda c: (round(exact[c] - counts[c], 9), sizes[c]), reverse=True)[: total - sum(counts.values())]:
        counts[c] += 1
    return counts


def make_subset(raw: list[dict], per_type: int, abstention: int, seed: int,
                total: int | None = None, exclude: set[str] | None = None) -> list[str]:
    by_cat = _by_category(raw)
    if total:
        counts = proportional_counts({c: len(by_cat.get(c, [])) for c in CATEGORIES}, total)
    else:
        counts = {c: abstention if c == "abstention" else per_type for c in CATEGORIES}
    rng = random.Random(seed)
    ids: list[str] = []
    for cat in CATEGORIES:
        pool = sorted(q for q in by_cat.get(cat, []) if q not in (exclude or set()))
        ids += rng.sample(pool, min(counts[cat], len(pool)))
    return ids


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/longmemeval_s_cleaned.json")
    ap.add_argument("--per-type", type=int, default=6)
    ap.add_argument("--abstention", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--total", type=int, default=None, help="sample this many, in the full set's type proportions")
    ap.add_argument("--exclude", nargs="*", default=[], help="subset JSON file(s) whose question ids must not be reused")
    ap.add_argument("--out", default="subsets/dev42.json")
    args = ap.parse_args(argv)
    exclude = {q for f in args.exclude for q in read_json(f)["question_ids"]}
    ids = make_subset(load_raw(args.data), args.per_type, args.abstention, args.seed, args.total, exclude)
    meta = {"source": Path(args.data).name, "seed": args.seed}
    if args.total:
        meta.update(total=args.total, proportional=True, excluded=args.exclude)
    else:
        meta.update(per_type=args.per_type, abstention=args.abstention)
    write_json(args.out, {**meta, "question_ids": ids})
    print(f"{len(ids)} question ids → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
