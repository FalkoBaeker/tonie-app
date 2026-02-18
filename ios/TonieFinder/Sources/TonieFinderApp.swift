import PhotosUI
import SwiftUI

@main
struct TonieFinderApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .preferredColorScheme(.light)
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isLoggedIn {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut, value: auth.isLoggedIn)
    }
}

// MARK: - Design

enum TFColor {
    static let tonieRed = Color(hex: "#E30613")
    static let silver = Color(hex: "#C0C0C0")
    static let background = Color(hex: "#F6F7F9")
    static let card = Color.white
}

extension Color {
    init(hex: String) {
        let hex = hex.replacingOccurrences(of: "#", with: "")
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255.0
        let g = Double((int >> 8) & 0xFF) / 255.0
        let b = Double(int & 0xFF) / 255.0
        self.init(red: r, green: g, blue: b)
    }
}

struct Card<Content: View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }

    var body: some View {
        content
            .padding(16)
            .background(TFColor.card)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: TFColor.silver.opacity(0.35), radius: 12, x: 0, y: 6)
    }
}

// MARK: - Models

enum TonieCondition: String, CaseIterable, Identifiable {
    case ovp = "Neu versiegelt (OVP)"
    case newOpen = "Neu offen"
    case veryGood = "Sehr gut"
    case good = "Gut"
    case played = "Stark bespielt"
    case defective = "Defekt"

    var id: String { rawValue }

    var apiValue: String {
        switch self {
        case .ovp: return "ovp"
        case .newOpen: return "new_open"
        case .veryGood: return "very_good"
        case .good: return "good"
        case .played: return "played"
        case .defective: return "defective"
        }
    }

    init?(apiValue: String) {
        switch apiValue {
        case "ovp": self = .ovp
        case "new_open": self = .newOpen
        case "very_good": self = .veryGood
        case "good": self = .good
        case "played": self = .played
        case "defective": self = .defective
        default: return nil
        }
    }
}

struct TonieCandidate: Identifiable, Hashable {
    let id: String
    let title: String
    let score: Double
}

struct PriceTriple {
    let instant: Double
    let fair: Double
    let patience: Double
    let sampleSize: Int?
    let effectiveSampleSize: Double?
    let source: String?
    let qualityTier: String?
    let confidenceScore: Double?
}

struct WatchItem: Identifiable {
    let id: String
    let backendId: Int?
    let tonieId: String
    let title: String
    let condition: TonieCondition
    let lastFairPrice: Double
}

// MARK: - ViewModels

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var email: String = ""
    @Published var password: String = ""
    @Published var isLoggedIn = false
    @Published var isLoading = false
    @Published var authToken: String?
    @Published var statusText: String?

    private let api = APIClient()

    func login() {
        let normalizedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalizedEmail.isEmpty, !password.isEmpty else { return }

        isLoading = true
        statusText = nil

        Task {
            defer { isLoading = false }

            do {
                var session = try await api.login(email: normalizedEmail, password: password)
                if session == nil {
                    session = try await api.register(email: normalizedEmail, password: password)
                }

                if let session {
                    email = session.userEmail
                    authToken = session.token
                    isLoggedIn = true
                    statusText = nil
                    return
                }

                statusText = "Login fehlgeschlagen. Prüfe E-Mail/Passwort."
                return
            } catch {
                // Offline/prototype fallback so core flows stay usable.
                email = normalizedEmail
                authToken = nil
                isLoggedIn = true
                statusText = "Lokaler Login aktiv (Backend aktuell nicht erreichbar)."
            }
        }
    }

    func logout() {
        let token = authToken
        isLoggedIn = false
        authToken = nil
        statusText = nil
        password = ""

        if let token {
            Task { try? await api.logout(token: token) }
        }
    }
}

@MainActor
final class PricingViewModel: ObservableObject {
    @Published var query = ""
    @Published var condition: TonieCondition = .good
    @Published var candidates: [TonieCandidate] = []
    @Published var selected: TonieCandidate?
    @Published var prices: PriceTriple?
    @Published var errorText: String?
    @Published var infoText: String?
    @Published var isLoading = false

    private let api = APIClient()
    private var searchTask: Task<Void, Never>?
    private var priceTask: Task<Void, Never>?

    func search() {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }

        searchTask?.cancel()
        priceTask?.cancel()

        isLoading = true
        errorText = nil
        infoText = nil
        selected = nil
        prices = nil

