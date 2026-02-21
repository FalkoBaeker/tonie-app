from datetime import UTC, datetime
from enum import Enum
from statistics import median

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.market_refresh import (
    get_refresh_status,
    run_refresh_now,
    start_refresh_background,
)
from app.services.external_auth import ExternalAuthError, verify_external_jwt
from app.services.persistence import (
    authenticate_user,
    create_session,
    create_user,
    create_watchlist_alert,
    delete_session,
    delete_watchlist_item,
    get_db_readiness,
    get_fresh_listing_counts,
    get_market_cache_status,
    get_market_coverage_report,
    get_market_listings,
    get_or_create_user_by_email,
    get_pricing_quality_status,
    get_user_by_token,
    list_refresh_runs,
    list_watchlist_alerts,
    list_watchlist_items,
    update_watchlist_item_price,
    upsert_watchlist_item,
)
from app.services.photo_recognition import (
    get_photo_recognition_status,
    recognize_tonie_from_image_bytes,
)
from app.services.pricing_engine import compute_prices_for_tonie
from app.services.tonie_resolver import get_resolver

router = APIRouter()


class ResolveRequest(BaseModel):
    query: str


class ResolveCandidate(BaseModel):
    tonie_id: str
    title: str
    score: float
    rarity_label: str | None = None


class ResolveResponse(BaseModel):
    status: str
    candidates: list[ResolveCandidate]


class RecognizeResponse(BaseModel):
    status: str
    candidates: list[ResolveCandidate]
    message: str | None = None


class RecognizeStatusResponse(BaseModel):
    ready: bool
    reference_count: int
    tonie_count: int
    generated_at: str | None
    message: str | None


class Condition(str, Enum):
    ovp = "ovp"
    new_open = "new_open"
    very_good = "very_good"
    good = "good"
    played = "played"
    defective = "defective"


class PricingResponse(BaseModel):
    tonie_id: str
    condition: Condition
    currency: str
    sofortverkaufspreis: float
    fairer_marktpreis: float
    geduldspreis: float
    sample_size: int
    effective_sample_size: float | None = None
    source: str
    quality_tier: str
    confidence_band: str
    confidence_score: float
    trend_direction: str
    trend_label: str
    trend_delta_pct: float | None = None
    rarity_label: str | None = None
    rarity_reason: str | None = None
    availability_state: str | None = None


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
    expires_at: str


class WatchlistAddRequest(BaseModel):
    tonie_id: str = Field(min_length=2)
    title: str | None = None
    condition: Condition = Condition.good
    target_price_eur: float | None = Field(default=None, gt=0)


class WatchlistItemResponse(BaseModel):
    id: int
    tonie_id: str
    title: str
    condition: Condition
    last_fair_price: float
    target_price_eur: float | None = None
    updated_at: str


class WatchlistAlertResponse(BaseModel):
    id: int
    watchlist_item_id: int
    tonie_id: str
    title: str
    condition: Condition
    alert_type: str
    message: str
    current_price_eur: float
    previous_price_eur: float | None = None
    target_price_eur: float | None = None
    is_read: bool
    created_at: str


class MarketCacheStatusResponse(BaseModel):
    tonie_id: str | None
    listing_count: int
    tonie_count: int
    latest_fetched_at: str | None
    fresh_window_minutes: int
    fresh_listing_count: int
    fresh_tonie_count: int


class MarketCoverageItemResponse(BaseModel):
    tonie_id: str
    title: str | None
    raw_samples: int
    effective_samples: float
    latest_fetched_at: str | None
    source_counts: dict[str, int]
    meets_target: bool


class MarketCoverageStatusResponse(BaseModel):
    fresh_window_minutes: int
    cutoff: str
    min_effective_samples: float
    total_tonies: int
    covered_tonies: int
    uncovered_tonies: int
    items: list[MarketCoverageItemResponse]


class PricingQualityFallbackItemResponse(BaseModel):
    tonie_id: str
    title: str | None
    requests: int
    avg_sample_size: float


class PricingQualityLowFreshItemResponse(BaseModel):
    tonie_id: str
    title: str
    fresh_listing_count: int
    latest_fetched_at: str | None


