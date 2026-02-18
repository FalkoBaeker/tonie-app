from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class PriceTriple:
    instant: float
    fair: float
    patience: float


CONDITION_FACTORS = {
    "ovp": 1.35,
    "new_open": 1.20,
    "very_good": 1.00,
    "good": 0.90,
    "played": 0.75,
    "defective": 0.35,
}


def _base_price_from_tonie_id(tonie_id: str) -> float:
    # Deterministic placeholder until market ingestion is connected.
    h = hashlib.sha1(tonie_id.encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    return 10.0 + (n % 1800) / 100.0  # 10.00 .. 27.99


def get_price_triple(tonie_id: str, condition: str) -> PriceTriple:
    factor = CONDITION_FACTORS.get(condition, CONDITION_FACTORS["good"])
    fair = round(_base_price_from_tonie_id(tonie_id) * factor, 2)
    instant = round(fair * 0.85, 2)
    patience = round(fair * 1.15, 2)
    return PriceTriple(instant=instant, fair=fair, patience=patience)
