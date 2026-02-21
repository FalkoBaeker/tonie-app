from __future__ import annotations

import asyncio
import difflib
import html as html_lib
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import quote_plus, urlparse, urlunparse

import httpx

from app.core.config import settings
from app.services.ebay_api_client import ebay_api_enabled, search_item_summaries

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency guard
    BeautifulSoup = None


@dataclass
class MarketListing:
    source: str
    title: str
    price_eur: float
    url: str
    sold_at: datetime | None = None


_BUNDLE_KEYWORDS = {
    "bundle",
    "set",
    "paket",
    "konvolut",
    "sammlung",
    "lot",
    "mehrere",
}

_EXCLUDE_KEYWORDS = {
    "defekt",
    "kaputt",
    "ersatzteil",
    "reparatur",
    "fake",
    "fälschung",
    "faelschung",
    "leer",
    "hülle",
    "huelle",
    "hörspiel-cd",
    "hoerspiel-cd",
    "hörspiel cd",
    "hoerspiel cd",
    "kassette",
    "dvd",
    "blu-ray",
    "buch",
    "hardcover",
    "paperback",
    "taschenbuch",
    "comic",
    "hoerbuch",
    "hörbuch",
    "cd",
    "audio cd",
    "musik cd",
    "film",
    "roman",
    "mp3",
    "download",
}

_ACCESSORY_KEYWORDS = {
    "toniebox",
    "starterset",
    "ladestation",
    "tasche",
    "transportbox",
    "regal",
    "wandhalter",
    "aufbewahrung",
    "kopfhörer",
    "kopfhoerer",
    "akku",
    "netzteil",
}

_TONIE_CONTEXT_KEYWORDS = {
    "tonie",
    "tonies",
    "hoerfigur",
    "hörfigur",
    "horfigur",
}

_GENERIC_MATCH_TOKENS = {
    "tonie",
    "tonies",
    "toniebox",
    "figur",
    "figuren",
    "hoerfigur",
    "horfigur",
    "hoerspiel",
    "horspiel",
    "auswahl",
    "neu",
    "gebraucht",
    "set",
    "original",
    "echt",
    "der",
    "die",
    "das",
    "und",
    "mit",
    "von",
}

_DASH_SPLIT_RE = re.compile(r"\s+[–—-]\s+")

# Keep this list explicit/reviewable: these terms are high-signal non-figure media noise
# that frequently pollute classifieds query results for Tonies.
_OFFER_MEDIA_NOISE_KEYWORDS = {
    "cd",
    "audio cd",
    "hoerspiel cd",
    "hörspiel cd",
    "hoerbuch",
    "hörbuch",
    "buch",
    "hardcover",
    "paperback",
    "taschenbuch",
    "comic",
    "dvd",
    "blu ray",
    "blu-ray",
    "kassette",
    "vinyl",
    "schallplatte",
    "ebook",
}

_TONIE_REQUIRED_TERMS = ("tonie", "tonies", "hoerfigur", "hörfigur", "horfigur")

_EBAY_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

_BOT_PAGE_MARKERS = {
    "pardon our interruption",
    "automated access",
    "captcha",
    "enable javascript",
    "robot check",
}