class PricingQualityStatusResponse(BaseModel):
    window_hours: int
    cutoff: str
    low_sample_threshold: int
    total_requests: int
    fallback_count: int
    fallback_rate: float
    live_count: int
    fresh_cache_count: int
    stale_cache_count: int
    low_sample_count: int
    avg_sample_size: float
    avg_latency_ms: float | None
    latest_event_at: str | None
    fallback_top: list[PricingQualityFallbackItemResponse]
    fresh_window_minutes: int
    low_fresh_threshold: int
    low_fresh_tonies: list[PricingQualityLowFreshItemResponse]


class MarketRefreshRequest(BaseModel):
    limit: int = Field(default=0, ge=0, le=5000)
    delay_ms: int = Field(default=200, ge=0, le=5000)
    max_items: int = Field(default=80, ge=10, le=200)
    background: bool = True


class MarketRefreshStatusResponse(BaseModel):
    run_id: str | None
    status: str
    started_at: str | None
    finished_at: str | None
    total: int
    processed: int
    successful: int
    failed: int
    saved_rows: int
    pruned_rows: int
    limit: int | None
    delay_ms: int
    max_items: int
    failures: list[str]


class MarketRefreshResponse(BaseModel):
    started: bool
    message: str
    status: MarketRefreshStatusResponse


class MarketRefreshRunsResponse(BaseModel):
    items: list[MarketRefreshStatusResponse]


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    if parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    return token if token else None


def _condition_from_raw(raw: str) -> Condition:
    try:
        return Condition(raw)
    except ValueError:
        return Condition.good


def _derive_pricing_quality(
    sample_size: int,
    source: str,
    effective_sample_size: float | None = None,
) -> tuple[str, float]:
    s = max(0, int(sample_size))
    effective = float(effective_sample_size) if effective_sample_size is not None else float(s)
    src = (source or "").lower()

    if src == "fallback_no_live_market_data":
        return "low", 0.15

    if src == "local_fallback":
        return "low", 0.05

    if "stale" in src:
        if effective >= 8:
            return "medium", 0.55
        return "low", 0.35

    if "offer_estimate" in src:
        if s >= 12:
            return "medium", min(0.72, 0.50 + min(s, 30) / 180.0)
        if s >= 6:
            return "medium", min(0.64, 0.45 + min(s, 20) / 220.0)
        return "low", min(0.48, 0.25 + min(s, 10) / 220.0)

    if "offer_only_weighted" in src:
        if effective >= 6:
            return "medium", min(0.68, 0.48 + min(effective, 20.0) / 180.0)
        return "low", min(0.5, 0.24 + min(effective, 10.0) / 200.0)

    if "blended_weighted" in src:
        if effective >= 12:
            return "high", min(0.94, 0.66 + min(effective, 40.0) / 120.0)
        if effective >= 5:
            return "medium", min(0.78, 0.42 + min(effective, 20.0) / 120.0)
        return "low", min(0.5, 0.2 + min(effective, 10.0) / 100.0)

    if "ebay" in src and effective >= 12:
        return "high", min(0.98, 0.70 + min(effective, 40.0) / 100.0)

    if "ebay" in src and effective >= 5:
        return "medium", min(0.8, 0.45 + min(effective, 20.0) / 100.0)

    return "low", min(0.5, 0.2 + min(max(effective, float(s)), 10.0) / 100.0)


def _quality_band_from_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    if t == "high":
        return "A"
    if t == "medium":
        return "B"
    return "C"


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _derive_price_trend(rows: list[dict]) -> tuple[str, str, float | None]:
    points: list[tuple[datetime, float]] = []
    for row in rows:
        try:
            price = float(row.get("price_eur") or 0.0)
        except (TypeError, ValueError):
            continue

        if price <= 0:
            continue

        dt = _parse_iso_datetime(str(row.get("fetched_at") or ""))
        if dt is None:
            continue

        points.append((dt, price))

    if len(points) < 4:
        return "right", "konstant", None

    points.sort(key=lambda item: item[0])
    prices = [price for _, price in points]
    split_at = len(prices) // 2
    older = prices[:split_at]
    newer = prices[split_at:]

    if not older or not newer:
        return "right", "konstant", None

    old_med = float(median(older))
    new_med = float(median(newer))
    if old_med <= 0:
        return "right", "konstant", None

    delta_pct = (new_med - old_med) / old_med

    if delta_pct >= 0.12:
        return "up", "steigend", round(delta_pct, 4)
    if delta_pct >= 0.03:
        return "up_right", "leicht steigend", round(delta_pct, 4)
    if delta_pct <= -0.12:
        return "down", "sinkend", round(delta_pct, 4)
    if delta_pct <= -0.03:
        return "down_right", "eher sinkend", round(delta_pct, 4)
    return "right", "konstant", round(delta_pct, 4)


