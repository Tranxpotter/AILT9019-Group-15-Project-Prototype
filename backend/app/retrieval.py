"""Lightweight hybrid retrieval: BM25 over restaurant documents.

The index is built from the name, cuisine/tags, curated preference tags,
description, menu items and reviews. It complements the structured
preference-tag matching in `preferences.py`; together they form the hybrid
retrieval/ranking signal.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def restaurant_document(restaurant: dict) -> str:
    parts = [
        restaurant.get("name", ""),
        restaurant.get("cuisine", ""),
        " ".join(restaurant.get("cuisine_tags") or []),
        " ".join(restaurant.get("tags") or []),
        " ".join(restaurant.get("preference_tags") or []),
        restaurant.get("description", ""),
    ]
    parts += [item.get("name", "") for item in (restaurant.get("menu") or [])]
    parts += [item.get("description", "") for item in (restaurant.get("menu") or [])]
    parts += [review.get("comment", "") for review in (restaurant.get("reviews") or [])]
    return " ".join(parts)


def build_index(restaurants: Iterable[dict]) -> dict:
    docs = [tokenize(restaurant_document(r)) for r in restaurants]
    df = Counter()
    for doc in docs:
        df.update(set(doc))
    n = len(docs)
    idf = {
        term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
        for term, freq in df.items()
    }
    avgdl = (sum(len(doc) for doc in docs) / n) if n else 0.0
    return {"docs": docs, "idf": idf, "avgdl": avgdl, "n": n}


def bm25(
    query_terms: Iterable[str],
    doc_tokens: list[str],
    index: dict,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not query_terms or not doc_tokens or not index["avgdl"]:
        return 0.0
    score = 0.0
    doc_len = len(doc_tokens)
    for term in query_terms:
        tf = doc_tokens.count(term)
        if not tf:
            continue
        idf = index["idf"].get(term, 0.0)
        denom = tf + k1 * (1 - b + b * doc_len / index["avgdl"])
        score += idf * (tf * (k1 + 1)) / denom
    return score


def build_query_terms(p) -> list[str]:
    terms: list[str] = []
    for category in ("dish_intent", "texture", "vibe"):
        for item in getattr(p, category, []) or []:
            terms.extend(tokenize(item))
    terms.extend(tokenize(" ".join(p.keywords or [])))
    terms.extend(tokenize(" ".join(p.cuisines or [])))
    return list(dict.fromkeys(terms))
