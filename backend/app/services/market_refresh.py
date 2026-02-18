from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from app.services.market_ingestion import (
    apply_time_window,
    build_ebay_search_queries,
    fetch_ebay_sold_listings_multi_query,
    fetch_kleinanzeigen_listings_multi_query,
)
from app.services.persistence import (
    create_refresh_run,
    init_db,
    prune_old_market_listings,
    save_market_listings,
    update_refresh_run,
)
from app.services.tonie_resolver import get_resolver

logger = logging.getLogger(__name__)


@dataclass
class RefreshState:
    run_id: str | None = None
    status: str = "idle"
    started_at: str | None = None
    finished_at: str | None = None

    total: int = 0
    processed: int = 0
    successful: int = 0
    failed: int = 0
    saved_rows: int = 0
    pruned_rows: int = 0

    limit: int | None = None
    delay_ms: int = 200
    max_items: int = 80

    failures: list[str] = field(default_factory=list)


_STATE = RefreshState()
_TASK: asyncio.Task | None = None
_LOCK = asyncio.Lock()


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _state_dict() -> dict:
    return deepcopy(
        {
            "run_id": _STATE.run_id,
            "status": _STATE.status,
            "started_at": _STATE.started_at,
            "finished_at": _STATE.finished_at,
            "total": _STATE.total,
            "processed": _STATE.processed,
            "successful": _STATE.successful,
            "failed": _STATE.failed,
            "saved_rows": _STATE.saved_rows,
            "pruned_rows": _STATE.pruned_rows,
            "limit": _STATE.limit,
            "delay_ms": _STATE.delay_ms,
            "max_items": _STATE.max_items,
            "failures": list(_STATE.failures),
        }
    )


def get_refresh_status() -> dict:
    return _state_dict()


def is_refresh_running() -> bool:
    return _is_running()


def _is_running() -> bool:
    return _TASK is not None and not _TASK.done()


async def _run_refresh(limit: int | None, delay_ms: int, max_items: int) -> dict:
    async with _LOCK:
        init_db()

        resolver = get_resolver()
        catalog = resolver.catalog[:limit] if limit and limit > 0 else resolver.catalog

        _STATE.run_id = uuid4().hex[:12]
        _STATE.status = "running"
        _STATE.started_at = _iso_now()
        _STATE.finished_at = None
        _STATE.total = len(catalog)
        _STATE.processed = 0
        _STATE.successful = 0
        _STATE.failed = 0
        _STATE.saved_rows = 0
        _STATE.pruned_rows = 0
        _STATE.limit = limit
        _STATE.delay_ms = max(0, delay_ms)
        _STATE.max_items = max(10, max_items)
        _STATE.failures = []

        logger.info(
            "Market refresh started run_id=%s total=%s limit=%s delay_ms=%s max_items=%s",
            _STATE.run_id,
            _STATE.total,
            _STATE.limit,
            _STATE.delay_ms,
            _STATE.max_items,
        )
        create_refresh_run(_state_dict())

        for idx, item in enumerate(catalog, start=1):
            tonie_id = str(item["id"])
            title = str(item["title"])

            try:
                queries = build_ebay_search_queries(
                    title=title,
                    aliases=item.get("aliases") or [],
                    series=item.get("series"),
                    limit=8,
                )

                ebay_result, kleinanzeigen_result = await asyncio.gather(
                    fetch_ebay_sold_listings_multi_query(
                        queries=queries,
                        max_items=_STATE.max_items,
                    ),
                    fetch_kleinanzeigen_listings_multi_query(
                        queries=queries,
                        max_items=min(60, _STATE.max_items),
                    ),
                    return_exceptions=True,
                )

                saved = 0

                if not isinstance(ebay_result, Exception):
                    listings = apply_time_window(ebay_result, days=90)
                    records = [
                        {
                            "title": l.title,
                            "price_eur": l.price_eur,
                            "url": l.url,
                            "sold_at": l.sold_at,
                        }
                        for l in listings
                        if l.price_eur > 0
                    ]
                    saved += save_market_listings(
                        tonie_id=tonie_id,
                        source="ebay_sold",
                        listings=records,
                    )
                else:
                    logger.debug(
                        "Market refresh ebay fetch failed run_id=%s tonie_id=%s error=%s",
                        _STATE.run_id,
                        tonie_id,
                        ebay_result,
                    )

                if not isinstance(kleinanzeigen_result, Exception):
                    listings = apply_time_window(kleinanzeigen_result, days=90)
                    records = [
                        {
                            "title": l.title,
                            "price_eur": l.price_eur,
                            "url": l.url,
                            "sold_at": l.sold_at,
                        }
                        for l in listings
                        if l.price_eur > 0
                    ]
                    saved += save_market_listings(
                        tonie_id=tonie_id,
                        source="kleinanzeigen_offer",
                        listings=records,
                    )
                else:
                    logger.debug(
                        "Market refresh kleinanzeigen fetch failed run_id=%s tonie_id=%s error=%s",
                        _STATE.run_id,
                        tonie_id,
                        kleinanzeigen_result,
                    )

                _STATE.saved_rows += saved
                _STATE.successful += 1
            except Exception as exc:  # noqa: BLE001
                _STATE.failed += 1
                _STATE.failures.append(f"{tonie_id}: {exc}")
                logger.warning(
                    "Market refresh item failed run_id=%s tonie_id=%s error=%s",
                    _STATE.run_id,
                    tonie_id,
                    exc,
                )

            _STATE.processed = idx

            if idx % 10 == 0 or idx == _STATE.total:
                logger.info(
                    "Market refresh progress run_id=%s processed=%s/%s successful=%s failed=%s",
                    _STATE.run_id,
                    _STATE.processed,
                    _STATE.total,
                    _STATE.successful,
                    _STATE.failed,
                )
                update_refresh_run(_state_dict())

            if _STATE.delay_ms > 0 and idx < _STATE.total:
                await asyncio.sleep(_STATE.delay_ms / 1000)

        _STATE.pruned_rows = prune_old_market_listings()
        _STATE.finished_at = _iso_now()
        _STATE.status = "completed_with_errors" if _STATE.failed else "completed"

        logger.info(
            "Market refresh finished run_id=%s status=%s processed=%s successful=%s failed=%s saved_rows=%s pruned_rows=%s",
            _STATE.run_id,
            _STATE.status,
            _STATE.processed,
            _STATE.successful,
            _STATE.failed,
            _STATE.saved_rows,
            _STATE.pruned_rows,
        )
        update_refresh_run(_state_dict())

        return _state_dict()


def start_refresh_background(limit: int | None, delay_ms: int, max_items: int) -> tuple[bool, dict, str]:
    global _TASK

    if _is_running():
        return False, _state_dict(), "refresh already running"

    _TASK = asyncio.create_task(_run_refresh(limit=limit, delay_ms=delay_ms, max_items=max_items))
    return True, _state_dict(), "refresh started"


async def run_refresh_now(limit: int | None, delay_ms: int, max_items: int) -> dict:
    if _is_running():
        raise RuntimeError("refresh already running")

    return await _run_refresh(limit=limit, delay_ms=delay_ms, max_items=max_items)