def _derive_rarity(item: dict | None) -> tuple[str | None, str | None, str | None]:
    if not item:
        return None, None, None

    state = str(item.get("availability_state") or "").strip()
    lowered = state.lower()

    if lowered == "endoflife":
        return "Rarität", "Auf der Tonies-Seite als nicht mehr verfügbar/End of Life markiert.", state

    if lowered == "sold-out":
        return "Vermutlich bald Rarität", "Auf der Tonies-Seite als ausverkauft markiert.", state

    return None, None, state or None


def _watchlist_item_response(item: dict) -> WatchlistItemResponse:
    return WatchlistItemResponse(
        id=int(item["id"]),
        tonie_id=str(item["tonie_id"]),
        title=str(item["title"]),
        condition=_condition_from_raw(str(item["condition"])),
        last_fair_price=float(item["last_fair_price"]),
        target_price_eur=(
            float(item["target_price_eur"]) if item.get("target_price_eur") is not None else None
        ),
        updated_at=str(item["updated_at"]),
    )


def _watchlist_alert_response(item: dict) -> WatchlistAlertResponse:
    return WatchlistAlertResponse(
        id=int(item["id"]),
        watchlist_item_id=int(item["watchlist_item_id"]),
        tonie_id=str(item["tonie_id"]),
        title=str(item["title"]),
        condition=_condition_from_raw(str(item["condition"])),
        alert_type=str(item["alert_type"]),
        message=str(item["message"]),
        current_price_eur=float(item["current_price_eur"]),
        previous_price_eur=(
            float(item["previous_price_eur"]) if item.get("previous_price_eur") is not None else None
        ),
        target_price_eur=(
            float(item["target_price_eur"]) if item.get("target_price_eur") is not None else None
        ),
        is_read=bool(item.get("is_read", False)),
        created_at=str(item["created_at"]),
    )


def _market_refresh_status_response(data: dict) -> MarketRefreshStatusResponse:
    return MarketRefreshStatusResponse(
        run_id=data.get("run_id"),
        status=str(data.get("status") or "idle"),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
        total=int(data.get("total") or 0),
        processed=int(data.get("processed") or 0),
        successful=int(data.get("successful") or 0),
        failed=int(data.get("failed") or 0),
        saved_rows=int(data.get("saved_rows") or 0),
        pruned_rows=int(data.get("pruned_rows") or 0),
        limit=data.get("limit"),
        delay_ms=int(data.get("delay_ms") or 0),
        max_items=int(data.get("max_items") or 0),
        failures=[str(x) for x in (data.get("failures") or [])],
    )


