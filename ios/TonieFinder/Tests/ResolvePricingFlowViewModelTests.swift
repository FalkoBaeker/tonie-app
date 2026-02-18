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
}
