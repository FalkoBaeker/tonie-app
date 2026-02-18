#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.photo_recognition import build_reference_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build Tonie photo reference index from backend/app/data/tonie_refs/<tonie_id>/* images"
        )
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default="",
        help="Reference image root directory (default: from RECOGNITION_REFERENCE_DIR)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output JSON path (default: from RECOGNITION_INDEX_PATH)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    source_dir = Path(args.source_dir).expanduser() if args.source_dir else None
    output = Path(args.output).expanduser() if args.output else None

    summary = build_reference_index(reference_root=source_dir, output_path=output)

    print("=== PHOTO REFERENCE INDEX BUILT ===")
    print(json.dumps(
        {
            "generated_at": summary.get("generated_at"),
            "reference_root": summary.get("reference_root"),
            "reference_count": summary.get("reference_count"),
            "tonie_count": summary.get("tonie_count"),
            "scanned_files": summary.get("scanned_files"),
            "skipped_files": summary.get("skipped_files"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
