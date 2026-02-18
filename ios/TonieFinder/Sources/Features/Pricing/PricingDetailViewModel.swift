import Foundation

@MainActor
final class PricingDetailViewModel: ObservableObject {
    let item: ResolveItem

    @Published var condition: TonieCondition = .good
    @Published var isLoading: Bool = false
    @Published var pricing: PriceTriple?
    @Published var errorMessage: String?

    private let api: ResolvePricingAPI

    init(item: ResolveItem, api: ResolvePricingAPI = LiveResolvePricingAPI()) {
        self.item = item
        self.api = api
    }

    func load() {
        isLoading = true
        errorMessage = nil

        let tonieId = item.tonieId
        let selectedCondition = condition

        Task {
            defer { isLoading = false }

            do {
                let loaded = try await api.fetchPricing(tonieId: tonieId, condition: selectedCondition)
                pricing = loaded
            } catch {
                pricing = nil
                errorMessage = APIError.map(error).userMessage
            }
        }
    }
}