def _pricing_quality_status_response(
    data: dict,
    *,
    fresh_minutes: int,
    low_fresh_threshold: int,
    low_fresh_limit: int,
) -> PricingQualityStatusResponse:
    resolver = get_resolver()
    title_by_id = {str(item["id"]): str(item["title"]) for item in resolver.catalog}

    fallback_items = [
        PricingQualityFallbackItemResponse(
            tonie_id=str(row.get("tonie_id") or ""),
            title=title_by_id.get(str(row.get("tonie_id") or "")),
            requests=int(row.get("requests") or 0),
            avg_sample_size=float(row.get("avg_sample_size") or 0.0),
        )
        for row in (data.get("fallback_top") or [])
    ]

    fresh_counts = get_fresh_listing_counts(fresh_minutes=fresh_minutes)
    low_fresh_rows = []
    for item in resolver.catalog:
        tonie_id = str(item["id"])
        fresh = fresh_counts.get(tonie_id) or {}
        fresh_listing_count = int(fresh.get("fresh_listing_count") or 0)
        if fresh_listing_count >= low_fresh_threshold:
            continue

        low_fresh_rows.append(
            PricingQualityLowFreshItemResponse(
                tonie_id=tonie_id,
                title=str(item["title"]),
                fresh_listing_count=fresh_listing_count,
                latest_fetched_at=fresh.get("latest_fetched_at"),
            )
        )

    low_fresh_rows.sort(
        key=lambda row: (
            row.fresh_listing_count,
            0 if row.latest_fetched_at is None else 1,
            row.latest_fetched_at or "",
            row.tonie_id,
        )
    )

    return PricingQualityStatusResponse(
        window_hours=int(data.get("window_hours") or 24),
        cutoff=str(data.get("cutoff") or ""),
        low_sample_threshold=int(data.get("low_sample_threshold") or 0),
        total_requests=int(data.get("total_requests") or 0),
        fallback_count=int(data.get("fallback_count") or 0),
        fallback_rate=float(data.get("fallback_rate") or 0.0),
        live_count=int(data.get("live_count") or 0),
        fresh_cache_count=int(data.get("fresh_cache_count") or 0),
        stale_cache_count=int(data.get("stale_cache_count") or 0),
        low_sample_count=int(data.get("low_sample_count") or 0),
        avg_sample_size=float(data.get("avg_sample_size") or 0.0),
        avg_latency_ms=(
            float(data.get("avg_latency_ms")) if data.get("avg_latency_ms") is not None else None
        ),
        latest_event_at=data.get("latest_event_at"),
        fallback_top=fallback_items,
        fresh_window_minutes=max(1, int(fresh_minutes)),
        low_fresh_threshold=max(1, int(low_fresh_threshold)),
        low_fresh_tonies=low_fresh_rows[: max(1, int(low_fresh_limit))],
    )


def _external_email_from_claims(claims: dict) -> str | None:
    raw_email = claims.get("email")
    if isinstance(raw_email, str) and raw_email.strip():
        return raw_email.strip().lower()

    sub = claims.get("sub")
    if isinstance(sub, str) and sub.strip():
        fallback = f"external_{sub.strip()}@external.local"
        return fallback.lower()

    return None


def _truthy_claim(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, int):
        return value == 1
    return False


def _is_verified_email(claims: dict) -> bool:
    # Supabase can emit email_verified either top-level or nested in user_metadata.
    if _truthy_claim(claims.get("email_verified")):
        return True

    user_metadata = claims.get("user_metadata")
    if isinstance(user_metadata, dict) and _truthy_claim(user_metadata.get("email_verified")):
        return True

    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, dict) and _truthy_claim(app_metadata.get("email_verified")):
        return True

    return False


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    token = _extract_bearer(authorization)

    if settings.auth_mode.strip().lower() == "external":
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

        try:
            claims = verify_external_jwt(token)
        except ExternalAuthError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        if settings.auth_require_verified_email and not _is_verified_email(claims):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="email not verified")

        email = _external_email_from_claims(claims)
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="external token missing email")

        user = get_or_create_user_by_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="external user provisioning failed")

        return user

    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return user


@router.get("/health")
async def health() -> dict:
    refresh = get_refresh_status()
    db = get_db_readiness()
    db_ok = bool(db.get("ok", False))

    return {
        "ok": db_ok,
        "status": "ok" if db_ok else "degraded",
        "reason": None if db_ok else (db.get("reason") or "db_not_ready"),
        "time": datetime.now(UTC).isoformat(),
        "db": {
            "ok": db_ok,
            "status": db.get("status") or ("ok" if db_ok else "degraded"),
            "reason": db.get("reason"),
            "sqlite_path": db.get("sqlite_path"),
        },
        "market_refresh": {
            "status": refresh.get("status"),
            "run_id": refresh.get("run_id"),
            "processed": refresh.get("processed"),
            "total": refresh.get("total"),
        },
    }