        searchTask = Task {
            defer {
                isLoading = false
                searchTask = nil
            }

            do {
                let resolved = try await api.resolveTonie(query: q)
                guard !Task.isCancelled else { return }

                candidates = resolved
                if resolved.isEmpty {
                    errorText = "Nicht eindeutig gefunden. Bitte präziser eingeben."
                }
            } catch {
                guard !Task.isCancelled else { return }
                errorText = "Suche fehlgeschlagen. Bitte später erneut versuchen."
            }
        }
    }

    func recognizePhoto(_ imageData: Data) {
        searchTask?.cancel()
        priceTask?.cancel()

        isLoading = true
        errorText = nil
        infoText = "Foto wird analysiert …"
        selected = nil
        prices = nil
        candidates = []

        searchTask = Task {
            defer {
                isLoading = false
                searchTask = nil
            }

            do {
                let result = try await api.recognizeToniePhoto(imageData: imageData, topK: 3)
                guard !Task.isCancelled else { return }

                candidates = result.candidates

                switch result.status {
                case "resolved":
                    if let top = result.candidates.first {
                        infoText = "Foto erkannt: \(top.title)"
                        choose(top)
                    } else {
                        errorText = "Kein Treffer gefunden."
                    }
                case "needs_confirmation":
                    infoText = "Foto erkannt, bitte Treffer bestätigen."
                    if result.candidates.isEmpty {
                        errorText = "Kein sicherer Treffer gefunden."
                    }
                case "not_configured":
                    errorText = result.message ?? "Fotoerkennung ist noch nicht eingerichtet."
                case "not_found":
                    errorText = result.message ?? "Kein passender Tonie gefunden."
                default:
                    errorText = result.message ?? "Fotoerkennung fehlgeschlagen."
                }
            } catch {
                guard !Task.isCancelled else { return }
                errorText = "Fotoerkennung fehlgeschlagen."
            }
        }
    }

    func choose(_ candidate: TonieCandidate) {
        selected = candidate
        errorText = nil
        infoText = nil

        priceTask?.cancel()

        let selectedId = candidate.id
        let selectedCondition = condition

        priceTask = Task {
            defer { priceTask = nil }

            do {
                if let backendPrices = try await api.fetchPricing(tonieId: selectedId, condition: selectedCondition) {
                    guard !Task.isCancelled, selected?.id == selectedId else { return }
                    prices = backendPrices
                    return
                }
            } catch {
                // fall through to local fallback
            }

            guard !Task.isCancelled, selected?.id == selectedId else { return }

            let base = max(4.0, 8.0 + (candidate.score * 20.0))
            let conditionFactor: Double
            switch selectedCondition {
            case .ovp: conditionFactor = 1.35
            case .newOpen: conditionFactor = 1.20
            case .veryGood: conditionFactor = 1.00
            case .good: conditionFactor = 0.90
            case .played: conditionFactor = 0.75
            case .defective: conditionFactor = 0.35
            }

            let fair = (base * conditionFactor).rounded(to: 2)
            prices = PriceTriple(
                instant: (fair * 0.85).rounded(to: 2),
                fair: fair,
                patience: (fair * 1.15).rounded(to: 2),
                sampleSize: nil,
                effectiveSampleSize: nil,
                source: "local_fallback",
                qualityTier: "low",
                confidenceScore: 0.05
            )
        }
    }

    func addSelectedToWatchlist(authToken: String?) {
        guard let selected, let _ = prices else {
            errorText = "Bitte erst einen Treffer auswählen."
            return
        }

        guard let authToken else {
            infoText = "Watchlist-Sync braucht Backend-Login."
            return
        }

        Task {
            do {
                let added = try await api.addWatchlistItem(
                    token: authToken,
                    tonieId: selected.id,
                    title: selected.title,
                    condition: condition
                )
                if added != nil {
                    infoText = "Zur Watchlist hinzugefügt."
                } else {
                    infoText = "Konnte nicht zur Watchlist hinzufügen."
                }
            } catch {
                infoText = "Watchlist-Update fehlgeschlagen."
            }
        }
    }
}

@MainActor
final class WatchlistViewModel: ObservableObject {
    @Published var items: [WatchItem] = []
    @Published var isLoading = false
    @Published var errorText: String?
    @Published var infoText: String?

    private let api = APIClient()
    private var loadTask: Task<Void, Never>?

