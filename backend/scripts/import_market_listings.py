#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.persistence import init_db, save_market_listings  # noqa: E402


def _load_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("listings") or payload.get("items") or payload.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _load_rows(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".jsonl":
        return _load_jsonl(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _first_non_empty(row: dict, keys: Iterable[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_rows(rows: list[dict], default_source: str) -> tuple[list[dict], int]:
    normalized: list[dict] = []
    skipped = 0

    for row in rows:
        tonie_id = _first_non_empty(row, ("tonie_id", "id", "tonie"))
        if not tonie_id:
            skipped += 1
            continue

        source = (_first_non_empty(row, ("source",)) or default_source).strip().lower()
        title = _first_non_empty(row, ("title", "name")) or f"Imported listing ({tonie_id})"

        price_raw = _first_non_empty(row, ("price_eur", "price", "eur"))
        if price_raw is None:
            skipped += 1
            continue

        try:
            price = float(str(price_raw).replace(",", "."))
        except ValueError:
            skipped += 1
            continue

        if price <= 0:
            skipped += 1
            continue

        url = _first_non_empty(row, ("url", "listing_url", "link"))
        listing_id = _first_non_empty(row, ("listing_id", "id_in_source", "external_id"))
        if not url and listing_id:
            url = f"import://{source}/{listing_id}"

        if not url:
            skipped += 1
            continue

        sold_at = _first_non_empty(row, ("sold_at", "soldAt", "created_at", "date"))

        normalized.append(
            {
                "tonie_id": tonie_id,
                "source": source,
                "title": title,
                "price_eur": price,
                "url": url,
                "sold_at": sold_at,
            }
        )

    return normalized, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import external market listings (CSV/JSON/JSONL) into tonie_finder.db"
    )
    parser.add_argument("--file", required=True, help="Path to CSV/JSON/JSONL input")
    parser.add_argument(
        "--default-source",
        default="manual_import",
        help="Fallback source name when row.source is missing",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate + summarize without writing")
    args = parser.parse_args()

    input_path = Path(args.file).expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: file not found: {input_path}")
        return 1

    rows = _load_rows(input_path)
    normalized, skipped = _normalize_rows(rows, default_source=args.default_source)

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in normalized:
        grouped[(row["tonie_id"], row["source"])].append(
            {
                "title": row["title"],
                "price_eur": row["price_eur"],
                "url": row["url"],
                "sold_at": row["sold_at"],
            }
        )

    print(f"Input rows: {len(rows)}")
    print(f"Valid rows: {len(normalized)}")
    print(f"Skipped rows: {skipped}")
    print(f"Tonie/source groups: {len(grouped)}")

    if args.dry_run:
        print("Dry run: no DB writes")
        return 0

    init_db()

    saved_total = 0
    for (tonie_id, source), listings in grouped.items():
        saved = save_market_listings(tonie_id=tonie_id, source=source, listings=listings)
        saved_total += saved

    print(f"Saved/updated rows: {saved_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
