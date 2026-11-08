"""Cut a large LongMemEval file down to the questions of one subset, without loading it whole.

    python -m memlab.extract --data data/longmemeval_m_cleaned.json --subset subsets/dev42.json \
        --out data/longmemeval_m_dev42.json

The _m file is ~2.7GB; json.load would need several times that in RAM. This streams it with
ijson (pip install ijson) and keeps only the wanted questions, in the same format, so every
other command can read the small file with --data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .io import read_json, utf8_stdout


def extract(data: str | Path, ids: set[str], out: str | Path) -> int:
    import ijson

    kept = []
    with open(data, "rb") as f:
        for q in ijson.items(f, "item", use_float=True):
            if str(q.get("question_id")) in ids:
                kept.append(q)
                if len(kept) == len(ids):
                    break
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False)
    return len(kept)


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--subset", required=True, nargs="+", help="one or more subset JSON files")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    ids = {q for s in args.subset for q in read_json(s)["question_ids"]}
    n = extract(args.data, ids, args.out)
    print(f"{n}/{len(ids)} questions → {args.out}")
    return 0 if n == len(ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