@router.get("/market/cache-status", response_model=MarketCacheStatusResponse)
async def market_cache_status(
    tonie_id: str | None = Query(default=None),
) -> MarketCacheStatusResponse:
    status_data = get_market_cache_status(tonie_id=tonie_id)
    return MarketCacheStatusResponse(**status_data)


@router.get("/market/coverage-status", response_model=MarketCoverageStatusResponse)
async def market_coverage_status(
    fresh_minutes: int = Query(default=settings.market_cache_ttl_minutes, ge=1, le=24 * 14 * 60),
    min_effective_samples: float = Query(default=settings.market_min_effective_samples, ge=0.1, le=1000),
    limit: int = Query(default=200, ge=1, le=1000),
) -> MarketCoverageStatusResponse:
    resolver = get_resolver()
    title_by_id = {str(item["id"]): str(item["title"]) for item in resolver.catalog}

    data = get_market_coverage_report(
        fresh_minutes=fresh_minutes,
        min_effective_samples=min_effective_samples,
        source_weights=settings.market_source_weights,
        default_source_weight=settings.market_default_source_weight,
    )

    items = [
        MarketCoverageItemResponse(
            tonie_id=str(item["tonie_id"]),
            title=title_by_id.get(str(item["tonie_id"])),
            raw_samples=int(item["raw_samples"]),
            effective_samples=float(item["effective_samples"]),
            latest_fetched_at=item.get("latest_fetched_at"),
            source_counts={str(k): int(v) for k, v in (item.get("source_counts") or {}).items()},
            meets_target=bool(item.get("meets_target", False)),
        )
        for item in (data.get("items") or [])[: max(1, int(limit))]
    ]

    return MarketCoverageStatusResponse(
        fresh_window_minutes=int(data.get("fresh_window_minutes") or fresh_minutes),
        cutoff=str(data.get("cutoff") or ""),
        min_effective_samples=float(data.get("min_effective_samples") or min_effective_samples),
        total_tonies=int(data.get("total_tonies") or 0),
        covered_tonies=int(data.get("covered_tonies") or 0),
        uncovered_tonies=int(data.get("uncovered_tonies") or 0),
        items=items,
    )


@router.get("/market/quality-status", response_model=PricingQualityStatusResponse)
async def market_quality_status(
    hours: int = Query(default=24, ge=1, le=24 * 14),
    low_sample_threshold: int = Query(default=settings.market_min_samples, ge=1, le=500),
    fresh_minutes: int = Query(default=settings.market_cache_ttl_minutes, ge=1, le=24 * 14 * 60),
    low_fresh_threshold: int = Query(default=settings.market_min_samples, ge=1, le=500),
    low_fresh_limit: int = Query(default=15, ge=1, le=200),
) -> PricingQualityStatusResponse:
    data = get_pricing_quality_status(
        window_hours=hours,
        low_sample_threshold=low_sample_threshold,
    )
    return _pricing_quality_status_response(
        data,
        fresh_minutes=fresh_minutes,
        low_fresh_threshold=low_fresh_threshold,
        low_fresh_limit=low_fresh_limit,
    )


@router.get("/market/refresh-status", response_model=MarketRefreshStatusResponse)
async def market_refresh_status() -> MarketRefreshStatusResponse:
    return _market_refresh_status_response(get_refresh_status())


@router.get("/market/refresh-runs", response_model=MarketRefreshRunsResponse)
async def market_refresh_runs(
    limit: int = Query(default=20, ge=1, le=200),
) -> MarketRefreshRunsResponse:
    rows = list_refresh_runs(limit=limit)
    return MarketRefreshRunsResponse(items=[_market_refresh_status_response(row) for row in rows])


