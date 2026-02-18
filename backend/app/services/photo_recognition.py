from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.tonie_resolver import get_resolver

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency guard
    Image = None


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_REF_DIR = _DATA_DIR / "tonie_refs"
_DEFAULT_INDEX_PATH = _DATA_DIR / "tonie_reference_index.json"
_SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class RecognitionCandidate:
    tonie_id: str
    title: str
    score: float


@dataclass
class RecognitionResult:
    status: str
    candidates: list[RecognitionCandidate]
    message: str | None = None


@dataclass
class _ImageDescriptor:
    dhash_hex: str
    mean_rgb: tuple[float, float, float]


def _pil_ready() -> bool:
    return Image is not None


def _resample_lanczos() -> int:
    if Image is None:  # pragma: no cover
        raise RuntimeError("Pillow not available")

    resampling = getattr(Image, "Resampling", None)
    if resampling is not None:
        return int(resampling.LANCZOS)
    return int(Image.LANCZOS)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _descriptor_from_image(img: Any) -> _ImageDescriptor:
    lanczos = _resample_lanczos()

    gray = img.convert("L").resize((9, 8), lanczos)
    g = list(gray.getdata())

    bits: list[int] = []
    for row in range(8):
        row_start = row * 9
        for col in range(8):
            left = g[row_start + col]
            right = g[row_start + col + 1]
            bits.append(1 if left > right else 0)

    value = 0
    for bit in bits:
        value = (value << 1) | bit
    dhash_hex = f"{value:016x}"

    rgb = img.convert("RGB").resize((32, 32), lanczos)
    pixels = list(rgb.getdata())
    n = max(1, len(pixels))

    mean_r = sum(px[0] for px in pixels) / (255.0 * n)
    mean_g = sum(px[1] for px in pixels) / (255.0 * n)
    mean_b = sum(px[2] for px in pixels) / (255.0 * n)

    return _ImageDescriptor(
        dhash_hex=dhash_hex,
        mean_rgb=(round(mean_r, 6), round(mean_g, 6), round(mean_b, 6)),
    )


def _descriptor_from_bytes(image_bytes: bytes) -> _ImageDescriptor:
    if not _pil_ready():
        raise RuntimeError("Pillow is not installed")

    from io import BytesIO

    if not image_bytes:
        raise ValueError("empty image payload")

    with Image.open(BytesIO(image_bytes)) as img:  # type: ignore[union-attr]
        return _descriptor_from_image(img)


def _hamming_distance_hex(a: str, b: str) -> int:
    try:
        ai = int(a, 16)
        bi = int(b, 16)
    except ValueError:
        return 64
    return (ai ^ bi).bit_count()


