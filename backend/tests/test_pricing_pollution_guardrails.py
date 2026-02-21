from __future__ import annotations

import unittest

from app.core.config import settings
from app.services.market_ingestion import filter_market_records_for_tonie
from app.services.pricing_engine import (
    _apply_quantile_guardrail,
    _price_bounds_for_tonie,
    _weighted_points_from_records,
    _weighted_quantile,
)


class PricingPollutionGuardrailsTests(unittest.TestCase):
    def test_quantile_guardrail_clamps_implausible_q25_gap(self) -> None:
        q25, q50, q75 = _apply_quantile_guardrail(q25=4.0, q50=20.0, q75=23.0)
        self.assertAlmostEqual(q50, 20.0)
        self.assertAlmostEqual(q75, 23.0)
        self.assertAlmostEqual(q25, 20.0 * settings.market_instant_q25_min_ratio_to_q50, places=6)

    def test_quantile_guardrail_keeps_normal_spread(self) -> None:
        q25, q50, q75 = _apply_quantile_guardrail(q25=14.0, q50=20.0, q75=23.0)
        self.assertAlmostEqual(q25, 14.0)
        self.assertAlmostEqual(q50, 20.0)
        self.assertAlmostEqual(q75, 23.0)

    def test_rarity_price_bounds_raise_upper_limit(self) -> None:
        normal_min, normal_max = _price_bounds_for_tonie({"availability_state": "orderable"})
        rare_min, rare_max = _price_bounds_for_tonie({"availability_state": "endOfLife"})

        self.assertEqual(normal_min, rare_min)
        self.assertGreater(rare_max, normal_max)

    def test_problematic_tonie_before_after_proof(self) -> None:
        # Repro case: query pollution ("CD/Buch") pushes low-end offer quantile far below fair quantile.
        polluted_records = [
            {"source": "kleinanzeigen_offer", "title": "Bibi und Tina Hörspiel CD Folge 1", "price_eur": 4.0},
            {"source": "kleinanzeigen_offer", "title": "Bibi und Tina Buch Hardcover", "price_eur": 5.0},
            {"source": "kleinanzeigen_offer", "title": "Tonie Hörfigur Bibi und Tina Der verschwundene Schatz", "price_eur": 15.0},
            {"source": "kleinanzeigen_offer", "title": "Tonie Bibi und Tina Der verschwundene Schatz", "price_eur": 16.0},
            {"source": "kleinanzeigen_offer", "title": "Tonie Hörfigur Bibi und Tina", "price_eur": 17.0},
        ]

        before_points, _, _, _ = _weighted_points_from_records(polluted_records)
        before_q25 = _weighted_quantile(before_points, 0.25)
        before_q50 = _weighted_quantile(before_points, 0.50)

        filtered_records = filter_market_records_for_tonie(
            records=polluted_records,
            tonie_title="Bibi & Tina - Der verschwundene Schatz",
            aliases=["Bibi und Tina"],
            sources={"kleinanzeigen_offer"},
        )
        after_points, _, _, _ = _weighted_points_from_records(filtered_records)
        after_q25 = _weighted_quantile(after_points, 0.25)
        after_q50 = _weighted_quantile(after_points, 0.50)
        guarded_q25, guarded_q50, _ = _apply_quantile_guardrail(q25=after_q25, q50=after_q50, q75=after_q50)

        self.assertLess(before_q25 / before_q50, 0.5)
        self.assertGreaterEqual(after_q25 / after_q50, 0.85)
        self.assertGreaterEqual(
            guarded_q25 / guarded_q50,
            settings.market_instant_q25_min_ratio_to_q50,
        )


if __name__ == "__main__":
    unittest.main()
