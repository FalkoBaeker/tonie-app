from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path() -> Path:
    path = Path(settings.sqlite_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS watchlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tonie_id TEXT NOT NULL,
                title TEXT NOT NULL,
                condition TEXT NOT NULL,
                last_fair_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, tonie_id, condition)
            );

            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tonie_id TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                price_eur REAL NOT NULL,
                url TEXT NOT NULL,
                sold_at TEXT,
                fetched_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(tonie_id, source, url, price_eur)
            );

            CREATE TABLE IF NOT EXISTS pricing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tonie_id TEXT NOT NULL,
                condition TEXT NOT NULL,
                source TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                latency_ms INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist_items(user_id);
            CREATE INDEX IF NOT EXISTS idx_market_tonie_fetched ON market_listings(tonie_id, fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_created ON pricing_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_source_created ON pricing_events(source, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_tonie_created ON pricing_events(tonie_id, created_at DESC);
            """
        )


def _hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        settings.password_iterations,
    )
    return f"{salt.hex()}${derived.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, expected_hash = stored.split("$", 1)
    except ValueError:
        return False

    calculated = _hash_password(password, salt_hex=salt_hex)
    return secrets.compare_digest(calculated.split("$", 1)[1], expected_hash)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, password: str) -> dict | None:
    normalized = _normalize_email(email)
    if not normalized or len(password) < 6:
        return None

    now = _now_iso()
    pw_hash = _hash_password(password)

    try:
        with _connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                (normalized, pw_hash, now),
            )
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return None

    return {"id": user_id, "email": normalized}


def authenticate_user(email: str, password: str) -> dict | None:
    normalized = _normalize_email(email)

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (normalized,),
        ).fetchone()

    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None

    return {"id": int(row["id"]), "email": str(row["email"])}


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires = now + timedelta(hours=settings.session_ttl_hours)

    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(), expires.isoformat()),
        )

    return token, expires.isoformat()


def delete_session(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_user_by_token(token: str | None) -> dict | None:
    if not token:
        return None

    now = datetime.now(UTC).isoformat()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT u.id AS id, u.email AS email
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at >= ?
            """,
            (token, now),
        ).fetchone()

        # lightweight cleanup of expired sessions
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))

    if not row:
        return None

    return {"id": int(row["id"]), "email": str(row["email"])}


