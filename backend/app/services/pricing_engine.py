from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

from app.core.config import settings
from app.services.market_ingestion import (
    apply_time_window,
    build_ebay_search_queries,
    fetch_ebay_api_listings_multi_query,
    fetch_ebay_sold_listings_multi_query,
    fetch_kleinanzeigen_listings_multi_query,
)
from app.services.persistence import (
    get_market_listings,
    prune_old_market_listings,
    save_market_listings,
    save_pricing_event,
)
from app.services.pricing import CONDITION_FACTORS
from app.services.tonie_resolver import get_resolver

logger = logging.getLogger(__name__)


@dataclass
class EnginePriceResult:
    instant: float
    fair: float
    patience: float
    sample_size: int
    source: str
    effective_sample_size: float | None = None


def _quantile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile for sorted or unsorted values."""
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    xs = sorted(values)
    pos = (len(xs) - 1) * max(0.0, min(1.0, q))
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    w = pos - lo
    return float(xs[lo] * (1 - w) + xs[hi] * w)


def _weighted_quantile(points: list[tuple[float, float]], q: float) -> float:
    if not points:
        return 0.0

    cleaned = [
        (float(value), max(0.0, float(weight)))
        for value, weight in points
        if math.isfinite(value) and math.isfinite(weight)
    ]
    cleaned = [(value, weight) for value, weight in cleaned if weight > 0.0]

    if not cleaned:
        return 0.0
    if len(cleaned) == 1:
        return cleaned[0][0]

    q = max(0.0, min(1.0, q))
    xs = sorted(cleaned, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in xs)
    if total_weight <= 0:
        return _quantile([value for value, _ in xs], q)

    target = total_weight * q
    running = 0.0

    for idx, (value, weight) in enumerate(xs):
        prev_running = running
        running += weight

        if running >= target:
            if idx == 0:
                return value

            prev_value = xs[idx - 1][0]
            span = running - prev_running
            if span <= 0:
                return value

            local_q = (target - prev_running) / span
            local_q = max(0.0, min(1.0, local_q))
            return float(prev_value + (value - prev_value) * local_q)

    return xs[-1][0]


def _source_weight(source: str | None) -> float:
    default_weight = max(0.0, float(settings.market_default_source_weight))
    if not source:
        return default_weight

    key = source.strip().lower()
    if not key:
        return default_weight

    weights = {
        str(k).strip().lower(): float(v)
        for k, v in (settings.market_source_weights or {}).items()
    }

    return max(0.0, float(weights.get(key, default_weight)))


def _fallback_from_tonie(tonie_id: str, condition: str) -> EnginePriceResult:
    # Deterministic fallback while ingestion is unavailable.
    seed = (sum(ord(c) for c in tonie_id) % 1500) / 100 + 10
    factor = CONDITION_FACTORS.get(condition, CONDITION_FACTORS["good"])
    fair = round(seed * factor, 2)
    return EnginePriceResult(
        instant=round(fair * 0.85, 2),
        fair=fair,
        patience=round(fair * 1.15, 2),
        sample_size=0,
        source="fallback_no_live_market_data",
        effective_sample_size=0.0,
    )


def _result_from_prices(prices: list[float], condition: str, source: str) -> EnginePriceResult:
    q25 = _quantile(prices, 0.25)
    q50 = _quantile(prices, 0.50)
    q75 = _quantile(prices, 0.75)

    factor = CONDITION_FACTORS.get(condition, CONDITION_FACTORS["good"])
    return EnginePriceResult(
        instant=round(q25 * factor, 2),
        fair=round(q50 * factor, 2),
        patience=round(q75 * factor, 2),
        sample_size=len(prices),
        source=source,
        effective_sample_size=float(len(prices)),
    )


def _result_from_weighted_points(
    points: list[tuple[float, float]],
    *,
    condition: str,
    source: str,
    raw_sample_size: int,
    effective_sample_size: float,
) -> EnginePriceResult:
    q25 = _weighted_quantile(points, 0.25)
    q50 = _weighted_quantile(points, 0.50)
    q75 = _weighted_quantile(points, 0.75)

    factor = CONDITION_FACTORS.get(condition, CONDITION_FACTORS["good"])

    return EnginePriceResult(
        instant=round(q25 * factor, 2),
        fair=round(q50 * factor, 2),
        patience=round(q75 * factor, 2),
        sample_size=max(0, int(raw_sample_size)),
        source=source,
        effective_sample_size=round(max(0.0, float(effective_sample_size)), 2),
    )


def _clean_price_samples(raw_prices: list[float]) -> list[float]:
    bounded = sorted(
        p
        for p in raw_prices
        if math.isfinite(p)
        and settings.market_price_min_eur <= p <= settings.market_price_max_eur
    )
    if not bounded:
        return []

    # Small samples: keep as-is (IQR trimming would be unstable).
    if len(bounded) < 8:
        return bounded

    q1 = _quantile(bounded, 0.25)
    q3 = _quantile(bounded, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return bounded

    low = max(settings.market_price_min_eur, q1 - (settings.market_outlier_iqr_factor * iqr))
    high = min(settings.market_price_max_eur, q3 + (settings.market_outlier_iqr_factor * iqr))

    filtered = [p for p in bounded if low <= p <= high]

    # Avoid over-aggressive trimming: require enough data retention.
    min_keep = max(settings.market_min_samples, int(math.ceil(len(bounded) * 0.5)))
    return filtered if len(filtered) >= min_keep else bounded


def _weighted_points_from_records(
    records: list[dict],
) -> tuple[list[tuple[float, float]], int, float, set[str]]:
    prices_by_source: dict[str, list[float]] = defaultdict(list)

    for record in records:
        try:
            value = float(record.get("price_eur", 0))
        except (TypeError, ValueError):
            continue

        if value <= 0:
            continue

        source = str(record.get("source") or "unknown").strip().lower() or "unknown"
        prices_by_source[source].append(value)

    weighted_points: list[tuple[float, float]] = []
    used_sources: set[str] = set()
    raw_sample_size = 0
    effective_sample_size = 0.0

    for source, source_prices in prices_by_source.items():
        cleaned = _clean_price_samples(source_prices)
        if not cleaned:
            continue

        weight = _source_weight(source)
        if weight <= 0:
            continue

        used_sources.add(source)
        raw_sample_size += len(cleaned)
        effective_sample_size += len(cleaned) * weight
        weighted_points.extend((price, weight) for price in cleaned)

    return weighted_points, raw_sample_size, effective_sample_size, used_sources


def _try_cached_result(
    tonie_id: str,
    condition: str,
    *,
    max_age_minutes: int | None,
    source: str,
) -> EnginePriceResult | None:
    cached = get_market_listings(
        tonie_id=tonie_id,
        max_age_minutes=max_age_minutes,
        limit=400,
    )

    points, raw_sample_size, effective_sample_size, used_sources = _weighted_points_from_records(cached)
    if raw_sample_size < settings.market_min_samples:
        return None

    base_min_effective = max(0.1, float(settings.market_min_effective_samples))
    has_ebay = any(src.startswith("ebay") for src in used_sources)

    # Offer-only data gets a lower effective threshold for MVP coverage,
    # but still requires enough raw samples.
    min_effective = base_min_effective if has_ebay else max(1.5, base_min_effective * 0.45)
    if effective_sample_size < min_effective:
        return None

    if has_ebay and any(not src.startswith("ebay") for src in used_sources):
        result_source = f"{source}_blended_weighted"
    elif has_ebay:
        result_source = source
    else:
        result_source = f"{source}_offer_only_weighted"

    return _result_from_weighted_points(
        points,
        condition=condition,
        source=result_source,
        raw_sample_size=raw_sample_size,
        effective_sample_size=effective_sample_size,
    )


def _estimate_from_offer_prices(prices: list[float], condition: str) -> EnginePriceResult | None:
    cleaned = _clean_price_samples(prices)
    if len(cleaned) < max(4, settings.market_min_samples - 1):
        return None

    q25_offer = _quantile(cleaned, 0.25)
    q50_offer = _quantile(cleaned, 0.50)
    q75_offer = _quantile(cleaned, 0.75)

    # Marketplace offer prices usually include negotiation headroom.
    # Use a conservative adjustment with liquidity/volatility tuning.
    iqr = max(0.0, q75_offer - q25_offer)
    spread_ratio = iqr / max(1.0, q50_offer)

    negotiation_discount = 0.84
    liquidity_factor = min(1.0, 0.92 + (min(len(cleaned), 20) * 0.004))
    volatility_factor = max(0.86, 1.0 - min(0.5, spread_ratio) * 0.22)

    adjustment = negotiation_discount * liquidity_factor * volatility_factor

    adjusted_prices = [p * adjustment for p in cleaned]
    factor = CONDITION_FACTORS.get(condition, CONDITION_FACTORS["good"])

    return EnginePriceResult(
        instant=round(_quantile(adjusted_prices, 0.25) * factor, 2),
        fair=round(_quantile(adjusted_prices, 0.50) * factor, 2),
        patience=round(_quantile(adjusted_prices, 0.75) * factor, 2),
        sample_size=len(cleaned),
        source="kleinanzeigen_offer_estimate_v1",
        effective_sample_size=round(len(cleaned) * _source_weight("kleinanzeigen_offer"), 2),
    )


def _record_and_return(
    *,
    tonie_id: str,
    condition: str,
    result: EnginePriceResult,
    started: float,
) -> EnginePriceResult:
    latency_ms = max(0, int((perf_counter() - started) * 1000))

    try:
        save_pricing_event(
            tonie_id=tonie_id,
            condition=condition,
            source=result.source,
            sample_size=result.sample_size,
            latency_ms=latency_ms,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to persist pricing telemetry (tonie_id=%s)", tonie_id)

    if result.source == "fallback_no_live_market_data":
        logger.warning(
            "Pricing fallback used (tonie_id=%s condition=%s latency_ms=%s)",
            tonie_id,
            condition,
            latency_ms,
        )

    return result


async def compute_prices_for_tonie(tonie_id: str, condition: str) -> EnginePriceResult:
    started = perf_counter()

    resolver = get_resolver()
    item = next((x for x in resolver.catalog if x["id"] == tonie_id), None)
    if not item:
        return _record_and_return(
            tonie_id=tonie_id,
            condition=condition,
            result=_fallback_from_tonie(tonie_id, condition),
            started=started,
        )

    fresh_cached = _try_cached_result(
        tonie_id,
        condition,
        max_age_minutes=settings.market_cache_ttl_minutes,
        source="ebay_sold_cached_q25_q50_q75",
    )
    if fresh_cached:
        return _record_and_return(
            tonie_id=tonie_id,
            condition=condition,
            result=fresh_cached,
            started=started,
        )

    try:
        queries = build_ebay_search_queries(
            title=str(item.get("title") or ""),
            aliases=item.get("aliases") or [],
            series=item.get("series"),
            limit=8,
        )

        use_ebay_api_in_pricing = bool(
            settings.ebay_api_enabled
            and settings.ebay_api_include_in_pricing
            and not settings.ebay_api_shadow_mode
        )

        ebay_api_rows = []
        if settings.ebay_api_enabled:
            try:
                ebay_api_rows = await fetch_ebay_api_listings_multi_query(
                    queries=queries,
                    max_items=80,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("eBay API fetch failed (tonie_id=%s): %s", tonie_id, exc)

        ebay_api_records = [
            {
                "source": "ebay_api_listing",
                "title": l.title,
                "price_eur": l.price_eur,
                "url": l.url,
                "sold_at": l.sold_at,
            }
            for l in ebay_api_rows
            if settings.market_price_min_eur <= l.price_eur <= settings.market_price_max_eur
        ]

        if ebay_api_records:
            save_market_listings(
                tonie_id=tonie_id,
                source="ebay_api_listing",
                listings=[
                    {
                        "title": r["title"],
                        "price_eur": r["price_eur"],
                        "url": r["url"],
                        "sold_at": r["sold_at"],
                    }
                    for r in ebay_api_records
                ],
            )

            if use_ebay_api_in_pricing:
                api_points, api_raw_sample_size, api_effective_sample_size, _ = _weighted_points_from_records(
                    ebay_api_records
                )
                min_effective_api = max(0.1, float(settings.market_min_effective_samples))
                if (
                    api_raw_sample_size >= settings.market_min_samples
                    and api_effective_sample_size >= min_effective_api
                ):
                    api_result = _result_from_weighted_points(
                        api_points,
                        condition=condition,
                        source="ebay_api_live_weighted",
                        raw_sample_size=api_raw_sample_size,
                        effective_sample_size=api_effective_sample_size,
                    )
                    return _record_and_return(
                        tonie_id=tonie_id,
                        condition=condition,
                        result=api_result,
                        started=started,
                    )

        # Fallback to scrape-based acquisition when API data is unavailable/insufficient
        ebay_out, offer_out = await asyncio.gather(
            fetch_ebay_sold_listings_multi_query(
                queries=queries,
                max_items=80,
            ),
            fetch_kleinanzeigen_listings_multi_query(
                queries=queries,
                max_items=60,
            ),
            return_exceptions=True,
        )

        ebay_rows = []
        offer_rows = []

        if not isinstance(ebay_out, Exception):
            ebay_rows = apply_time_window(ebay_out, days=90)
        else:
            logger.debug("Live ebay scrape fetch failed (tonie_id=%s): %s", tonie_id, ebay_out)

        if not isinstance(offer_out, Exception):
            offer_rows = apply_time_window(offer_out, days=90)
        else:
            logger.debug("Live offer fetch failed (tonie_id=%s): %s", tonie_id, offer_out)

        ebay_records = [
            {
                "source": "ebay_sold",
                "title": l.title,
                "price_eur": l.price_eur,
                "url": l.url,
                "sold_at": l.sold_at,
            }
            for l in ebay_rows
            if settings.market_price_min_eur <= l.price_eur <= settings.market_price_max_eur
        ]
        offer_records = [
            {
                "source": "kleinanzeigen_offer",
                "title": l.title,
                "price_eur": l.price_eur,
                "url": l.url,
                "sold_at": l.sold_at,
            }
            for l in offer_rows
            if settings.market_price_min_eur <= l.price_eur <= settings.market_price_max_eur
        ]

        if ebay_records:
            save_market_listings(
                tonie_id=tonie_id,
                source="ebay_sold",
                listings=[
                    {
                        "title": r["title"],
                        "price_eur": r["price_eur"],
                        "url": r["url"],
                        "sold_at": r["sold_at"],
                    }
                    for r in ebay_records
                ],
            )

        if offer_records:
            save_market_listings(
                tonie_id=tonie_id,
                source="kleinanzeigen_offer",
                listings=[
                    {
                        "title": r["title"],
                        "price_eur": r["price_eur"],
                        "url": r["url"],
                        "sold_at": r["sold_at"],
                    }
                    for r in offer_records
                ],
            )

        if ebay_api_records or ebay_records or offer_records:
            prune_old_market_listings()

        sold_prices = _clean_price_samples([float(r["price_eur"]) for r in ebay_records])
        if len(sold_prices) >= settings.market_min_samples:
            live_result = _result_from_prices(
                sold_prices,
                condition=condition,
                source="ebay_sold_live_q25_q50_q75",
            )
            return _record_and_return(
                tonie_id=tonie_id,
                condition=condition,
                result=live_result,
                started=started,
            )

        live_records = ebay_records + offer_records
        if use_ebay_api_in_pricing and ebay_api_records:
            live_records = ebay_api_records + live_records

        points, raw_sample_size, effective_sample_size, used_sources = _weighted_points_from_records(live_records)
        has_ebay = any(src.startswith("ebay") for src in used_sources)

        min_effective = max(0.1, float(settings.market_min_effective_samples))
        if not has_ebay:
            min_effective = max(1.5, min_effective * 0.45)

        if raw_sample_size >= settings.market_min_samples and effective_sample_size >= min_effective:
            live_source = "market_live_blended_weighted" if has_ebay else "market_live_offer_only_weighted"
            live_weighted_result = _result_from_weighted_points(
                points,
                condition=condition,
                source=live_source,
                raw_sample_size=raw_sample_size,
                effective_sample_size=effective_sample_size,
            )
            return _record_and_return(
                tonie_id=tonie_id,
                condition=condition,
                result=live_weighted_result,
                started=started,
            )

        offer_estimate = _estimate_from_offer_prices(
            [float(r["price_eur"]) for r in offer_records],
            condition=condition,
        )
        if offer_estimate is not None:
            return _record_and_return(
                tonie_id=tonie_id,
                condition=condition,
                result=offer_estimate,
                started=started,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Live pricing fetch failed (tonie_id=%s)", tonie_id)

    stale_cached = _try_cached_result(
        tonie_id,
        condition,
        max_age_minutes=None,
        source="ebay_sold_cached_stale_q25_q50_q75",
    )
    if stale_cached:
        return _record_and_return(
            tonie_id=tonie_id,
            condition=condition,
            result=stale_cached,
            started=started,
        )

    return _record_and_return(
        tonie_id=tonie_id,
        condition=condition,
        result=_fallback_from_tonie(tonie_id, condition),
        started=started,
    )


def compute_prices_for_tonie_sync(tonie_id: str, condition: str) -> EnginePriceResult:
    return asyncio.run(compute_prices_for_tonie(tonie_id, condition))
