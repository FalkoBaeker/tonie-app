from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process


@dataclass
class ResolverCandidate:
    tonie_id: str
    title: str
    score: float  # 0..1


@dataclass
class ResolverResult:
    status: str
    candidates: list[ResolverCandidate]


@dataclass
class _SearchEntry:
    tonie_id: str
    title: str
    norm: str
    tokens: frozenset[str]


_GENERIC_QUERY_TOKENS = {
    "tonie",
    "tonies",
    "toniebox",
    "figur",
    "figuren",
    "hoerfigur",
    "horfigur",
    "hoerspiel",
    "horspiel",
    "geschichte",
    "geschichten",
    "folge",
    "edition",
    "der",
    "die",
    "das",
    "dem",
    "den",
    "des",
    "ein",
    "eine",
    "einer",
    "und",
    "mit",
    "von",
    "fur",
    "fuer",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " und ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(norm_text: str) -> set[str]:
    return {t for t in norm_text.split() if len(t) >= 2}


def _informative_tokens(norm_text: str) -> set[str]:
    return {t for t in _tokens(norm_text) if t not in _GENERIC_QUERY_TOKENS}


def _token_overlap_score(query_tokens: set[str], candidate_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & candidate_tokens)
    if overlap <= 0:
        return 0.0

    # Emphasize how much of the query is covered by candidate terms.
    query_coverage = overlap / max(1, len(query_tokens))
    candidate_coverage = overlap / max(1, len(candidate_tokens))
    return round((query_coverage * 0.85) + (candidate_coverage * 0.15), 4)


class TonieResolver:
    def __init__(self, catalog: list[dict[str, Any]]):
        self.catalog = catalog
        self._entries: list[_SearchEntry] = []
        self._choice_norms: list[str] = []

        for item in catalog:
            title = item["title"]
            tonie_id = item["id"]
            aliases = item.get("aliases", [])
            series = item.get("series", "")

            variants = {title, *aliases}
            if series:
                variants.add(f"{series} {title}")

            for variant in variants:
                norm = _normalize(variant)
                if not norm:
                    continue

                self._entries.append(
                    _SearchEntry(
                        tonie_id=tonie_id,
                        title=title,
                        norm=norm,
                        tokens=frozenset(_informative_tokens(norm)),
                    )
                )

        self._choice_norms = [e.norm for e in self._entries]

    def _resolve_by_tonie_id(self, norm_query: str) -> ResolverResult | None:
        compact = norm_query.replace(" ", "")
        match = re.fullmatch(r"tn_?(\d{1,5})", compact)
        if not match:
            return None

        tonie_id = f"tn_{int(match.group(1)):03d}"
        item = next((x for x in self.catalog if x.get("id") == tonie_id), None)
        if not item:
            return ResolverResult(status="not_found", candidates=[])

        return ResolverResult(
            status="resolved",
            candidates=[ResolverCandidate(tonie_id=tonie_id, title=str(item["title"]), score=1.0)],
        )

    def _resolve_exact_variant(self, norm_query: str) -> ResolverResult | None:
        exact = [e for e in self._entries if e.norm == norm_query]
        if not exact:
            return None

        unique: dict[str, ResolverCandidate] = {}
        for entry in exact:
            unique[entry.tonie_id] = ResolverCandidate(
                tonie_id=entry.tonie_id,
                title=entry.title,
                score=1.0,
            )

        candidates = list(unique.values())
        if len(candidates) == 1:
            return ResolverResult(status="resolved", candidates=candidates)

        return ResolverResult(status="needs_confirmation", candidates=candidates)

    def resolve(self, query: str, limit: int = 5) -> ResolverResult:
        qn = _normalize(query)
        if not qn or len(qn) < 2:
            return ResolverResult(status="not_found", candidates=[])

        by_id = self._resolve_by_tonie_id(qn)
        if by_id is not None:
            return by_id

        exact = self._resolve_exact_variant(qn)
        if exact is not None:
            return exact

        query_tokens = _informative_tokens(qn)
        if not query_tokens:
            # Generic queries like "tonie" are too risky: avoid false positives.
            return ResolverResult(status="not_found", candidates=[])

        raw_matches = process.extract(
            qn,
            self._choice_norms,
            scorer=fuzz.WRatio,
            limit=max(limit * 10, 30),
        )

        by_tonie: dict[str, tuple[ResolverCandidate, float]] = {}

        for _, fuzzy_score_raw, idx in raw_matches:
            entry = self._entries[idx]
            fuzzy_score = float(fuzzy_score_raw) / 100.0
            overlap_score = _token_overlap_score(query_tokens, set(entry.tokens))

            # Hard reject clearly unrelated fuzzy hits.
            if overlap_score <= 0.0 and fuzzy_score < 0.93:
                continue
            if overlap_score < 0.34 and fuzzy_score < 0.88:
                continue

            combined = min(1.0, (fuzzy_score * 0.82) + (overlap_score * 0.18))
            candidate = ResolverCandidate(
                tonie_id=entry.tonie_id,
                title=entry.title,
                score=round(combined, 4),
            )

            previous = by_tonie.get(entry.tonie_id)
            if previous is None or candidate.score > previous[0].score:
                by_tonie[entry.tonie_id] = (candidate, overlap_score)

        ranked = sorted(by_tonie.values(), key=lambda item: item[0].score, reverse=True)
        candidates = [item[0] for item in ranked][:limit]

        if not candidates:
            return ResolverResult(status="not_found", candidates=[])

        top = candidates[0].score
        second = candidates[1].score if len(candidates) > 1 else 0.0
        top_overlap = ranked[0][1]

        if top < 0.60:
            return ResolverResult(status="not_found", candidates=[])

        # Require overlap for confidence (prevents wrong "best effort" prices).
        if top_overlap < 0.34 and top < 0.88:
            return ResolverResult(status="not_found", candidates=[])

        if len(candidates) == 1 and top >= 0.86:
            return ResolverResult(status="resolved", candidates=[candidates[0]])

        # Strong confidence only when best hit is high-quality and clearly ahead.
        if top >= 0.92 and (top - second) >= 0.06 and top_overlap >= 0.60:
            return ResolverResult(status="resolved", candidates=[candidates[0]])

        return ResolverResult(status="needs_confirmation", candidates=candidates)


@lru_cache(maxsize=1)
def get_resolver() -> TonieResolver:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    preferred = data_dir / "tonies_catalog.json"
    fallback = data_dir / "tonies_seed.json"

    data_path = preferred if preferred.exists() else fallback
    catalog = json.loads(data_path.read_text(encoding="utf-8"))
    return TonieResolver(catalog=catalog)
