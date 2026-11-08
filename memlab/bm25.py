"""Minimal Okapi BM25 (no dependencies). Good enough to be the baseline to beat."""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an the and or but if of to in on at for with from by as is are was were be been being
    i me my mine we our you your he she him her it its they them their this that these those
    what which who whom when where why how do does did have has had not no so than too very
    can could will would should just about into over also there here then""".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        tokens = [tokenize(d) for d in docs]
        self.tf = [Counter(t) for t in tokens]
        self.doc_len = [len(t) for t in tokens]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 1.0
        df: Counter = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {term: math.log(1 + (n - c + 0.5) / (c + 0.5)) for term, c in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = set(tokenize(query))
        out = []
        for tf, dl in zip(self.tf, self.doc_len):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            for term in terms:
                f = tf.get(term)
                if f:
                    s += self.idf[term] * f * (self.k1 + 1) / (f + norm)
            out.append(s)
        return out