def _normalize_token_text(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.lower()


def _parse_euro(raw: str) -> float | None:
    if not raw:
        return None

    txt = raw.replace("\xa0", " ").replace("EUR", "").replace("€", "")
    txt = txt.strip()
    lowered = txt.lower()

    # Typical listing ranges are not a single sold price and should be ignored.
    if " bis " in lowered or " to " in lowered:
        return None

    match = re.search(r"\d[\d. ]*(?:,\d{1,2})?", txt)
    if not match:
        return None

    token = match.group(0).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        value = float(token)
    except ValueError:
        return None

    if value < settings.market_price_min_eur or value > settings.market_raw_price_max_eur:
        return None

    return value


def _canonicalize_listing_url(raw_url: str) -> str:
    value = html_lib.unescape((raw_url or "").strip())
    if not value:
        return ""

    if value.startswith("//"):
        value = f"https:{value}"
    elif value.startswith("/"):
        value = f"https://www.ebay.de{value}"

    parsed = urlparse(value)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "www.ebay.de"
    path = parsed.path or "/"

    # Normalize item URLs to stable /itm/<id> shape to dedupe tracking params.
    item_match = re.search(r"/itm/(?:[^/]+/)?(\d{8,20})", path)
    if item_match:
        path = f"/itm/{item_match.group(1)}"

    return urlunparse((scheme, netloc, path, "", "", ""))


def _is_valid_listing_title(title: str, *, require_tonie_context: bool = True) -> bool:
    t = _normalize_token_text(title)

    if any(k in t for k in _EXCLUDE_KEYWORDS):
        return False

    if any(k in t for k in _ACCESSORY_KEYWORDS):
        return False

    # Enforce Tonie context to avoid generic media listings.
    if require_tonie_context and not any(k in t for k in _TONIE_CONTEXT_KEYWORDS):
        return False

    # Bundle detection heuristic.
    if any(k in t for k in _BUNDLE_KEYWORDS):
        return False

    # Avoid obvious multi-item titles like "2 Tonies", "3x", "10er" etc.
    if re.search(r"\b(?:[2-9]|[1-9]\d)\s*(?:x|er|stk|stück|stueck|tonies?)\b", t):
        return False

    return True


def _tokenize_for_match(text: str) -> set[str]:
    norm = _normalize_token_text(text)
    return {
        t
        for t in re.findall(r"[a-z0-9]+", norm)
        if len(t) >= 3 and t not in _GENERIC_MATCH_TOKENS
    }


def _is_relevant_to_query(title: str, query: str) -> bool:
    query_tokens = _tokenize_for_match(query)
    if not query_tokens:
        return False

    title_tokens = _tokenize_for_match(title)
    overlap = len(query_tokens & title_tokens)

    if len(query_tokens) <= 2:
        return overlap >= 1
    if len(query_tokens) <= 4:
        return overlap >= 2
    return overlap >= 3


def _target_overlap_score(title: str, target: str) -> tuple[int, int, float]:
    title_tokens = _tokenize_for_match(title)
    target_tokens = _tokenize_for_match(target)
    if not title_tokens or not target_tokens:
        return 0, len(target_tokens), 0.0

    overlap = len(title_tokens & target_tokens)
    return overlap, len(target_tokens), overlap / max(1, len(target_tokens))


def _specific_tokens_for_tonie(
    *,
    tonie_title: str,
    aliases: Iterable[str] | None = None,
    series: str | None = None,
) -> set[str]:
    series_tokens = _tokenize_for_match(series or "")

    def _collect(value: str) -> set[str]:
        norm = _normalize_token_text(value)
        if not norm:
            return set()

        chunks = [norm]
        parts = [p.strip() for p in _DASH_SPLIT_RE.split(norm, maxsplit=1) if p.strip()]
        if len(parts) == 2:
            chunks.append(parts[1])

        tokens: set[str] = set()
        for chunk in chunks:
            tokens |= _tokenize_for_match(chunk)

        return {t for t in tokens if t not in series_tokens}

    out = _collect(tonie_title)
    for alias in aliases or []:
        out |= _collect(str(alias))

    return out


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_token_text(phrase).strip()
    if not normalized_phrase:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def is_relevant_offer_title_for_tonie(
    *,
    offer_title: str,
    tonie_title: str,
    aliases: Iterable[str] | None = None,
    series: str | None = None,
    require_tonie_context: bool = True,
) -> bool:
    normalized_offer = _normalize_token_text(offer_title)
    if not normalized_offer:
        return False

    # Explicit Tonie context terms are required for classifieds offer data.
    if require_tonie_context and not any(_contains_phrase(normalized_offer, term) for term in _TONIE_REQUIRED_TERMS):
        return False

    if any(_contains_phrase(normalized_offer, k) for k in _OFFER_MEDIA_NOISE_KEYWORDS):
        return False

    offer_tokens = _tokenize_for_match(normalized_offer)
    specific_tokens = _specific_tokens_for_tonie(
        tonie_title=tonie_title,
        aliases=aliases,
        series=series,
    )
    specific_hit = bool(offer_tokens & specific_tokens) if specific_tokens else True

    target_candidates: list[str] = [tonie_title]
    if series:
        target_candidates.append(series)
        target_candidates.append(f"{series} {tonie_title}")
    for alias in aliases or []:
        target_candidates.append(str(alias))

    # Title relevance gate:
    # 1) token overlap threshold per candidate target, then
    # 2) fuzzy fallback to support punctuation/word-order variants.
    for target in target_candidates:
        target_norm = _normalize_token_text(str(target))
        if not target_norm:
            continue

        if target_norm in normalized_offer and specific_hit:
            return True

        overlap, target_size, overlap_ratio = _target_overlap_score(normalized_offer, target_norm)
        overlap_match = False
        if target_size <= 2 and overlap >= 1:
            overlap_match = True
        elif target_size <= 4 and overlap >= 2:
            overlap_match = True
        elif target_size >= 5 and (overlap >= 3 or overlap_ratio >= 0.55):
            overlap_match = True

        if overlap_match and specific_hit:
            return True

        fuzzy = difflib.SequenceMatcher(a=normalized_offer, b=target_norm).ratio()
        if fuzzy >= 0.78 and overlap >= 1 and specific_hit:
            return True

    return False


def filter_market_records_for_tonie(
    *,
    records: list[dict],
    tonie_title: str,
    aliases: Iterable[str] | None = None,
    series: str | None = None,
    sources: set[str] | None = None,
    require_tonie_context_sources: set[str] | None = None,
) -> list[dict]:
    """Filter polluted offer records for one Tonie target.

    Only records from `sources` are filtered; all other sources pass through unchanged.
    """
    scoped_sources = {s.lower() for s in (sources or {"kleinanzeigen_offer"})}
    context_sources = {
        s.lower() for s in (require_tonie_context_sources or {"kleinanzeigen_offer", "ebay_api_listing", "ebay_sold"})
    }
    out: list[dict] = []

    for row in records:
        source = str(row.get("source") or "").strip().lower()
        if source not in scoped_sources:
            out.append(row)
            continue

        title = str(row.get("title") or "").strip()
        if not title:
            continue

        if is_relevant_offer_title_for_tonie(
            offer_title=title,
            tonie_title=tonie_title,
            aliases=aliases,
            series=series,
            require_tonie_context=source in context_sources,
        ):
            out.append(row)

    return out


def _normalize_search_query(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value or "")
    cleaned = cleaned.replace("&", " und ")
    cleaned = re.sub(r"[–—]", " ", cleaned)
    cleaned = re.sub(r"[\[\](){},;:!?\"']", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_ebay_search_queries(
    *,
    title: str,
    aliases: Iterable[str] | None = None,
    series: str | None = None,
    limit: int = 8,
) -> list[str]:
    """Build stable query variants for a Tonie title.

    Goal: improve sold-listing recall (especially for titles with punctuation/long dashes)
    while keeping query count bounded for refresh performance.
    """

    ordered_base: list[str] = []

    def _append_base(candidate: str) -> None:
        normalized = _normalize_search_query(candidate)
        if not normalized:
            return
        if normalized in ordered_base:
            return
        ordered_base.append(normalized)

    _append_base(title)

    title_norm = _normalize_search_query(title)
    parts = [p.strip() for p in _DASH_SPLIT_RE.split(title_norm, maxsplit=1) if p.strip()]
    if len(parts) == 2:
        left, right = parts
        # More specific content title without franchise prefix.
        _append_base(right)
        # Keep franchise context but without punctuation noise.
        _append_base(f"{left} {right}")
    elif len(parts) == 1:
        _append_base(parts[0])

    if series:
        _append_base(series)

    for alias in aliases or []:
        _append_base(alias)

    out: list[str] = []

    def _append_query(candidate: str) -> None:
        value = candidate.strip()
        if not value:
            return
        if value in out:
            return
        out.append(value)

    for base in ordered_base:
        # Prefer Tonie-context searches first (higher recall on ebay sold pages).
        base_norm = _normalize_token_text(base)
        has_tonie_context = any(tok in base_norm for tok in {"tonie", "tonies", "hoerfigur", "horfigur", "hörfigur"})

        if not has_tonie_context:
            _append_query(f"{base} Tonie")
        _append_query(base)

    return out[: max(1, int(limit))]


def _strip_html(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", value)
    cleaned = html_lib.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_cards_with_regex(html: str) -> list[MarketListing]:
    out: list[MarketListing] = []

    card_pattern = re.compile(
        r"<li[^>]*class=(?:\"[^\"]*(?:s-card|s-item)[^\"]*\"|'[^']*(?:s-card|s-item)[^']*')[^>]*>(.*?)</li>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for card_html in card_pattern.findall(html):
        title_match = re.search(
            r"<[^>]*class=[^>]*(?:s-card__title|s-item__title)[^>]*>(.*?)</[^>]+>",
            card_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        price_match = re.search(
            r"<[^>]*class=[^>]*(?:s-card__price|s-item__price)[^>]*>(.*?)</[^>]+>",
            card_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        link_tag = re.search(
            r"<a[^>]*class=[^>]*(?:s-card__link|s-item__link)[^>]*>",
            card_html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if not title_match or not price_match or not link_tag:
            continue

        title = _strip_html(title_match.group(1))
        if not title or title.lower() == "shop on ebay":
            continue
        if not _is_valid_listing_title(title):
            continue

        price = _parse_euro(_strip_html(price_match.group(1)))
        if price is None:
            continue

        href_match = re.search(
            r"href=(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))",
            link_tag.group(0),
            flags=re.IGNORECASE | re.DOTALL,
        )
        raw_url = next((g for g in href_match.groups() if g), "") if href_match else ""
        url = _canonicalize_listing_url(raw_url)
        if not url:
            continue

        out.append(
            MarketListing(
                source="ebay_sold",
                title=title,
                price_eur=price,
                url=url,
                sold_at=None,
            )
        )

    return out


def _extract_cards_from_ebay_html(html: str) -> list[MarketListing]:
    # Prefer BeautifulSoup when available; fallback to regex parsing when not.
    if BeautifulSoup is None:
        return _extract_cards_with_regex(html)

    soup = BeautifulSoup(html, "html.parser")
    out: list[MarketListing] = []

    for li in soup.select("li.s-card, li.s-item"):
        title_el = li.select_one(
            ".s-card__title .su-styled-text.primary, .s-card__title, .s-item__title"
        )
        price_el = li.select_one(".s-card__price, .s-item__price")
        link_el = li.select_one("a.s-card__link, a.s-item__link")

        if not title_el or not price_el or not link_el:
            continue

        title = title_el.get_text(" ", strip=True)
        if not title or title.lower() == "shop on ebay":
            continue
        if not _is_valid_listing_title(title):
            continue

        price = _parse_euro(price_el.get_text(" ", strip=True))
        if price is None:
            continue

        url = _canonicalize_listing_url(link_el.get("href") or "")
        if not url:
            continue

        out.append(
            MarketListing(
                source="ebay_sold",
                title=title,
                price_eur=price,
                url=url,
                sold_at=None,
            )
        )

    # In some anti-bot variants soup extraction can miss cards; fallback to regex if empty.
    if not out:
        return _extract_cards_with_regex(html)

    return out


def _extract_cards_from_kleinanzeigen_html(html: str) -> list[MarketListing]:
    out: list[MarketListing] = []

    card_pattern = re.compile(
        r"<article[^>]*class=(?:\"[^\"]*aditem[^\"]*\"|'[^']*aditem[^']*')[^>]*>(.*?)</article>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for card_html in card_pattern.findall(html):
        title_match = re.search(
            r"<a[^>]*class=(?:\"[^\"]*ellipsis[^\"]*\"|'[^']*ellipsis[^']*')[^>]*href=(?:\"([^\"]+)\"|'([^']+)')[^>]*>(.*?)</a>",
            card_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        price_match = re.search(
            r"<p[^>]*class=(?:\"[^\"]*aditem-main--middle--price-shipping--price[^\"]*\"|'[^']*aditem-main--middle--price-shipping--price[^']*')[^>]*>(.*?)</p>",
            card_html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if not title_match or not price_match:
            continue

        raw_href = next((g for g in title_match.groups()[:2] if g), "")
        raw_title = title_match.group(3)

        title = _strip_html(raw_title)
        if not title:
            continue
        if not _is_valid_listing_title(title, require_tonie_context=False):
            continue

        price = _parse_euro(_strip_html(price_match.group(1)))
        if price is None:
            continue

        url = raw_href.strip()
        if url.startswith("/"):
            url = f"https://www.kleinanzeigen.de{url}"
        url = _canonicalize_listing_url(url)
        if not url:
            continue

        out.append(
            MarketListing(
                source="kleinanzeigen_offer",
                title=title,
                price_eur=price,
                url=url,
                sold_at=None,
            )
        )

    return out


def _dedupe_listings(items: Iterable[MarketListing]) -> list[MarketListing]:
    seen_url: set[str] = set()
    seen_title_price: set[tuple[str, int]] = set()
    out: list[MarketListing] = []

    for it in items:
        url_key = _canonicalize_listing_url(it.url)
        if not url_key:
            continue
        if url_key in seen_url:
            continue

        title_price_key = (_normalize_token_text(it.title).strip(), int(round(it.price_eur * 100)))
        if title_price_key in seen_title_price:
            continue

        seen_url.add(url_key)
        seen_title_price.add(title_price_key)
        it.url = url_key
        out.append(it)

    return out


def _looks_like_bot_page(html: str) -> bool:
    if not html:
        return True

    lowered = html.lower()
    if any(marker in lowered for marker in _BOT_PAGE_MARKERS):
        return True

    # Very tiny responses are usually challenge/blocked placeholders.
    return len(lowered.strip()) < 2000


def _extract_ebay_api_price(item: dict) -> float | None:
    price_obj = item.get("price") or item.get("currentBidPrice") or {}
    if not isinstance(price_obj, dict):
        return None

    currency = str(price_obj.get("currency") or "").upper().strip()
    if currency and currency != "EUR":
        return None

    raw_value = price_obj.get("value")
    if raw_value is None:
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None

    if value < settings.market_price_min_eur or value > settings.market_raw_price_max_eur:
        return None

    return value


async def fetch_ebay_api_listings(
    query: str,
    max_items: int = 80,
) -> list[MarketListing]:
    """Fetch listing data via eBay Browse API (server-side OAuth)."""
    if not ebay_api_enabled():
        return []

    rows = await search_item_summaries(query=query, limit=max_items)

    out: list[MarketListing] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        title = str(row.get("title") or "").strip()
        if not title:
            continue
        if not _is_valid_listing_title(title):
            continue
        if not _is_relevant_to_query(title, query):
            continue

        price = _extract_ebay_api_price(row)
        if price is None:
            continue

        raw_url = str(row.get("itemWebUrl") or row.get("itemAffiliateWebUrl") or "")
        url = _canonicalize_listing_url(raw_url)
        if not url:
            continue

        out.append(
            MarketListing(
                source="ebay_api_listing",
                title=title,
                price_eur=price,
                url=url,
                sold_at=None,
            )
        )

    return _dedupe_listings(out)[: max(1, int(max_items))]


async def fetch_ebay_api_listings_multi_query(
    *,
    queries: Iterable[str],
    max_items: int = 80,
    per_query_max_items: int | None = None,
) -> list[MarketListing]:
    query_list = [q.strip() for q in queries if q and q.strip()]
    if not query_list:
        return []

    max_items = max(1, int(max_items))
    per_query_max = per_query_max_items if per_query_max_items is not None else max_items
    per_query_max = max(1, int(per_query_max))

    merged: list[MarketListing] = []

    for query in query_list:
        try:
            rows = await fetch_ebay_api_listings(
                query=query,
                max_items=per_query_max,
            )
        except Exception:
            continue

        if rows:
            merged.extend(rows)
            deduped = _dedupe_listings(merged)
            if len(deduped) >= max_items:
                return deduped[:max_items]

    return _dedupe_listings(merged)[:max_items]


async def fetch_ebay_sold_listings(
    query: str,
    max_items: int = 80,
    timeout_s: float = 15.0,
    retries: int = 2,
) -> list[MarketListing]:
    """
    Public-page scrape of ebay.de sold/completed listings.
    Prototype-grade (no bypass tricks): compliant-first request/parse flow.
    """
    q = quote_plus(query)
    url = (
        "https://www.ebay.de/sch/i.html"
        f"?_nkw={q}&LH_Complete=1&LH_Sold=1&_sop=13&rt=nc"
    )

    max_attempts = max(1, int(retries) + 1)

    for attempt in range(1, max_attempts + 1):
        headers = {
            "User-Agent": random.choice(_EBAY_USER_AGENTS),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.ebay.de/",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout_s,
                headers=headers,
            ) as client:
                resp = await client.get(url)

            if resp.status_code in {403, 429}:
                if attempt < max_attempts:
                    await asyncio.sleep(0.6 * attempt)
                    continue
                return []

            resp.raise_for_status()

            if _looks_like_bot_page(resp.text):
                if attempt < max_attempts:
                    await asyncio.sleep(0.6 * attempt)
                    continue
                return []

            raw = _extract_cards_from_ebay_html(resp.text)
            cleaned = _dedupe_listings(raw)

            # Safety > quantity: if relevance gate yields no matches, return empty list.
            relevant = [x for x in cleaned if _is_relevant_to_query(x.title, query)]
            return relevant[:max_items]
        except Exception:
            if attempt < max_attempts:
                await asyncio.sleep(0.6 * attempt)
                continue
            return []

    return []


async def fetch_ebay_sold_listings_multi_query(
    *,
    queries: Iterable[str],
    max_items: int = 80,
    timeout_s: float = 15.0,
    per_query_max_items: int | None = None,
) -> list[MarketListing]:
    """Fetch sold listings for multiple query variants and merge them safely.

    The first strong query often already gives enough data; we stop early once
    enough deduped listings are collected.
    """

    query_list = [q.strip() for q in queries if q and q.strip()]
    if not query_list:
        return []

    max_items = max(1, int(max_items))
    per_query_max = per_query_max_items if per_query_max_items is not None else max_items
    per_query_max = max(1, int(per_query_max))

    merged: list[MarketListing] = []

    for query in query_list:
        try:
            rows = await fetch_ebay_sold_listings(
                query=query,
                max_items=per_query_max,
                timeout_s=timeout_s,
            )
        except Exception:
            # Query-level failures are expected occasionally (rate limits/anti-bot); keep going.
            continue

        if rows:
            merged.extend(rows)
            deduped = _dedupe_listings(merged)
            if len(deduped) >= max_items:
                return deduped[:max_items]

    return _dedupe_listings(merged)[:max_items]


async def fetch_kleinanzeigen_listings(
    query: str,
    max_items: int = 60,
    timeout_s: float = 15.0,
) -> list[MarketListing]:
    encoded = quote_plus(query)
    url = f"https://www.kleinanzeigen.de/s-suchanfrage.html?keywords={encoded}"

    headers = {
        "User-Agent": random.choice(_EBAY_USER_AGENTS),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.kleinanzeigen.de/",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_s, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    raw = _extract_cards_from_kleinanzeigen_html(resp.text)
    cleaned = _dedupe_listings(raw)
    relevant = [x for x in cleaned if _is_relevant_to_query(x.title, query)]
    return relevant[: max(1, int(max_items))]


async def fetch_kleinanzeigen_listings_multi_query(
    *,
    queries: Iterable[str],
    max_items: int = 60,
    timeout_s: float = 15.0,
    per_query_max_items: int | None = None,
) -> list[MarketListing]:
    query_list = [q.strip() for q in queries if q and q.strip()]
    if not query_list:
        return []

    max_items = max(1, int(max_items))
    per_query_max = per_query_max_items if per_query_max_items is not None else max_items
    per_query_max = max(1, int(per_query_max))

    merged: list[MarketListing] = []

    for query in query_list:
        try:
            rows = await fetch_kleinanzeigen_listings(
                query=query,
                max_items=per_query_max,
                timeout_s=timeout_s,
            )
        except Exception:
            continue

        if rows:
            merged.extend(rows)
            deduped = _dedupe_listings(merged)
            if len(deduped) >= max_items:
                return deduped[:max_items]

    return _dedupe_listings(merged)[:max_items]


def apply_time_window(listings: list[MarketListing], days: int = 90) -> list[MarketListing]:
    """
    Keep entries within window only when sold_at exists.
    For sources without sold_at we keep them and rely on source freshness strategy.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    out: list[MarketListing] = []
    for l in listings:
        if l.sold_at is None or l.sold_at >= cutoff:
            out.append(l)
    return out
