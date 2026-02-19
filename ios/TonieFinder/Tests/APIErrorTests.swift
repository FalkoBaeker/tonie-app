import XCTest
@testable import TonieFinder

final class APIErrorTests: XCTestCase {
    func testMapStatusCodeUnauthorized() {
        let mapped = APIError.fromStatusCode(401, detail: "unauthorized")
        XCTAssertEqual(mapped, .unauthorized(detail: "unauthorized"))
        XCTAssertEqual(mapped.userMessage, "unauthorized")
    }

    func testMapStatusCodeConflict() {
        let mapped = APIError.fromStatusCode(409, detail: "refresh already running")
        XCTAssertEqual(mapped, .conflict(detail: "refresh already running"))
        XCTAssertEqual(mapped.userMessage, "refresh already running")
    }

    func testMapURLErrorToNetwork() {
        let mapped = APIError.map(URLError(.notConnectedToInternet))
        XCTAssertEqual(mapped, .network)
    }

    func testMapDecodingError() {
        struct Dummy: Decodable { let value: Int }
        let data = Data("{}".utf8)

        do {
            _ = try JSONDecoder().decode(Dummy.self, from: data)
            XCTFail("Expected decoding to fail")
        } catch {
            let mapped = APIError.map(error)
            XCTAssertEqual(mapped, .decoding)
        }
    }

    func testDebugLoggingToggleParsing() {
        XCTAssertTrue(AppConfig.debugLoggingEnabled(from: "1", plistValue: nil))
        XCTAssertTrue(AppConfig.debugLoggingEnabled(from: "true", plistValue: nil))
        XCTAssertTrue(AppConfig.debugLoggingEnabled(from: nil, plistValue: true))
        XCTAssertFalse(AppConfig.debugLoggingEnabled(from: nil, plistValue: nil))
        XCTAssertFalse(AppConfig.debugLoggingEnabled(from: "0", plistValue: nil))
    }

    func testDiagnosticsReporter_sanitizesSensitiveFields() {
        var lines: [String] = []
        let reporter = DiagnosticsReporter(
            isEnabled: { true },
            logger: { lines.append($0) }
        )

        reporter.reportAPIError(
            flow: "auth",
            endpointPath: "/auth/login",
            statusCode: 401,
            errorType: "unauthorized",
            message: "Authorization: Bearer abc.def token=secret password=hunter2 user=test@example.com",
            context: [
                "Authorization": "Bearer hidden",
                "token": "123",
                "email": "test@example.com",
                "safe": "ok"
            ]
        )

        XCTAssertEqual(lines.count, 1)
        let line = lines[0]
        XCTAssertFalse(line.lowercased().contains("bearer hidden"))
        XCTAssertFalse(line.lowercased().contains("hunter2"))
        XCTAssertFalse(line.lowercased().contains("test@example.com"))
        XCTAssertTrue(line.contains("safe=ok"))
    }

    func testDiagnosticsReporter_apiErrorEventContainsPathStatusAndFlow() {
        var lines: [String] = []
        let reporter = DiagnosticsReporter(
            isEnabled: { true },
            logger: { lines.append($0) }
        )

        reporter.reportAPIError(
            flow: "alerts",
            endpointPath: "/watchlist/alerts?unread_only=true",
            statusCode: 500,
            errorType: "server",
            message: "backend failed",
            context: ["action": "load_alerts_unread"]
        )

        XCTAssertEqual(lines.count, 1)
        let line = lines[0]
        XCTAssertTrue(line.contains("flow=alerts"))
        XCTAssertTrue(line.contains("path=/watchlist/alerts?unread_only=true"))
        XCTAssertTrue(line.contains("status=500"))
        XCTAssertTrue(line.contains("action=load_alerts_unread"))
    }

    func testDiagnosticsReporter_respectsEnabledToggle() {
        var lines: [String] = []
        let disabledReporter = DiagnosticsReporter(
            isEnabled: { false },
            logger: { lines.append($0) }
        )

        disabledReporter.reportNonFatal(
            flow: "pricing",
            errorType: "photo_processing_failed",
            message: "failed"
        )

        XCTAssertTrue(lines.isEmpty)

        let enabledReporter = DiagnosticsReporter(
            isEnabled: { true },
            logger: { lines.append($0) }
        )

        enabledReporter.reportNonFatal(
            flow: "pricing",
            errorType: "photo_processing_failed",
            message: "failed"
        )

        XCTAssertEqual(lines.count, 1)
    }
}