    private let localFallback: [WatchItem] = [
        WatchItem(
            id: UUID().uuidString,
            backendId: nil,
            tonieId: "local_1",
            title: "Der Löwe, der nicht schreiben konnte",
            condition: .veryGood,
            lastFairPrice: 18.50
        ),
        WatchItem(
            id: UUID().uuidString,
            backendId: nil,
            tonieId: "local_2",
            title: "Benjamin Blümchen – Der Zoo-Kindergarten",
            condition: .good,
            lastFairPrice: 14.90
        ),
    ]

    func load(authToken: String?, refreshPrices: Bool = false) {
        loadTask?.cancel()

        guard let authToken else {
            items = localFallback
            errorText = nil
            infoText = "Lokale Watchlist (kein Backend-Login)."
            return
        }

        isLoading = true
        errorText = nil
        infoText = refreshPrices ? "Preise werden aktualisiert …" : nil

        loadTask = Task {
            defer {
                isLoading = false
                loadTask = nil
            }

            do {
                let backendItems = try await api.fetchWatchlist(
                    token: authToken,
                    refreshPrices: refreshPrices
                )
                guard !Task.isCancelled else { return }
                items = backendItems

                if refreshPrices {
                    infoText = "Preise aktualisiert (\(backendItems.count) Einträge)."
                }
            } catch {
                guard !Task.isCancelled else { return }
                items = localFallback
                errorText = "Watchlist konnte nicht geladen werden."
            }
        }
    }

    func remove(item: WatchItem, authToken: String?) {
        guard let backendId = item.backendId, let authToken else {
            items.removeAll { $0.id == item.id }
            return
        }

        Task {
            do {
                let ok = try await api.deleteWatchlistItem(token: authToken, itemId: backendId)
                if ok {
                    items.removeAll { $0.id == item.id }
                } else {
                    errorText = "Eintrag konnte nicht gelöscht werden."
                }
            } catch {
                errorText = "Eintrag konnte nicht gelöscht werden."
            }
        }
    }
}

extension Double {
    func rounded(to places: Int) -> Double {
        let p = pow(10.0, Double(places))
        return (self * p).rounded() / p
    }
}

// MARK: - API Config

enum AppConfig {
    private static let simulatorDefault = "http://127.0.0.1:8787/api"
    private static let deviceDefault = "http://192.168.178.100:8787/api"

    static var apiBaseURL: String {
        if let env = ProcessInfo.processInfo.environment["TF_API_BASE_URL"], !env.isEmpty {
            return env
        }

        if let plistValue = Bundle.main.object(forInfoDictionaryKey: "TF_API_BASE_URL") as? String,
           !plistValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return plistValue
        }

        #if targetEnvironment(simulator)
        return simulatorDefault
        #else
        return deviceDefault
        #endif
    }
}

// MARK: - API Client

final class APIClient {
    private let baseURL: String

    init(baseURL: String = AppConfig.apiBaseURL) {
        self.baseURL = baseURL
    }

    struct ResolveResponse: Decodable {
        struct CandidateDTO: Decodable {
            let tonie_id: String
            let title: String
            let score: Double
        }
        let status: String
        let candidates: [CandidateDTO]
    }

    struct RecognizeResponse: Decodable {
        let status: String
        let candidates: [ResolveResponse.CandidateDTO]
        let message: String?
    }

    struct PricingResponse: Decodable {
        let tonie_id: String
        let condition: String
        let sofortverkaufspreis: Double
        let fairer_marktpreis: Double
        let geduldspreis: Double
        let sample_size: Int
        let effective_sample_size: Double?
        let source: String
        let quality_tier: String?
        let confidence_score: Double?
    }

    struct AuthRequest: Encodable {
        let email: String
        let password: String
    }

    struct AuthResponse: Decodable {
        struct UserDTO: Decodable {
            let id: Int
            let email: String
        }

        let token: String
        let user: UserDTO
        let expires_at: String
    }

    struct AuthSession {
        let token: String
        let userId: Int
        let userEmail: String
        let expiresAt: String
    }

    struct WatchlistAddRequest: Encodable {
        let tonie_id: String
        let title: String
        let condition: String
    }

    struct WatchlistItemDTO: Decodable {
        let id: Int
        let tonie_id: String
        let title: String
        let condition: String
        let last_fair_price: Double
    }

    private func makeURL(path: String) -> URL? {
        URL(string: "\(baseURL)\(path)")
    }