@router.post("/market/refresh", response_model=MarketRefreshResponse)
async def market_refresh(payload: MarketRefreshRequest) -> MarketRefreshResponse:
    limit = payload.limit if payload.limit > 0 else None

    if payload.background:
        started, status_data, message = start_refresh_background(
            limit=limit,
            delay_ms=payload.delay_ms,
            max_items=payload.max_items,
        )
        if not started:
            raise HTTPException(status_code=409, detail=message)
        return MarketRefreshResponse(
            started=started,
            message=message,
            status=_market_refresh_status_response(status_data),
        )

    try:
        status_data = await run_refresh_now(
            limit=limit,
            delay_ms=payload.delay_ms,
            max_items=payload.max_items,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return MarketRefreshResponse(
        started=True,
        message="refresh completed",
        status=_market_refresh_status_response(status_data),
    )


@router.post("/tonies/resolve", response_model=ResolveResponse)
async def resolve_tonie(payload: ResolveRequest) -> ResolveResponse:
    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")

    resolver = get_resolver()
    result = resolver.resolve(q)

    if result.status == "not_found":
        raise HTTPException(status_code=404, detail="tonie not found")

    by_id = {str(item.get("id")): item for item in resolver.catalog}
    return ResolveResponse(
        status=result.status,
        candidates=[
            ResolveCandidate(
                tonie_id=c.tonie_id,
                title=c.title,
                score=c.score,
                rarity_label=_derive_rarity(by_id.get(c.tonie_id))[0],
            )
            for c in result.candidates
        ],
    )


@router.get("/tonies/recognize-status", response_model=RecognizeStatusResponse)
async def tonie_recognize_status() -> RecognizeStatusResponse:
    status_data = get_photo_recognition_status()
    return RecognizeStatusResponse(**status_data)


@router.post("/tonies/recognize", response_model=RecognizeResponse)
async def recognize_tonie_photo(
    image: UploadFile = File(...),
    top_k: int = Query(default=3, ge=1, le=5),
) -> RecognizeResponse:
    content_type = (image.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image file required")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty image payload")

    if len(payload) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image too large (max 10MB)")

    result = recognize_tonie_from_image_bytes(payload, top_k=top_k)

    return RecognizeResponse(
        status=result.status,
        message=result.message,
        candidates=[
            ResolveCandidate(tonie_id=c.tonie_id, title=c.title, score=c.score)
            for c in result.candidates
        ],
    )


@router.get("/pricing/{tonie_id}", response_model=PricingResponse)
async def pricing(
    tonie_id: str,
    condition: Condition = Query(default=Condition.good),
) -> PricingResponse:
    resolver = get_resolver()
    item = next((x for x in resolver.catalog if str(x.get("id")) == tonie_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="tonie not found")

    price = await compute_prices_for_tonie(tonie_id=tonie_id, condition=condition.value)
    quality_tier, confidence_score = _derive_pricing_quality(
        price.sample_size,
        price.source,
        price.effective_sample_size,
    )

    market_rows = get_market_listings(tonie_id=tonie_id, limit=120)

    trend_direction, trend_label, trend_delta_pct = _derive_price_trend(market_rows)
    rarity_label, rarity_reason, availability_state = _derive_rarity(item)

    return PricingResponse(
        tonie_id=tonie_id,
        condition=condition,
        currency="EUR",
        sofortverkaufspreis=price.instant,
        fairer_marktpreis=price.fair,
        geduldspreis=price.patience,
        sample_size=price.sample_size,
        effective_sample_size=price.effective_sample_size,
        source=price.source,
        quality_tier=quality_tier,
        confidence_band=_quality_band_from_tier(quality_tier),
        confidence_score=round(confidence_score, 2),
        trend_direction=trend_direction,
        trend_label=trend_label,
        trend_delta_pct=trend_delta_pct,
        rarity_label=rarity_label,
        rarity_reason=rarity_reason,
        availability_state=availability_state,
    )


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: AuthRequest) -> AuthResponse:
    if settings.auth_mode.strip().lower() == "external":
        raise HTTPException(status_code=400, detail="local auth disabled in external mode")

    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="invalid email")

    user = create_user(email=email, password=payload.password)
    if not user:
        raise HTTPException(status_code=409, detail="user already exists")

    token, expires_at = create_session(user_id=int(user["id"]))
    return AuthResponse(
        token=token,
        expires_at=expires_at,
        user=UserResponse(id=int(user["id"]), email=str(user["email"])),
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: AuthRequest) -> AuthResponse:
    if settings.auth_mode.strip().lower() == "external":
        raise HTTPException(status_code=400, detail="local auth disabled in external mode")

    email = payload.email.strip().lower()
    user = authenticate_user(email=email, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")

    token, expires_at = create_session(user_id=int(user["id"]))
    return AuthResponse(
        token=token,
        expires_at=expires_at,
        user=UserResponse(id=int(user["id"]), email=str(user["email"])),
    )


@router.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)) -> dict:
    token = _extract_bearer(authorization)
    if token:
        delete_session(token)
    return {"ok": True}


