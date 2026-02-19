import XCTest
@testable import TonieFinder

@MainActor
final class ResolvePricingFlowViewModelTests: XCTestCase {
    private struct MockResolvePricingAPI: ResolvePricingAPI {
        var resolveHandler: (String) async throws -> [ResolveItem]
        var pricingHandler: (String, TonieCondition) async throws -> PriceTriple

        func resolve(query: String) async throws -> [ResolveItem] {
            try await resolveHandler(query)
        }

        func fetchPricing(tonieId: String, condition: TonieCondition) async throws -> PriceTriple {
            try await pricingHandler(tonieId, condition)
        }
    }

    private struct MockWatchlistAPI: WatchlistAPI {
        var fetchHandler: (String, Bool) async throws -> [WatchItem]
        var addHandler: (String, String, String, TonieCondition) async throws -> WatchItem
        var deleteHandler: (String, Int) async throws -> Void

        func fetchWatchlist(token: String, refreshPrices: Bool) async throws -> [WatchItem] {
            try await fetchHandler(token, refreshPrices)
        }

        func addWatchlistItem(token: String, tonieId: String, title: String, condition: TonieCondition) async throws -> WatchItem {
            try await addHandler(token, tonieId, title, condition)
        }

        func deleteWatchlistItem(token: String, itemId: Int) async throws {
            try await deleteHandler(token, itemId)
        }
    }

    private struct MockAlertsAPI: AlertsAPI {
        var fetchHandler: (String, Bool) async throws -> [WatchlistAlert]

        func fetchAlerts(token: String, unreadOnly: Bool) async throws -> [WatchlistAlert] {
            try await fetchHandler(token, unreadOnly)
        }
    }

    func testResolveViewModel_setsErrorMessageOnNetworkError() async {
        let api = MockResolvePricingAPI(
            resolveHandler: { _ in throw URLError(.notConnectedToInternet) },
            pricingHandler: { _, _ in
                PriceTriple(
                    instant: 10,
                    fair: 12,
                    patience: 14,
                    sampleSize: 3,
                    effectiveSampleSize: 3,
                    source: "test",
                    qualityTier: "low",
                    confidenceScore: 0.2
                )
            }
        )

        let vm = ResolveViewModel(api: api)
        vm.query = "hexe"
        vm.search()

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertNotNil(vm.errorMessage)
        XCTAssertEqual(vm.errorMessage, APIError.network.userMessage)
    }

    func testPricingDetailViewModel_setsErrorMessageOnNotFound() async {
        let api = MockResolvePricingAPI(
            resolveHandler: { _ in [] },
            pricingHandler: { _, _ in throw APIError.notFound(detail: "tonie not found") }
        )

        let item = ResolveItem(tonieId: "tn_unknown", title: "Unknown", score: 0.2)
        let vm = PricingDetailViewModel(item: item, api: api)
        vm.load()

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertNil(vm.pricing)
        XCTAssertEqual(vm.errorMessage, "tonie not found")
    }

    func testWatchlistViewModel_add_setsErrorMessageOnAPIError() async {
        let api = MockWatchlistAPI(
            fetchHandler: { _, _ in [] },
            addHandler: { _, _, _, _ in throw APIError.unauthorized(detail: nil) },
            deleteHandler: { _, _ in }
        )

        let vm = WatchlistViewModel(api: api)
        let added = await vm.addItem(
            authToken: "token",
            tonieId: "tn_123",
            title: "Hexe Lilli",
            condition: .good
        )

        XCTAssertFalse(added)
        XCTAssertEqual(vm.errorText, APIError.unauthorized(detail: nil).userMessage)
    }

    func testWatchlistViewModel_add_success_insertsItem() async {
        let addedItem = WatchItem(
            id: "42",
            backendId: 42,
            tonieId: "tn_999",
            title: "Bibi Blocksberg",
            condition: .veryGood,
            lastFairPrice: 19.5
        )

        let api = MockWatchlistAPI(
            fetchHandler: { _, _ in [] },
            addHandler: { _, _, _, _ in addedItem },
            deleteHandler: { _, _ in }
        )

        let vm = WatchlistViewModel(api: api)
        let added = await vm.addItem(
            authToken: "token",
            tonieId: "tn_999",
            title: "Bibi Blocksberg",
            condition: .veryGood
        )

        XCTAssertTrue(added)
        XCTAssertEqual(vm.items.count, 1)
        XCTAssertEqual(vm.items.first?.id, "42")
    }

    func testAlertsViewModel_loadWithUnreadOnlyTrue_setsResults() async {
        let api = MockAlertsAPI(fetchHandler: { _, unreadOnly in
            if unreadOnly {
                return [
                    WatchlistAlert(
                        id: "11",
                        title: "Bibi Blocksberg",
                        alertType: "price_drop",
                        message: "Preis gefallen",
                        currentPrice: 17.9,
                        previousPrice: 20.5,
                        targetPrice: 18.0,
                        isUnread: true
                    )
                ]
            }

            return []
        })

        let vm = AlertsViewModel(api: api)
        vm.unreadOnly = true
        vm.load(authToken: "token")

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertEqual(vm.alerts.count, 1)
        XCTAssertEqual(vm.alerts.first?.id, "11")
    }

    func testAlertsViewModel_load_setsErrorMessageOnNetworkError() async {
        let api = MockAlertsAPI(fetchHandler: { _, _ in
            throw URLError(.notConnectedToInternet)
        })

        let vm = AlertsViewModel(api: api)
        vm.load(authToken: "token")

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertEqual(vm.errorText, APIError.network.userMessage)
    }
}