def _color_similarity(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dist = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
    # sqrt(3) is the max distance in normalized RGB cube.
    return max(0.0, 1.0 - (dist / math.sqrt(3.0)))


def _reference_root() -> Path:
    root = Path(settings.recognition_reference_dir).expanduser()
    if not root.is_absolute():
        root = _DEFAULT_REF_DIR if str(root) == "./app/data/tonie_refs" else (Path.cwd() / root)
    return root


def _index_path() -> Path:
    path = Path(settings.recognition_index_path).expanduser()
    if not path.is_absolute():
        path = (
            _DEFAULT_INDEX_PATH
            if str(path) == "./app/data/tonie_reference_index.json"
            else (Path.cwd() / path)
        )
    return path


@lru_cache(maxsize=1)
def _load_reference_index() -> dict:
    path = _index_path()
    if not path.exists():
        return {
            "version": 1,
            "generated_at": None,
            "references": [],
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": 1,
            "generated_at": None,
            "references": [],
        }

    if not isinstance(payload, dict):
        return {
            "version": 1,
            "generated_at": None,
            "references": [],
        }

    refs = payload.get("references")
    if not isinstance(refs, list):
        refs = []

    return {
        "version": int(payload.get("version") or 1),
        "generated_at": payload.get("generated_at"),
        "references": refs,
    }


def clear_reference_index_cache() -> None:
    _load_reference_index.cache_clear()


def build_reference_index(
    *,
    reference_root: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    if not _pil_ready():
        raise RuntimeError("Pillow is required to build photo reference index")

    root = reference_root or _reference_root()
    out_path = output_path or _index_path()

    root.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    resolver = get_resolver()
    known_ids = {str(item["id"]): str(item["title"]) for item in resolver.catalog}

    references: list[dict[str, Any]] = []
    scanned_files = 0
    skipped_files = 0

    for tonie_dir in sorted(root.iterdir()):
        if not tonie_dir.is_dir():
            continue

        tonie_id = tonie_dir.name.strip()
        title = known_ids.get(tonie_id)
        if not title:
            continue

        for file_path in sorted(tonie_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue

            scanned_files += 1

            try:
                with Image.open(file_path) as img:  # type: ignore[union-attr]
                    descriptor = _descriptor_from_image(img)
            except Exception:
                skipped_files += 1
                continue

            references.append(
                {
                    "tonie_id": tonie_id,
                    "title": title,
                    "path": str(file_path.relative_to(root)),
                    "dhash": descriptor.dhash_hex,
                    "mean_rgb": [
                        descriptor.mean_rgb[0],
                        descriptor.mean_rgb[1],
                        descriptor.mean_rgb[2],
                    ],
                }
            )

    payload = {
        "version": 1,
        "generated_at": _now_iso(),
        "reference_root": str(root),
        "reference_count": len(references),
        "tonie_count": len({r["tonie_id"] for r in references}),
        "scanned_files": scanned_files,
        "skipped_files": skipped_files,
        "references": references,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_reference_index_cache()
    return payload


def get_photo_recognition_status() -> dict:
    index = _load_reference_index()
    references = [r for r in index.get("references", []) if isinstance(r, dict)]
    tonie_count = len({str(r.get("tonie_id") or "") for r in references if r.get("tonie_id")})

    ready = _pil_ready() and len(references) > 0
    if not _pil_ready():
        message = "Pillow not installed"
    elif not references:
        message = "No indexed reference images"
    else:
        message = None

    return {
        "ready": ready,
        "reference_count": len(references),
        "tonie_count": tonie_count,
        "generated_at": index.get("generated_at"),
        "message": message,
    }


def recognize_tonie_from_image_bytes(image_bytes: bytes, top_k: int = 3) -> RecognitionResult:
    if not _pil_ready():
        return RecognitionResult(
            status="not_configured",
            candidates=[],
            message="Pillow not installed on backend",
        )

    index = _load_reference_index()
    references = [r for r in index.get("references", []) if isinstance(r, dict)]
    if not references:
        return RecognitionResult(
            status="not_configured",
            candidates=[],
            message="No indexed reference images available",
        )

    try:
        descriptor = _descriptor_from_bytes(image_bytes)
    except Exception:
        return RecognitionResult(
            status="not_found",
            candidates=[],
            message="Image could not be processed",
        )

    by_tonie: dict[str, RecognitionCandidate] = {}

    for row in references:
        tonie_id = str(row.get("tonie_id") or "").strip()
        title = str(row.get("title") or tonie_id)
        dhash = str(row.get("dhash") or "")

        mean_rgb_raw = row.get("mean_rgb") or [0.0, 0.0, 0.0]
        try:
            mean_rgb = (
                float(mean_rgb_raw[0]),
                float(mean_rgb_raw[1]),
                float(mean_rgb_raw[2]),
            )
        except Exception:
            mean_rgb = (0.0, 0.0, 0.0)

        hash_distance = _hamming_distance_hex(descriptor.dhash_hex, dhash)
        hash_similarity = max(0.0, 1.0 - (hash_distance / 64.0))
        color_similarity = _color_similarity(descriptor.mean_rgb, mean_rgb)
        combined = round((hash_similarity * 0.86) + (color_similarity * 0.14), 4)

        if combined < 0.45:
            continue

        candidate = RecognitionCandidate(tonie_id=tonie_id, title=title, score=combined)
        prev = by_tonie.get(tonie_id)
        if prev is None or candidate.score > prev.score:
            by_tonie[tonie_id] = candidate

    candidates = sorted(by_tonie.values(), key=lambda c: c.score, reverse=True)
    if not candidates:
        return RecognitionResult(status="not_found", candidates=[], message="No matching Tonie found")

    top_k = max(1, min(5, int(top_k)))
    candidates = candidates[:top_k]

    top = candidates[0].score
    second = candidates[1].score if len(candidates) > 1 else 0.0

    if top < settings.recognition_min_score:
        return RecognitionResult(
            status="not_found",
            candidates=[],
            message="Recognition confidence too low",
        )

    if top >= settings.recognition_resolved_score and (top - second) >= settings.recognition_resolved_gap:
        return RecognitionResult(status="resolved", candidates=[candidates[0]])

    return RecognitionResult(status="needs_confirmation", candidates=candidates)