    func resolveTonie(query: String) async throws -> [TonieCandidate] {
        guard let url = makeURL(path: "/tonies/resolve") else {
            return []
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["query": query])

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                return []
            }
            let decoded = try JSONDecoder().decode(ResolveResponse.self, from: data)
            return decoded.candidates.map { TonieCandidate(id: $0.tonie_id, title: $0.title, score: $0.score) }
        } catch {
            // Fallback local fuzzy-like behavior while backend is unavailable.
            return [
                TonieCandidate(id: "local_1", title: query, score: 0.92),
                TonieCandidate(id: "local_2", title: "\(query) – Hörspiel", score: 0.77),
                TonieCandidate(id: "local_3", title: "\(query) – Reihe 2", score: 0.65)
            ]
        }
    }

    func recognizeToniePhoto(
        imageData: Data,
        topK: Int = 3
    ) async throws -> (status: String, candidates: [TonieCandidate], message: String?) {
        guard let url = makeURL(path: "/tonies/recognize?top_k=\(topK)") else {
            return ("not_found", [], "Ungültige API-URL")
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(Data("Content-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\n".utf8))
        body.append(Data("Content-Type: image/jpeg\r\n\r\n".utf8))
        body.append(imageData)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            return ("not_found", [], "Keine Serverantwort")
        }

        guard (200..<300).contains(http.statusCode) else {
            return ("not_found", [], "Fotoerkennung derzeit nicht verfügbar")
        }

        let decoded = try JSONDecoder().decode(RecognizeResponse.self, from: data)
        let mapped = decoded.candidates.map {
            TonieCandidate(id: $0.tonie_id, title: $0.title, score: $0.score)
        }

        return (decoded.status, mapped, decoded.message)
    }

    func fetchPricing(tonieId: String, condition: TonieCondition) async throws -> PriceTriple? {
        guard let url = makeURL(path: "/pricing/\(tonieId)?condition=\(condition.apiValue)") else {
            return nil
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            return nil
        }

        let decoded = try JSONDecoder().decode(PricingResponse.self, from: data)
        return PriceTriple(
            instant: decoded.sofortverkaufspreis,
            fair: decoded.fairer_marktpreis,
            patience: decoded.geduldspreis,
            sampleSize: decoded.sample_size,
            effectiveSampleSize: decoded.effective_sample_size,
            source: decoded.source,
            qualityTier: decoded.quality_tier,
            confidenceScore: decoded.confidence_score
        )
    }

    func login(email: String, password: String) async throws -> AuthSession? {
        try await authenticate(path: "/auth/login", email: email, password: password)
    }

    func register(email: String, password: String) async throws -> AuthSession? {
        try await authenticate(path: "/auth/register", email: email, password: password)
    }

    private func authenticate(path: String, email: String, password: String) async throws -> AuthSession? {
        guard let url = makeURL(path: path) else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(AuthRequest(email: email, password: password))

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { return nil }

        guard (200..<300).contains(http.statusCode) else {
            if [400, 401, 404, 409, 422].contains(http.statusCode) {
                return nil
            }
            return nil
        }

        let decoded = try JSONDecoder().decode(AuthResponse.self, from: data)
        return AuthSession(
            token: decoded.token,
            userId: decoded.user.id,
            userEmail: decoded.user.email,
            expiresAt: decoded.expires_at
        )
    }

    func logout(token: String) async throws {
        guard let url = makeURL(path: "/auth/logout") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        _ = try await URLSession.shared.data(for: request)
    }

    func fetchWatchlist(token: String, refreshPrices: Bool = false) async throws -> [WatchItem] {
        let path = refreshPrices ? "/watchlist?refresh=true" : "/watchlist"
        guard let url = makeURL(path: path) else { return [] }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            return []
        }

        let decoded = try JSONDecoder().decode([WatchlistItemDTO].self, from: data)
        return decoded.map {
            WatchItem(
                id: "\($0.id)",
                backendId: $0.id,
                tonieId: $0.tonie_id,
                title: $0.title,
                condition: TonieCondition(apiValue: $0.condition) ?? .good,
                lastFairPrice: $0.last_fair_price
            )
        }
    }

    func addWatchlistItem(
        token: String,
        tonieId: String,
        title: String,
        condition: TonieCondition
    ) async throws -> WatchItem? {
        guard let url = makeURL(path: "/watchlist") else { return nil }

        let payload = WatchlistAddRequest(
            tonie_id: tonieId,
            title: title,
            condition: condition.apiValue
        )

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            return nil
        }

        let item = try JSONDecoder().decode(WatchlistItemDTO.self, from: data)
        return WatchItem(
            id: "\(item.id)",
            backendId: item.id,
            tonieId: item.tonie_id,
            title: item.title,
            condition: TonieCondition(apiValue: item.condition) ?? .good,
            lastFairPrice: item.last_fair_price
        )
    }

    func deleteWatchlistItem(token: String, itemId: Int) async throws -> Bool {
        guard let url = makeURL(path: "/watchlist/\(itemId)") else { return false }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { return false }
        return (200..<300).contains(http.statusCode)
    }
}

