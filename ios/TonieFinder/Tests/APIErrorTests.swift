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
}