def list_watchlist_items(user_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, tonie_id, title, condition, last_fair_price, updated_at
            FROM watchlist_items
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [
        {
            "id": int(r["id"]),
            "tonie_id": str(r["tonie_id"]),
            "title": str(r["title"]),
            "condition": str(r["condition"]),
            "last_fair_price": float(r["last_fair_price"]),
            "updated_at": str(r["updated_at"]),
        }
        for r in rows
    ]


def upsert_watchlist_item(
    user_id: int,
    tonie_id: str,
    title: str,
    condition: str,
    last_fair_price: float,
) -> dict:
    now = _now_iso()

    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist_items WHERE user_id = ? AND tonie_id = ? AND condition = ?",
            (user_id, tonie_id, condition),
        ).fetchone()

        if existing:
            item_id = int(existing["id"])
            conn.execute(
                """
                UPDATE watchlist_items
                SET title = ?, last_fair_price = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, last_fair_price, now, item_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO watchlist_items(
                    user_id, tonie_id, title, condition, last_fair_price, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, tonie_id, title, condition, last_fair_price, now, now),
            )
            item_id = int(cursor.lastrowid)

        row = conn.execute(
            """
            SELECT id, tonie_id, title, condition, last_fair_price, updated_at
            FROM watchlist_items
            WHERE id = ? AND user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("watchlist item not found after upsert")

    return {
        "id": int(row["id"]),
        "tonie_id": str(row["tonie_id"]),
        "title": str(row["title"]),
        "condition": str(row["condition"]),
        "last_fair_price": float(row["last_fair_price"]),
        "updated_at": str(row["updated_at"]),
    }


def delete_watchlist_item(user_id: int, item_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )
    return cursor.rowcount > 0


def update_watchlist_item_price(
    user_id: int,
    item_id: int,
    *,
    title: str | None = None,
    last_fair_price: float,
) -> dict | None:
    now = _now_iso()

    with _connect() as conn:
        if title:
            conn.execute(
                """
                UPDATE watchlist_items
                SET title = ?, last_fair_price = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (title, float(last_fair_price), now, item_id, user_id),
            )
        else:
            conn.execute(
                """
                UPDATE watchlist_items
                SET last_fair_price = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (float(last_fair_price), now, item_id, user_id),
            )

        row = conn.execute(
            """
            SELECT id, tonie_id, title, condition, last_fair_price, updated_at
            FROM watchlist_items
            WHERE id = ? AND user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": int(row["id"]),
        "tonie_id": str(row["tonie_id"]),
        "title": str(row["title"]),
        "condition": str(row["condition"]),
        "last_fair_price": float(row["last_fair_price"]),
        "updated_at": str(row["updated_at"]),
    }


def _to_iso(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    return str(value)


def save_market_listings(
    tonie_id: str,
    source: str,
    listings: list[dict],
    fetched_at: str | datetime | None = None,
) -> int:
    if not listings:
        return 0

    now_iso = _now_iso()
    fetched_iso = _to_iso(fetched_at) or now_iso

    affected = 0
    with _connect() as conn:
        for item in listings:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            price = float(item.get("price_eur", 0.0) or 0.0)
            sold_at = _to_iso(item.get("sold_at"))

            if not title or not url or price <= 0:
                continue

            conn.execute(
                """
                INSERT INTO market_listings(
                    tonie_id, source, title, price_eur, url, sold_at, fetched_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tonie_id, source, url, price_eur)
                DO UPDATE SET
                    title = excluded.title,
                    sold_at = excluded.sold_at,
                    fetched_at = excluded.fetched_at
                """,
                (tonie_id, source, title, price, url, sold_at, fetched_iso, now_iso),
            )
            affected += 1

    return affected


def get_market_listings(
    tonie_id: str,
    max_age_minutes: int | None = None,
    limit: int = 250,
) -> list[dict]:
    query = (
        "SELECT source, title, price_eur, url, sold_at, fetched_at "
        "FROM market_listings WHERE tonie_id = ?"
    )
    params: list[object] = [tonie_id]

    if max_age_minutes is not None:
        cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
        query += " AND fetched_at >= ?"
        params.append(cutoff.isoformat())

    query += " ORDER BY fetched_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [
        {
            "source": str(r["source"]),
            "title": str(r["title"]),
            "price_eur": float(r["price_eur"]),
            "url": str(r["url"]),
            "sold_at": str(r["sold_at"]) if r["sold_at"] else None,
            "fetched_at": str(r["fetched_at"]),
        }
        for r in rows
    ]


def prune_old_market_listings(max_age_days: int | None = None) -> int:
    keep_days = max_age_days if max_age_days is not None else settings.market_history_days
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)

    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM market_listings WHERE fetched_at < ?",
            (cutoff.isoformat(),),
        )
        deleted = int(cursor.rowcount)

    return deleted


def get_market_cache_status(
    *,
    tonie_id: str | None = None,
    fresh_minutes: int | None = None,
) -> dict:
    fresh_window = fresh_minutes if fresh_minutes is not None else settings.market_cache_ttl_minutes
    fresh_cutoff = (datetime.now(UTC) - timedelta(minutes=fresh_window)).isoformat()

    where_clause = ""
    params: list[object] = []
    if tonie_id:
        where_clause = "WHERE tonie_id = ?"
        params.append(tonie_id)

    with _connect() as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) AS listing_count,
                COUNT(DISTINCT tonie_id) AS tonie_count,
                MAX(fetched_at) AS latest_fetched_at
            FROM market_listings
            {where_clause}
            """,
            tuple(params),
        ).fetchone()

        if where_clause:
            fresh_where = f"{where_clause} AND fetched_at >= ?"
            fresh_params = [*params, fresh_cutoff]
        else:
            fresh_where = "WHERE fetched_at >= ?"
            fresh_params = [fresh_cutoff]

        fresh = conn.execute(
            f"""
            SELECT
                COUNT(*) AS fresh_listing_count,
                COUNT(DISTINCT tonie_id) AS fresh_tonie_count
            FROM market_listings
            {fresh_where}
            """,
            tuple(fresh_params),
        ).fetchone()

    return {
        "tonie_id": tonie_id,
        "listing_count": int(totals["listing_count"] if totals and totals["listing_count"] else 0),
        "tonie_count": int(totals["tonie_count"] if totals and totals["tonie_count"] else 0),
        "latest_fetched_at": str(totals["latest_fetched_at"]) if totals and totals["latest_fetched_at"] else None,
        "fresh_window_minutes": int(fresh_window),
        "fresh_listing_count": int(
            fresh["fresh_listing_count"] if fresh and fresh["fresh_listing_count"] else 0
        ),
        "fresh_tonie_count": int(
            fresh["fresh_tonie_count"] if fresh and fresh["fresh_tonie_count"] else 0
        ),
    }


def save_pricing_event(
    tonie_id: str,
    condition: str,
    source: str,
    sample_size: int,
    *,
    latency_ms: int | None = None,
) -> None:
    init_db()
    now = _now_iso()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO pricing_events(tonie_id, condition, source, sample_size, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(tonie_id),
                str(condition),
                str(source),
                max(0, int(sample_size)),
                int(latency_ms) if latency_ms is not None else None,
                now,
            ),
        )


