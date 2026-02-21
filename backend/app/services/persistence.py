from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path() -> Path:
    path = Path(settings.sqlite_path).expanduser()
    if not path.is_absolute():
        # Resolve relative DB paths against backend root, not process cwd.
        path = (_BACKEND_ROOT / path).resolve()

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    db_path = _db_path()

    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
    except sqlite3.OperationalError as exc:
        raise sqlite3.OperationalError(
            f"unable to open sqlite database at '{db_path}': {exc}"
        ) from exc

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        # Fallback for filesystems/environments where WAL sidecar files are blocked.
        conn.execute("PRAGMA journal_mode = DELETE")

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
                target_price_eur REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, tonie_id, condition)
            );

            CREATE TABLE IF NOT EXISTS watchlist_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                watchlist_item_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                current_price_eur REAL NOT NULL,
                previous_price_eur REAL,
                target_price_eur REAL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(watchlist_item_id) REFERENCES watchlist_items(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS refresh_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                total INTEGER NOT NULL,
                processed INTEGER NOT NULL,
                successful INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                saved_rows INTEGER NOT NULL,
                pruned_rows INTEGER NOT NULL,
                limit_value INTEGER,
                delay_ms INTEGER NOT NULL,
                max_items INTEGER NOT NULL,
                failures_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist_items(user_id);
            CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_user_created ON watchlist_alerts(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_user_read_created ON watchlist_alerts(user_id, is_read, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_market_tonie_fetched ON market_listings(tonie_id, fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_created ON pricing_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_source_created ON pricing_events(source, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_events_tonie_created ON pricing_events(tonie_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_started_at ON refresh_runs(started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_refresh_runs_status ON refresh_runs(status, started_at DESC);
            """
        )

        # Lightweight schema migration for existing DBs.
        try:
            conn.execute("ALTER TABLE watchlist_items ADD COLUMN target_price_eur REAL")
        except sqlite3.OperationalError:
            pass


def get_db_readiness() -> dict:
    db_path = _db_path()

    try:
        init_db()
        with _connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.OperationalError as exc:
        return {
            "ok": False,
            "status": "degraded",
            "reason": f"sqlite_operational_error: {exc}",
            "sqlite_path": str(db_path),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "degraded",
            "reason": f"db_check_failed: {exc}",
            "sqlite_path": str(db_path),
        }

    return {
        "ok": True,
        "status": "ok",
        "reason": None,
        "sqlite_path": str(db_path),
    }


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


def get_or_create_user_by_email(email: str) -> dict | None:
    normalized = _normalize_email(email)
    if not normalized:
        return None

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, email FROM users WHERE email = ?",
            (normalized,),
        ).fetchone()
        if row:
            return {"id": int(row["id"]), "email": str(row["email"])}

        # External-auth users do not use local password login.
        placeholder_password = secrets.token_urlsafe(32)
        pw_hash = _hash_password(placeholder_password)
        now = _now_iso()

        cursor = conn.execute(
            "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
            (normalized, pw_hash, now),
        )

    return {"id": int(cursor.lastrowid), "email": normalized}


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
            SELECT id, tonie_id, title, condition, last_fair_price, target_price_eur, updated_at
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
            "target_price_eur": float(r["target_price_eur"]) if r["target_price_eur"] is not None else None,
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
    target_price_eur: float | None = None,
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
                SET title = ?, last_fair_price = ?, target_price_eur = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, last_fair_price, target_price_eur, now, item_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO watchlist_items(
                    user_id, tonie_id, title, condition, last_fair_price, target_price_eur, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, tonie_id, title, condition, last_fair_price, target_price_eur, now, now),
            )
            item_id = int(cursor.lastrowid)

        row = conn.execute(
            """
            SELECT id, tonie_id, title, condition, last_fair_price, target_price_eur, updated_at
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
        "target_price_eur": float(row["target_price_eur"]) if row["target_price_eur"] is not None else None,
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
            SELECT id, tonie_id, title, condition, last_fair_price, target_price_eur, updated_at
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
        "target_price_eur": float(row["target_price_eur"]) if row["target_price_eur"] is not None else None,
        "updated_at": str(row["updated_at"]),
    }


def create_watchlist_alert(
    *,
    user_id: int,
    watchlist_item_id: int,
    alert_type: str,
    message: str,
    current_price_eur: float,
    previous_price_eur: float | None = None,
    target_price_eur: float | None = None,
) -> dict:
    init_db()
    created_at = _now_iso()

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO watchlist_alerts(
                user_id, watchlist_item_id, alert_type, message,
                current_price_eur, previous_price_eur, target_price_eur,
                is_read, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                user_id,
                watchlist_item_id,
                str(alert_type),
                str(message),
                float(current_price_eur),
                float(previous_price_eur) if previous_price_eur is not None else None,
                float(target_price_eur) if target_price_eur is not None else None,
                created_at,
            ),
        )
        alert_id = int(cursor.lastrowid)

    return {
        "id": alert_id,
        "user_id": int(user_id),
        "watchlist_item_id": int(watchlist_item_id),
        "alert_type": str(alert_type),
        "message": str(message),
        "current_price_eur": float(current_price_eur),
        "previous_price_eur": float(previous_price_eur) if previous_price_eur is not None else None,
        "target_price_eur": float(target_price_eur) if target_price_eur is not None else None,
        "is_read": False,
        "created_at": created_at,
    }


def list_watchlist_alerts(*, user_id: int, unread_only: bool = False, limit: int = 200) -> list[dict]:
    init_db()

    where_clause = "WHERE a.user_id = ?"
    params: list[object] = [int(user_id)]
    if unread_only:
        where_clause += " AND a.is_read = 0"

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.id,
                a.watchlist_item_id,
                a.alert_type,
                a.message,
                a.current_price_eur,
                a.previous_price_eur,
                a.target_price_eur,
                a.is_read,
                a.created_at,
                w.tonie_id,
                w.title,
                w.condition
            FROM watchlist_alerts a
            JOIN watchlist_items w ON w.id = a.watchlist_item_id
            {where_clause}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()

    return [
        {
            "id": int(row["id"]),
            "watchlist_item_id": int(row["watchlist_item_id"]),
            "tonie_id": str(row["tonie_id"]),
            "title": str(row["title"]),
            "condition": str(row["condition"]),
            "alert_type": str(row["alert_type"]),
            "message": str(row["message"]),
            "current_price_eur": float(row["current_price_eur"]),
            "previous_price_eur": float(row["previous_price_eur"]) if row["previous_price_eur"] is not None else None,
            "target_price_eur": float(row["target_price_eur"]) if row["target_price_eur"] is not None else None,
            "is_read": bool(row["is_read"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


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
        "SELECT id, source, title, price_eur, url, sold_at, fetched_at "
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
            "id": int(r["id"]),
            "source": str(r["source"]),
            "title": str(r["title"]),
            "price_eur": float(r["price_eur"]),
            "url": str(r["url"]),
            "sold_at": str(r["sold_at"]) if r["sold_at"] else None,
            "fetched_at": str(r["fetched_at"]),
        }
        for r in rows
    ]


def list_market_listings_for_source(
    *,
    source: str,
    tonie_id: str | None = None,
    limit: int = 2000,
) -> list[dict]:
    query = (
        "SELECT id, tonie_id, source, title, price_eur, url, sold_at, fetched_at "
        "FROM market_listings WHERE source = ?"
    )
    params: list[object] = [str(source)]

    if tonie_id:
        query += " AND tonie_id = ?"
        params.append(str(tonie_id))

    query += " ORDER BY fetched_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))

    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [
        {
            "id": int(r["id"]),
            "tonie_id": str(r["tonie_id"]),
            "source": str(r["source"]),
            "title": str(r["title"]),
            "price_eur": float(r["price_eur"]),
            "url": str(r["url"]),
            "sold_at": str(r["sold_at"]) if r["sold_at"] else None,
            "fetched_at": str(r["fetched_at"]),
        }
        for r in rows
    ]


def delete_market_listings_by_ids(*, ids: list[int], source: str | None = None) -> int:
    cleaned_ids = [int(x) for x in ids if int(x) > 0]
    if not cleaned_ids:
        return 0

    placeholders = ", ".join(["?"] * len(cleaned_ids))
    query = f"DELETE FROM market_listings WHERE id IN ({placeholders})"
    params: list[object] = list(cleaned_ids)
    if source:
        query += " AND source = ?"
        params.append(str(source))

    with _connect() as conn:
        cursor = conn.execute(query, tuple(params))
        return int(cursor.rowcount)


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


def create_refresh_run(state: dict) -> None:
    init_db()
    now = _now_iso()
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")

    failures = [str(x) for x in (state.get("failures") or [])]

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO refresh_runs(
                run_id, status, started_at, finished_at,
                total, processed, successful, failed, saved_rows, pruned_rows,
                limit_value, delay_ms, max_items, failures_json,
                created_at, updated_at
            )
            VALUES(
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                COALESCE((SELECT created_at FROM refresh_runs WHERE run_id = ?), ?),
                ?
            )
            """,
            (
                run_id,
                str(state.get("status") or "running"),
                str(state.get("started_at") or now),
                state.get("finished_at"),
                int(state.get("total") or 0),
                int(state.get("processed") or 0),
                int(state.get("successful") or 0),
                int(state.get("failed") or 0),
                int(state.get("saved_rows") or 0),
                int(state.get("pruned_rows") or 0),
                int(state["limit"]) if state.get("limit") is not None else None,
                int(state.get("delay_ms") or 0),
                int(state.get("max_items") or 0),
                json.dumps(failures, ensure_ascii=False),
                run_id,
                now,
                now,
            ),
        )


def update_refresh_run(state: dict) -> None:
    create_refresh_run(state)


def list_refresh_runs(*, limit: int = 20) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, status, started_at, finished_at,
                   total, processed, successful, failed, saved_rows, pruned_rows,
                   limit_value, delay_ms, max_items, failures_json,
                   created_at, updated_at
            FROM refresh_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()

    out: list[dict] = []
    for row in rows:
        failures_raw = row["failures_json"] if row["failures_json"] else "[]"
        try:
            failures = json.loads(str(failures_raw))
        except json.JSONDecodeError:
            failures = []

        out.append(
            {
                "run_id": str(row["run_id"]),
                "status": str(row["status"]),
                "started_at": str(row["started_at"]),
                "finished_at": str(row["finished_at"]) if row["finished_at"] else None,
                "total": int(row["total"] or 0),
                "processed": int(row["processed"] or 0),
                "successful": int(row["successful"] or 0),
                "failed": int(row["failed"] or 0),
                "saved_rows": int(row["saved_rows"] or 0),
                "pruned_rows": int(row["pruned_rows"] or 0),
                "limit": int(row["limit_value"]) if row["limit_value"] is not None else None,
                "delay_ms": int(row["delay_ms"] or 0),
                "max_items": int(row["max_items"] or 0),
                "failures": [str(x) for x in failures],
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )

    return out


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
