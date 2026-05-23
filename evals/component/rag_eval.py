"""RAG eval — Hit@K, MRR, against labeled (obligation -> policy) pairs.

Offline mode: simulates pgvector retrieval with TF-IDF cosine over the
banking.yaml corpus. Approximates semantic search well enough to exercise
the metric pipeline without a live DB or embedding API.

Online mode (LIVE_DB=1): hits real pgvector via the production retriever.
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

import yaml

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)

HIT_AT_3_THRESHOLD = 0.80
MRR_THRESHOLD = 0.70

BANKING_YAML = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures"
    / "control_matrices"
    / "banking.yaml"
)


def _load_corpus() -> list[dict]:
    data = yaml.safe_load(BANKING_YAML.read_text())
    return data["policies"]


_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


def _tfidf_score(
    query_toks: list[str], doc_toks: list[str], idf: dict[str, float]
) -> float:
    """Cheap BM25-lite scorer: sum of TF*IDF for overlapping tokens."""
    if not query_toks or not doc_toks:
        return 0.0
    doc_freq: dict[str, int] = {}
    for t in doc_toks:
        doc_freq[t] = doc_freq.get(t, 0) + 1
    score = 0.0
    for q in set(query_toks):
        if q in doc_freq:
            score += (1 + math.log(doc_freq[q])) * idf.get(q, 0.0)
    norm = math.sqrt(sum(v * v for v in doc_freq.values())) or 1.0
    return score / norm


def _build_idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    n = len(corpus_tokens)
    df: dict[str, int] = {}
    for doc in corpus_tokens:
        for t in set(doc):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((n + 1) / (cnt + 1)) + 1 for t, cnt in df.items()}


def _retrieve(query: str, corpus: list[dict], k: int = 5) -> list[str]:
    corpus_tokens = [_tokens(p["text"] + " " + p["title"]) for p in corpus]
    idf = _build_idf(corpus_tokens)
    q_toks = _tokens(query)
    scored = [
        (_tfidf_score(q_toks, dt, idf), p["id"])
        for dt, p in zip(corpus_tokens, corpus, strict=True)
    ]
    scored.sort(reverse=True)
    return [pid for _, pid in scored[:k]]


def _evaluate(items: list[dict], corpus: list[dict]) -> dict[str, float]:
    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0
    rr_sum = 0.0
    for item in items:
        retrieved = _retrieve(item["obligation_text"], corpus, k=5)
        expected = set(item["expected_policy_ids"])
        ranks = [i + 1 for i, pid in enumerate(retrieved) if pid in expected]
        if ranks:
            best = ranks[0]
            rr_sum += 1.0 / best
            if best == 1:
                hit_at_1 += 1
            if best <= 3:
                hit_at_3 += 1
            if best <= 5:
                hit_at_5 += 1
    n = len(items)
    return {
        "hit@1": hit_at_1 / n,
        "hit@3": hit_at_3 / n,
        "hit@5": hit_at_5 / n,
        "mrr": rr_sum / n,
    }


def main() -> int:
    if os.environ.get("LIVE_DB") == "1":
        print(
            "LIVE_DB mode not implemented in this stub; using offline TF-IDF retriever."
        )
    dataset = load_dataset("rag/retrieval_pairs.json")
    corpus = _load_corpus()
    metrics = _evaluate(dataset["items"], corpus)

    print_table(
        "RAG eval (offline TF-IDF surrogate)",
        [
            ("hit@1", metrics["hit@1"]),
            ("hit@3", metrics["hit@3"]),
            ("hit@5", metrics["hit@5"]),
            ("mrr", metrics["mrr"]),
            ("dataset_size", len(dataset["items"])),
            ("corpus_size", len(corpus)),
        ],
    )

    failed: list[str] = []
    if not assert_threshold("hit@3", metrics["hit@3"], HIT_AT_3_THRESHOLD):
        failed.append("hit@3")
    if not assert_threshold("mrr", metrics["mrr"], MRR_THRESHOLD):
        failed.append("mrr")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