def get_pricing_quality_status(
    *,
    window_hours: int = 24,
    low_sample_threshold: int | None = None,
    fallback_limit: int = 10,
) -> dict:
    init_db()
    hours = max(1, min(24 * 14, int(window_hours)))
    threshold = (
        max(1, int(low_sample_threshold))
        if low_sample_threshold is not None
        else max(1, int(settings.market_min_samples))
    )
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    with _connect() as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS total_requests,
                SUM(CASE WHEN source = 'fallback_no_live_market_data' THEN 1 ELSE 0 END) AS fallback_count,
                SUM(CASE WHEN source = 'ebay_sold_live_q25_q50_q75' THEN 1 ELSE 0 END) AS live_count,
                SUM(CASE WHEN source = 'ebay_sold_cached_q25_q50_q75' THEN 1 ELSE 0 END) AS fresh_cache_count,
                SUM(CASE WHEN source = 'ebay_sold_cached_stale_q25_q50_q75' THEN 1 ELSE 0 END) AS stale_cache_count,
                SUM(CASE WHEN sample_size < ? THEN 1 ELSE 0 END) AS low_sample_count,
                AVG(sample_size) AS avg_sample_size,
                AVG(latency_ms) AS avg_latency_ms,
                MAX(created_at) AS latest_event_at
            FROM pricing_events
            WHERE created_at >= ?
            """,
            (threshold, cutoff),
        ).fetchone()

        fallback_rows = conn.execute(
            """
            SELECT tonie_id, COUNT(*) AS requests, AVG(sample_size) AS avg_sample_size
            FROM pricing_events
            WHERE created_at >= ? AND source = 'fallback_no_live_market_data'
            GROUP BY tonie_id
            ORDER BY requests DESC, tonie_id ASC
            LIMIT ?
            """,
            (cutoff, max(1, int(fallback_limit))),
        ).fetchall()

    total_requests = int(summary["total_requests"] if summary and summary["total_requests"] else 0)
    fallback_count = int(summary["fallback_count"] if summary and summary["fallback_count"] else 0)

    return {
        "window_hours": hours,
        "cutoff": cutoff,
        "low_sample_threshold": threshold,
        "total_requests": total_requests,
        "fallback_count": fallback_count,
        "fallback_rate": round((fallback_count / total_requests) * 100.0, 2)
        if total_requests > 0
        else 0.0,
        "live_count": int(summary["live_count"] if summary and summary["live_count"] else 0),
        "fresh_cache_count": int(
            summary["fresh_cache_count"] if summary and summary["fresh_cache_count"] else 0
        ),
        "stale_cache_count": int(
            summary["stale_cache_count"] if summary and summary["stale_cache_count"] else 0
        ),
        "low_sample_count": int(
            summary["low_sample_count"] if summary and summary["low_sample_count"] else 0
        ),
        "avg_sample_size": round(float(summary["avg_sample_size"]), 2)
        if summary and summary["avg_sample_size"] is not None
        else 0.0,
        "avg_latency_ms": round(float(summary["avg_latency_ms"]), 2)
        if summary and summary["avg_latency_ms"] is not None
        else None,
        "latest_event_at": str(summary["latest_event_at"])
        if summary and summary["latest_event_at"]
        else None,
        "fallback_top": [
            {
                "tonie_id": str(row["tonie_id"]),
                "requests": int(row["requests"] if row["requests"] else 0),
                "avg_sample_size": round(float(row["avg_sample_size"]), 2)
                if row["avg_sample_size"] is not None
                else 0.0,
            }
            for row in fallback_rows
        ],
    }


def get_fresh_listing_counts(*, fresh_minutes: int | None = None) -> dict[str, dict]:
    init_db()
    window = (
        max(1, int(fresh_minutes))
        if fresh_minutes is not None
        else max(1, int(settings.market_cache_ttl_minutes))
    )
    cutoff = (datetime.now(UTC) - timedelta(minutes=window)).isoformat()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT tonie_id, COUNT(*) AS fresh_listing_count, MAX(fetched_at) AS latest_fetched_at
            FROM market_listings
            WHERE fetched_at >= ?
            GROUP BY tonie_id
            """,
            (cutoff,),
        ).fetchall()

    return {
        str(row["tonie_id"]): {
            "fresh_listing_count": int(row["fresh_listing_count"] if row["fresh_listing_count"] else 0),
            "latest_fetched_at": str(row["latest_fetched_at"]) if row["latest_fetched_at"] else None,
        }
        for row in rows
    }


