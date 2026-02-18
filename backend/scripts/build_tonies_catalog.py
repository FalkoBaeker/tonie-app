#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DE_TONIES_LIST_URL = "https://tonies.com/de-de/tonies/"
SITEMAP_PRODUCTS_1_URL = "https://tonies.com/sitemap_products_1.xml"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@dataclass
class ScrapedTonie:
    source_url: str
    series: str
    name: str

    @property
    def title(self) -> str:
        series_norm = _normalize(self.series)
        name_norm = _normalize(self.name)

        # Avoid noisy duplicates like "101 Dalmatiner – 101 Dalmatiner".
        if name_norm.startswith(series_norm):
            return self.name

        return f"{self.series} – {self.name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build large Tonie catalog from tonies.com DE sitemap + Next data endpoints."
    )
    parser.add_argument(
        "--seed",
        default=str(ROOT / "app" / "data" / "tonies_seed.json"),
        help="Path to legacy/manual seed JSON (default: app/data/tonies_seed.json)",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "app" / "data" / "tonies_catalog.json"),
        help="Path to generated merged catalog JSON (default: app/data/tonies_catalog.json)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=18,
        help="Concurrent requests for product JSON fetches (default: 18)",
    )
    return parser.parse_args()


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _ascii_alias(text: str) -> str:
    replaced = (
        text.replace("Ä", "Ae")
        .replace("Ö", "Oe")
        .replace("Ü", "Ue")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    replaced = unicodedata.normalize("NFKC", replaced)
    replaced = re.sub(r"\s+", " ", replaced).strip()
    return replaced


def _merge_aliases(*groups: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for group in groups:
        for alias in group:
            value = re.sub(r"\s+", " ", str(alias or "")).strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)

    return out


def _aliases_for_scraped(item: ScrapedTonie) -> list[str]:
    base = [item.name, _ascii_alias(item.name)]

    series_norm = _normalize(item.series)
    name_norm = _normalize(item.name)

    if not name_norm.startswith(series_norm):
        base.extend(
            [
                f"{item.series} {item.name}",
                _ascii_alias(f"{item.series} {item.name}"),
            ]
        )

    return _merge_aliases(base)


def _extract_build_id(list_page_html: str) -> str:
    next_data_match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        list_page_html,
        flags=re.DOTALL,
    )
    if next_data_match:
        payload = json.loads(next_data_match.group(1))
        build_id = str(payload.get("buildId") or "").strip()
        if build_id:
            return build_id

    manifest_match = re.search(r"/_next/static/([^/]+)/_buildManifest\.js", list_page_html)
    if manifest_match:
        return manifest_match.group(1)

    raise RuntimeError("Could not extract Next buildId from listing page")


def _load_de_tonies_urls_from_sitemap() -> list[str]:
    raw = urlopen(SITEMAP_PRODUCTS_1_URL, timeout=30).read()
    root = ET.fromstring(raw)

    urls = []
    for node in root.findall(".//sm:loc", SITEMAP_NS):
        loc = (node.text or "").strip()
        if not loc:
            continue
        if "/de-de/tonies/" not in loc:
            continue
        urls.append(loc)

    # Keep deterministic ordering from sitemap
    return urls


def _path_from_product_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path.strip("/")


async def _fetch_product(client: httpx.AsyncClient, build_id: str, product_url: str) -> ScrapedTonie | None:
    path = _path_from_product_url(product_url)
    data_url = f"https://tonies.com/_next/data/{build_id}/{path}.json"

    try:
        response = await client.get(data_url)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    product = (payload.get("pageProps") or {}).get("product") or {}

    name = str(product.get("name") or "").strip()
    series_raw = product.get("series")

    if isinstance(series_raw, dict):
        series = str(series_raw.get("label") or series_raw.get("key") or "").strip()
    else:
        series = str(series_raw or "").strip()

    if not name or not series:
        return None

    return ScrapedTonie(
        source_url=product_url,
        series=series,
        name=name,
    )


async def _fetch_all_products(urls: list[str], build_id: str, concurrency: int) -> tuple[list[ScrapedTonie], int]:
    limits = httpx.Limits(max_keepalive_connections=max(10, concurrency), max_connections=max(10, concurrency))
    timeout = httpx.Timeout(20.0)
    sem = asyncio.Semaphore(max(1, concurrency))

    scraped: list[ScrapedTonie] = []
    errors = 0

    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
        async def worker(url: str) -> None:
            nonlocal errors
            async with sem:
                result = await _fetch_product(client, build_id=build_id, product_url=url)
            if result is None:
                errors += 1
                return
            scraped.append(result)

        await asyncio.gather(*(worker(url) for url in urls))

    return scraped, errors


def _entry_num(tonie_id: str) -> int:
    match = re.fullmatch(r"tn_(\d+)", tonie_id.strip())
    return int(match.group(1)) if match else -1


def main() -> int:
    args = parse_args()

    seed_path = Path(args.seed).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    print("Loading legacy seed:", seed_path)
    legacy_seed = json.loads(seed_path.read_text(encoding="utf-8"))

    print("Fetching DE tonies listing page...")
    list_page_html = urlopen(DE_TONIES_LIST_URL, timeout=30).read().decode("utf-8", "ignore")
    build_id = _extract_build_id(list_page_html)
    print("Detected Next buildId:", build_id)

    print("Loading sitemap URLs...")
    product_urls = _load_de_tonies_urls_from_sitemap()
    print("Sitemap DE tonie URLs:", len(product_urls))

    print("Fetching product JSON details...")
    scraped, fetch_errors = asyncio.run(
        _fetch_all_products(
            product_urls,
            build_id=build_id,
            concurrency=max(1, int(args.concurrency)),
        )
    )
    print("Fetched product rows:", len(scraped), "errors:", fetch_errors)

    # Dedupe scraped rows by normalized title
    scraped_by_norm: dict[str, ScrapedTonie] = {}
    for item in scraped:
        key = _normalize(item.title)
        if not key:
            continue
        scraped_by_norm.setdefault(key, item)

    legacy_by_norm = {_normalize(str(row.get("title") or "")): row for row in legacy_seed}

    merged: list[dict] = [dict(row) for row in legacy_seed]
    used_ids = {_entry_num(str(row.get("id") or "")) for row in merged}
    used_ids.discard(-1)
    next_id = (max(used_ids) + 1) if used_ids else 1

    # Enrich existing rows when same normalized title is found in scraped catalog.
    for key, legacy in legacy_by_norm.items():
        source = scraped_by_norm.get(key)
        if not source:
            continue

        legacy["aliases"] = _merge_aliases(
            list(legacy.get("aliases") or []),
            _aliases_for_scraped(source),
        )

    # Add new rows for scraped titles that are not in legacy seed.
    new_rows: list[dict] = []
    for key, source in sorted(
        scraped_by_norm.items(),
        key=lambda kv: (kv[1].series.lower(), kv[1].name.lower()),
    ):
        if key in legacy_by_norm:
            continue

        tonie_id = f"tn_{next_id:03d}"
        next_id += 1

        aliases = _aliases_for_scraped(source)

        new_rows.append(
            {
                "id": tonie_id,
                "title": source.title,
                "series": source.series,
                "aliases": aliases,
            }
        )

    merged.extend(new_rows)
    merged.sort(key=lambda row: _entry_num(str(row.get("id") or "")))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("---")
    print("Legacy seed entries:", len(legacy_seed))
    print("Unique scraped entries:", len(scraped_by_norm))
    print("New appended entries:", len(new_rows))
    print("Merged catalog entries:", len(merged))
    print("Output:", output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
