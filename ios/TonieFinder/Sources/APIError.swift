import Foundation

enum APIError: Error, Equatable {
    case invalidURL
    case network
    case unauthorized(detail: String?)
    case forbidden(detail: String?)
    case notFound(detail: String?)
    case conflict(detail: String?)
    case validation(detail: String?)
    case server(statusCode: Int, detail: String?)
    case decoding
    case unknown(detail: String?)

    var userMessage: String {
        switch self {
        case .invalidURL:
            return "Interner Konfigurationsfehler (ungültige API-URL)."
        case .network:
            return "Backend nicht erreichbar. Prüfe Base-URL, WLAN und laufenden Server."
        case let .unauthorized(detail):
            return detail ?? "Nicht eingeloggt oder Session abgelaufen."
        case let .forbidden(detail):
            return detail ?? "Zugriff verweigert."
        case let .notFound(detail):
            return detail ?? "Ressource nicht gefunden."
        case let .conflict(detail):
            return detail ?? "Konflikt: Bitte später erneut versuchen."
        case let .validation(detail):
            return detail ?? "Ungültige Eingabe."
        case let .server(_, detail):
            return detail ?? "Serverfehler. Bitte später erneut versuchen."
        case .decoding:
            return "Antwort vom Backend konnte nicht gelesen werden."
        case let .unknown(detail):
            return detail ?? "Unbekannter Fehler."
        }
    }

    static func fromStatusCode(_ statusCode: Int, detail: String?) -> APIError {
        switch statusCode {
        case 400, 422:
            return .validation(detail: detail)
        case 401:
            return .unauthorized(detail: detail)
        case 403:
            return .forbidden(detail: detail)
        case 404:
            return .notFound(detail: detail)
        case 409:
            return .conflict(detail: detail)
        case 500...599:
            return .server(statusCode: statusCode, detail: detail)
        default:
            return .unknown(detail: detail)
        }
    }

    static func map(_ error: Error) -> APIError {
        if let api = error as? APIError {
            return api
        }
        if error is DecodingError {
            return .decoding
        }
        if error is URLError {
            return .network
        }
        return .unknown(detail: nil)
    }
}

struct APIErrorPayload: Decodable {
    let detail: String?
}