def get_market_coverage_report(
    *,
    fresh_minutes: int | None = None,
    min_effective_samples: float | None = None,
    source_weights: dict[str, float] | None = None,
    default_source_weight: float | None = None,
) -> dict:
    """
    Build a per-tonie coverage report with weighted sample counts.

    Example use case:
    - ebay_sold weight 1.0
    - kleinanzeigen_offer weight 0.35
    """
    init_db()

    window = (
        max(1, int(fresh_minutes))
        if fresh_minutes is not None
        else max(1, int(settings.market_cache_ttl_minutes))
    )
    cutoff = (datetime.now(UTC) - timedelta(minutes=window)).isoformat()

    default_weight = (
        max(0.0, float(default_source_weight))
        if default_source_weight is not None
        else max(0.0, float(settings.market_default_source_weight))
    )

    configured_weights = source_weights if source_weights is not None else settings.market_source_weights
    normalized_weights = {
        str(key).strip().lower(): max(0.0, float(value))
        for key, value in (configured_weights or {}).items()
    }

    effective_target = (
        max(0.1, float(min_effective_samples))
        if min_effective_samples is not None
        else max(0.1, float(settings.market_min_effective_samples))
    )

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                tonie_id,
                source,
                COUNT(*) AS listing_count,
                MAX(fetched_at) AS latest_fetched_at
            FROM market_listings
            WHERE fetched_at >= ?
            GROUP BY tonie_id, source
            ORDER BY tonie_id ASC, source ASC
            """,
            (cutoff,),
        ).fetchall()

    per_tonie: dict[str, dict] = {}

    for row in rows:
        tonie_id = str(row["tonie_id"])
        source = str(row["source"] or "unknown").strip().lower() or "unknown"
        listing_count = int(row["listing_count"] if row["listing_count"] else 0)
        latest_fetched_at = str(row["latest_fetched_at"]) if row["latest_fetched_at"] else None

        weight = normalized_weights.get(source, default_weight)

        bucket = per_tonie.setdefault(
            tonie_id,
            {
                "tonie_id": tonie_id,
                "raw_samples": 0,
                "effective_samples": 0.0,
                "latest_fetched_at": None,
                "source_counts": {},
            },
        )

        bucket["raw_samples"] += listing_count
        bucket["effective_samples"] += listing_count * weight
        bucket["source_counts"][source] = bucket["source_counts"].get(source, 0) + listing_count

        current_latest = bucket["latest_fetched_at"]
        if latest_fetched_at and (current_latest is None or latest_fetched_at > current_latest):
            bucket["latest_fetched_at"] = latest_fetched_at

    items = []
    for tonie_id, bucket in per_tonie.items():
        effective = round(float(bucket["effective_samples"]), 2)
        items.append(
            {
                "tonie_id": tonie_id,
                "raw_samples": int(bucket["raw_samples"]),
                "effective_samples": effective,
                "latest_fetched_at": bucket["latest_fetched_at"],
                "source_counts": dict(bucket["source_counts"]),
                "meets_target": effective >= effective_target,
            }
        )

    items.sort(key=lambda item: (item["effective_samples"], item["raw_samples"], item["tonie_id"]))

    covered = sum(1 for item in items if item["meets_target"])

    return {
        "fresh_window_minutes": window,
        "cutoff": cutoff,
        "min_effective_samples": round(effective_target, 2),
        "total_tonies": len(items),
        "covered_tonies": covered,
        "uncovered_tonies": max(0, len(items) - covered),
        "items": items,
    }