@router.get("/auth/me", response_model=UserResponse)
async def me(user: dict = Depends(require_user)) -> UserResponse:
    return UserResponse(id=int(user["id"]), email=str(user["email"]))


@router.get("/watchlist", response_model=list[WatchlistItemResponse])
async def watchlist(
    refresh: bool = Query(default=False),
    user: dict = Depends(require_user),
) -> list[WatchlistItemResponse]:
    user_id = int(user["id"])
    items = list_watchlist_items(user_id=user_id)

    if refresh and items:
        refreshed: list[dict] = []
        for item in items:
            condition = str(item.get("condition", "good"))
            previous_price = float(item.get("last_fair_price") or 0.0)
            target_price = item.get("target_price_eur")

            price = await compute_prices_for_tonie(
                tonie_id=str(item["tonie_id"]),
                condition=condition,
            )
            current_price = float(price.fair)

            updated = update_watchlist_item_price(
                user_id=user_id,
                item_id=int(item["id"]),
                last_fair_price=current_price,
            )

            if target_price is not None and current_price <= float(target_price):
                create_watchlist_alert(
                    user_id=user_id,
                    watchlist_item_id=int(item["id"]),
                    alert_type="price_below_target",
                    message=(
                        f"{item['title']}: {current_price:.2f} EUR <= target {float(target_price):.2f} EUR"
                    ),
                    current_price_eur=current_price,
                    previous_price_eur=previous_price if previous_price > 0 else None,
                    target_price_eur=float(target_price),
                )

            if previous_price > 0:
                drop_ratio = (previous_price - current_price) / previous_price
                if drop_ratio >= 0.15:
                    create_watchlist_alert(
                        user_id=user_id,
                        watchlist_item_id=int(item["id"]),
                        alert_type="price_drop_15pct",
                        message=(
                            f"{item['title']}: price drop {drop_ratio * 100:.1f}% "
                            f"({previous_price:.2f} -> {current_price:.2f} EUR)"
                        ),
                        current_price_eur=current_price,
                        previous_price_eur=previous_price,
                        target_price_eur=(float(target_price) if target_price is not None else None),
                    )

            refreshed.append(updated if updated is not None else item)
        items = refreshed

    return [_watchlist_item_response(item) for item in items]


@router.get("/watchlist/alerts", response_model=list[WatchlistAlertResponse])
async def watchlist_alerts(
    unread_only: bool = Query(default=False),
    user: dict = Depends(require_user),
) -> list[WatchlistAlertResponse]:
    rows = list_watchlist_alerts(user_id=int(user["id"]), unread_only=unread_only)
    return [_watchlist_alert_response(row) for row in rows]


@router.post("/watchlist", response_model=WatchlistItemResponse)
async def watchlist_add(
    payload: WatchlistAddRequest,
    user: dict = Depends(require_user),
) -> WatchlistItemResponse:
    tonie_id = payload.tonie_id.strip()
    if not tonie_id:
        raise HTTPException(status_code=400, detail="tonie_id is required")

    title = (payload.title or "").strip()
    if not title:
        resolver = get_resolver()
        candidate = next((x for x in resolver.catalog if x["id"] == tonie_id), None)
        title = candidate["title"] if candidate else tonie_id

    fair = (
        await compute_prices_for_tonie(tonie_id=tonie_id, condition=payload.condition.value)
    ).fair

    item = upsert_watchlist_item(
        user_id=int(user["id"]),
        tonie_id=tonie_id,
        title=title,
        condition=payload.condition.value,
        last_fair_price=fair,
        target_price_eur=payload.target_price_eur,
    )

    return _watchlist_item_response(item)


@router.delete("/watchlist/{item_id}")
async def watchlist_delete(item_id: int, user: dict = Depends(require_user)) -> dict:
    deleted = delete_watchlist_item(user_id=int(user["id"]), item_id=item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    return {"ok": True}
