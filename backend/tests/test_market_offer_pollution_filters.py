from __future__ import annotations

import unittest

from app.services.market_ingestion import filter_market_records_for_tonie, is_relevant_offer_title_for_tonie


class MarketOfferPollutionFiltersTests(unittest.TestCase):
    def test_rejects_media_noise_even_with_title_overlap(self) -> None:
        target_title = "Bibi & Tina - Der verschwundene Schatz"
        aliases = ["Bibi und Tina"]

        self.assertFalse(
            is_relevant_offer_title_for_tonie(
                offer_title="Bibi und Tina Hörspiel CD Folge 1",
                tonie_title=target_title,
                aliases=aliases,
            )
        )
        self.assertFalse(
            is_relevant_offer_title_for_tonie(
                offer_title="Bibi und Tina Buch Hardcover",
                tonie_title=target_title,
                aliases=aliases,
            )
        )
        self.assertFalse(
            is_relevant_offer_title_for_tonie(
                offer_title="Bibi und Tina Figur Der verschwundene Schatz",
                tonie_title=target_title,
                aliases=aliases,
            )
        )
        self.assertTrue(
            is_relevant_offer_title_for_tonie(
                offer_title="Tonie Hörfigur Bibi und Tina Der verschwundene Schatz",
                tonie_title=target_title,
                aliases=aliases,
            )
        )

    def test_ebay_rows_can_match_without_explicit_tonie_token(self) -> None:
        records = [
            {
                "source": "ebay_sold",
                "title": "Steiff Soft Cuddly Friends Ben Teddybär Hörspiel",
                "price_eur": 299.0,
                "url": "https://example.org/ebay-ben",
            },
            {
                "source": "ebay_sold",
                "title": "Steiff Soft Cuddly Friends Jimmy Bär Hörspiel",
                "price_eur": 120.0,
                "url": "https://example.org/ebay-jimmy",
            },
        ]

        filtered = filter_market_records_for_tonie(
            records=records,
            tonie_title="Steiff Soft Cuddly Friends – Ben Teddybär Hörspiel",
            aliases=["Ben Teddybär Hörspiel"],
            series="Steiff Soft Cuddly Friends",
            sources={"ebay_sold"},
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["url"], "https://example.org/ebay-ben")

    def test_filter_only_scopes_kleinanzeigen_offer(self) -> None:
        records = [
            {
                "source": "kleinanzeigen_offer",
                "title": "Bibi und Tina Hörspiel CD",
                "price_eur": 4.0,
                "url": "https://example.org/1",
            },
            {
                "source": "kleinanzeigen_offer",
                "title": "Tonie Hörfigur Bibi und Tina Der verschwundene Schatz",
                "price_eur": 16.0,
                "url": "https://example.org/2",
            },
            {
                "source": "ebay_sold",
                "title": "Bibi und Tina Hörspiel CD",
                "price_eur": 6.0,
                "url": "https://example.org/3",
            },
        ]

        filtered = filter_market_records_for_tonie(
            records=records,
            tonie_title="Bibi & Tina - Der verschwundene Schatz",
            aliases=["Bibi und Tina"],
            sources={"kleinanzeigen_offer"},
        )
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]["source"], "kleinanzeigen_offer")
        self.assertEqual(filtered[0]["url"], "https://example.org/2")
        self.assertEqual(filtered[1]["source"], "ebay_sold")


if __name__ == "__main__":
    unittest.main()