// MARK: - Views

struct LoginView: View {
    @EnvironmentObject private var auth: AuthViewModel

    var body: some View {
        ZStack {
            TFColor.background.ignoresSafeArea()

            VStack(spacing: 20) {
                VStack(spacing: 6) {
                    Text("Tonie Finder")
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(TFColor.tonieRed)
                    Text("Preisfindung für Tonies")
                        .foregroundStyle(.secondary)
                }
                .padding(.bottom, 8)

                Card {
                    VStack(spacing: 14) {
                        TextField("E-Mail", text: $auth.email)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.emailAddress)
                            .padding(12)
                            .background(Color.gray.opacity(0.08))
                            .clipShape(RoundedRectangle(cornerRadius: 10))

                        SecureField("Passwort", text: $auth.password)
                            .padding(12)
                            .background(Color.gray.opacity(0.08))
                            .clipShape(RoundedRectangle(cornerRadius: 10))

                        Button(action: auth.login) {
                            if auth.isLoading {
                                ProgressView()
                                    .frame(maxWidth: .infinity)
                            } else {
                                Text("Einloggen")
                                    .bold()
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(TFColor.tonieRed)

                        if let status = auth.statusText, !status.isEmpty {
                            Text(status)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.horizontal)
            }
        }
    }
}

struct MainTabView: View {
    var body: some View {
        TabView {
            PricingView()
                .tabItem {
                    Label("Preis", systemImage: "tag")
                }

            WatchlistView()
                .tabItem {
                    Label("Watchlist", systemImage: "eye")
                }

            AccountView()
                .tabItem {
                    Label("Konto", systemImage: "person")
                }
        }
    }
}

struct PricingView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @StateObject private var vm = PricingViewModel()
    @State private var selectedPhotoItem: PhotosPickerItem?

    var body: some View {
        NavigationStack {
            ZStack {
                TFColor.background.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 14) {
                        Card {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Tonie finden")
                                    .font(.headline)

                                TextField("Titel eingeben", text: $vm.query)
                                    .padding(12)
                                    .background(Color.gray.opacity(0.08))
                                    .clipShape(RoundedRectangle(cornerRadius: 10))

                                Picker("Zustand", selection: $vm.condition) {
                                    ForEach(TonieCondition.allCases) { c in
                                        Text(c.rawValue).tag(c)
                                    }
                                }
                                .pickerStyle(.menu)
                                .onChange(of: vm.condition) {
                                    if let selected = vm.selected {
                                        vm.choose(selected)
                                    }
                                }

                                Button(action: vm.search) {
                                    if vm.isLoading {
                                        ProgressView()
                                            .frame(maxWidth: .infinity)
                                    } else {
                                        Text("Preis ermitteln")
                                            .bold()
                                            .frame(maxWidth: .infinity)
                                    }
                                }
                                .buttonStyle(.borderedProminent)
                                .tint(TFColor.tonieRed)

                                PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                                    Label("Foto erkennen", systemImage: "camera.viewfinder")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .tint(TFColor.silver)

                                Text("Fotoerkennung v1: Bei Unsicherheit bitte Kandidat manuell bestätigen.")
                                    .font(.footnote)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if let errorText = vm.errorText {
                            Card {
                                Text(errorText)
                                    .foregroundStyle(.red)
                            }
                        }

                        if let infoText = vm.infoText, !infoText.isEmpty {
                            Card {
                                Text(infoText)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if !vm.candidates.isEmpty {
                            Card {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("Mögliche Treffer")
                                        .font(.headline)

                                    ForEach(vm.candidates) { c in
                                        Button {
                                            vm.choose(c)
                                        } label: {
                                            HStack {
                                                VStack(alignment: .leading) {
                                                    Text(c.title)
                                                        .foregroundStyle(.primary)
                                                    Text("Score: \(Int(c.score * 100))%")
                                                        .font(.caption)
                                                        .foregroundStyle(.secondary)
                                                }
                                                Spacer()
                                                Image(systemName: "chevron.right")
                                                    .foregroundStyle(.secondary)
                                            }
                                        }
                                        .buttonStyle(.plain)
                                        Divider()
                                    }
                                }
                            }
                        }

                        if let p = vm.prices {
                            Card {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("Preisvorschlag")
                                        .font(.headline)
                                    PriceRow(title: "Sofortverkaufspreis", value: p.instant)
                                    PriceRow(title: "Fairer Marktpreis", value: p.fair)
                                    PriceRow(title: "Geduldspreis", value: p.patience)

                                    Divider()
                                    if let tier = p.qualityTier {
                                        let label: String
                                        switch tier {
                                        case "high": label = "Preisqualität: Hoch"
                                        case "medium": label = "Preisqualität: Mittel"
                                        default: label = "Preisqualität: Niedrig"
                                        }
                                        Text(label)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    if let confidence = p.confidenceScore {
                                        Text("Confidence: \(Int((confidence * 100).rounded()))%")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }

                                    if let sample = p.sampleSize, sample > 0 {
                                        Text("Datenbasis: \(sample) Verkäufe")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)

                                        if let effective = p.effectiveSampleSize {
                                            Text(
                                                "Effektive Datenbasis (gewichtet): \(effective, specifier: "%.1f")"
                                            )
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                        }

                                        if let source = p.source, source.contains("blended_weighted") {
                                            Text("Preis aus mehreren Quellen (niedriger gewichtete Nebenquellen)")
                                                .font(.caption2)
                                                .foregroundStyle(.secondary)
                                        }
                                    } else if p.source == "fallback_no_live_market_data" {
                                        Text("Fallback: zu wenig aktuelle Verkäufe")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    } else if p.source == "local_fallback" {
                                        Text("Fallback-Schätzung (Backend nicht erreichbar)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    Button {
                                        vm.addSelectedToWatchlist(authToken: auth.authToken)
                                    } label: {
                                        Text("Zur Watchlist hinzufügen")
                                            .bold()
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.bordered)
                                    .tint(TFColor.tonieRed)
                                }
                            }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Tonie Finder")
            .onChange(of: selectedPhotoItem) { _, newItem in
                guard let newItem else { return }

                Task {
                    do {
                        if let data = try await newItem.loadTransferable(type: Data.self) {
                            await MainActor.run {
                                vm.recognizePhoto(data)
                            }
                        } else {
                            await MainActor.run {
                                vm.errorText = "Foto konnte nicht gelesen werden."
                            }
                        }
                    } catch {
                        await MainActor.run {
                            vm.errorText = "Foto konnte nicht verarbeitet werden."
                        }
                    }
                }
            }
        }
    }
}

struct PriceRow: View {
    let title: String
    let value: Double

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            Text(value, format: .currency(code: "EUR"))
                .bold()
                .foregroundStyle(TFColor.tonieRed)
        }
        .padding(.vertical, 2)
    }
}

struct WatchlistView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @StateObject private var vm = WatchlistViewModel()

    var body: some View {
        NavigationStack {
            List {
                if vm.isLoading {
                    ProgressView("Lade Watchlist …")
                }

                if let errorText = vm.errorText {
                    Text(errorText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if let infoText = vm.infoText, !infoText.isEmpty {
                    Text(infoText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                ForEach(vm.items) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.title)
                        Text("\(item.condition.rawValue) · Fair \(item.lastFairPrice, format: .currency(code: "EUR"))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .onDelete { offsets in
                    for index in offsets {
                        let item = vm.items[index]
                        vm.remove(item: item, authToken: auth.authToken)
                    }
                }
            }
            .navigationTitle("Watchlist")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if auth.authToken != nil {
                        Button("Preise aktualisieren") {
                            vm.load(authToken: auth.authToken, refreshPrices: true)
                        }
                        .disabled(vm.isLoading)
                    }
                }
            }
            .task {
                vm.load(authToken: auth.authToken)
            }
            .refreshable {
                vm.load(authToken: auth.authToken, refreshPrices: true)
            }
        }
    }
}

struct AccountView: View {
    @EnvironmentObject private var auth: AuthViewModel

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Card {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Konto")
                            .font(.headline)
                        Text(auth.email.isEmpty ? "Kein Konto" : auth.email)
                            .foregroundStyle(.secondary)

                        Text(auth.authToken == nil ? "Modus: lokal" : "Modus: Backend-Login")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Button("Ausloggen", role: .destructive) {
                    auth.logout()
                }
            }
            .padding()
            .navigationTitle("Konto")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(TFColor.background)
        }
    }
}
