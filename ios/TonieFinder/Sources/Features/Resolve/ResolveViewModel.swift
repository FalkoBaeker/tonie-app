import Foundation

struct ResolveItem: Identifiable, Hashable {
    let tonieId: String
    let title: String
    let score: Double

    var id: String { tonieId }
}

protocol ResolvePricingAPI {
    func resolve(query: String) async throws -> [ResolveItem]
    func fetchPricing(tonieId: String, condition: TonieCondition) async throws -> PriceTriple
}

struct LiveResolvePricingAPI: ResolvePricingAPI {
    private let client: APIClient

    init(client: APIClient = APIClient()) {
        self.client = client
    }

    func resolve(query: String) async throws -> [ResolveItem] {
        let candidates = try await client.resolve(query: query)
        return candidates.map {
            ResolveItem(tonieId: $0.id, title: $0.title, score: $0.score)
        }
    }

    func fetchPricing(tonieId: String, condition: TonieCondition) async throws -> PriceTriple {
        try await client.fetchPricingOrThrow(tonieId: tonieId, condition: condition)
    }
}

@MainActor
final class ResolveViewModel: ObservableObject {
    @Published var query: String = ""
    @Published var isLoading: Bool = false
    @Published var results: [ResolveItem] = []
    @Published var errorMessage: String?

    private let api: ResolvePricingAPI

    init(api: ResolvePricingAPI = LiveResolvePricingAPI()) {
        self.api = api
    }

    func search() {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            results = []
            errorMessage = "Bitte Suchbegriff eingeben."
            return
        }

        isLoading = true
        errorMessage = nil

        Task {
            defer { isLoading = false }

            do {
                let resolved = try await api.resolve(query: trimmed)
                results = resolved
                if resolved.isEmpty {
                    errorMessage = "Keine Treffer gefunden."
                }
            } catch {
                errorMessage = APIError.map(error).userMessage
            }
        }
    }
}
