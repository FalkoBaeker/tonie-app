import XCTest
import Darwin
@testable import TonieFinder

@MainActor
final class AuthViewModelTests: XCTestCase {
    private final class InMemoryTokenStore: AuthTokenStore {
        var token: String?

        func save(token: String) {
            self.token = token
        }

        func loadToken() -> String? {
            token
        }

        func clearToken() {
            token = nil
        }
    }

    private struct MockAuthAPI: AuthAPI {
        var loginHandler: (String, String) async throws -> ClientAuthSession
        var registerHandler: (String, String) async throws -> ClientAuthSession
        var externalLoginHandler: (String, String) async throws -> ClientAuthSession
        var externalRegisterHandler: (String, String) async throws -> ExternalRegisterResult
        var meHandler: (String) async throws -> ClientUser

        func login(email: String, password: String) async throws -> ClientAuthSession {
            try await loginHandler(email, password)
        }

        func register(email: String, password: String) async throws -> ClientAuthSession {
            try await registerHandler(email, password)
        }

        func externalLogin(email: String, password: String) async throws -> ClientAuthSession {
            try await externalLoginHandler(email, password)
        }

        func externalRegister(email: String, password: String) async throws -> ExternalRegisterResult {
            try await externalRegisterHandler(email, password)
        }

        func me(token: String) async throws -> ClientUser {
            try await meHandler(token)
        }

        func logout(token: String) async throws {}
    }

    override func tearDown() {
        unsetenv("TF_AUTH_MODE")
        unsetenv("TF_SUPABASE_URL")
        unsetenv("TF_SUPABASE_ANON_KEY")
        unsetenv("TF_API_BASE_URL")
        super.tearDown()
    }

    func testLocalModeSubmitAuth_usesLocalLoginAndSavesToken() async {
        setenv("TF_AUTH_MODE", "local", 1)
        let store = InMemoryTokenStore()

        let api = MockAuthAPI(
            loginHandler: { _, _ in
                ClientAuthSession(token: "local_token", userId: 1, userEmail: "local@example.com", expiresAt: "")
            },
            registerHandler: { _, _ in
                ClientAuthSession(token: "reg", userId: 1, userEmail: "local@example.com", expiresAt: "")
            },
            externalLoginHandler: { _, _ in
                XCTFail("external login should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            externalRegisterHandler: { _, _ in
                XCTFail("external register should not be called")
                return ExternalRegisterResult(session: nil, requiresEmailVerification: false)
            },
            meHandler: { _ in ClientUser(id: 1, email: "local@example.com") }
        )

        let vm = AuthViewModel(api: api, tokenStore: store)
        vm.email = "local@example.com"
        vm.password = "secret123"
        vm.mode = .login
        vm.submitAuth()

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertTrue(vm.isLoggedIn)
        XCTAssertEqual(vm.authToken, "local_token")
        XCTAssertEqual(store.token, "local_token")
    }

    func testExternalModeMissingConfig_showsConfigErrorBeforeNetworkCall() async {
        setenv("TF_AUTH_MODE", "external", 1)
        unsetenv("TF_SUPABASE_URL")
        unsetenv("TF_SUPABASE_ANON_KEY")

        let store = InMemoryTokenStore()
        let api = MockAuthAPI(
            loginHandler: { _, _ in
                XCTFail("local login should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            registerHandler: { _, _ in
                XCTFail("local register should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            externalLoginHandler: { _, _ in
                XCTFail("external login should not be called when config is invalid")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            externalRegisterHandler: { _, _ in
                XCTFail("external register should not be called when config is invalid")
                return ExternalRegisterResult(session: nil, requiresEmailVerification: false)
            },
            meHandler: { _ in
                XCTFail("me should not be called")
                return ClientUser(id: 1, email: "x@example.com")
            }
        )

        let vm = AuthViewModel(api: api, tokenStore: store)
        vm.email = "ext@example.com"
        vm.password = "secret123"
        vm.mode = .login
        vm.submitAuth()

        XCTAssertFalse(vm.isLoggedIn)
        XCTAssertEqual(vm.statusText, "External Auth aktiv, aber TF_SUPABASE_URL fehlt.")
    }

    func testExternalRegisterRequiresVerification_showsHintAndDoesNotLogin() async {
        setenv("TF_AUTH_MODE", "external", 1)
        setenv("TF_SUPABASE_URL", "https://example.supabase.co", 1)
        setenv("TF_SUPABASE_ANON_KEY", "dummy", 1)
        let store = InMemoryTokenStore()

        let api = MockAuthAPI(
            loginHandler: { _, _ in
                XCTFail("local login should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            registerHandler: { _, _ in
                XCTFail("local register should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            externalLoginHandler: { _, _ in
                throw APIError.unauthorized(detail: "invalid credentials")
            },
            externalRegisterHandler: { _, _ in
                ExternalRegisterResult(session: nil, requiresEmailVerification: true)
            },
            meHandler: { _ in
                XCTFail("me should not be called")
                return ClientUser(id: 1, email: "x@example.com")
            }
        )

        let vm = AuthViewModel(api: api, tokenStore: store)
        vm.email = "ext@example.com"
        vm.password = "secret123"
        vm.mode = .register
        vm.submitAuth()

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertFalse(vm.isLoggedIn)
        XCTAssertEqual(vm.statusText, "Bitte E-Mail bestätigen und danach einloggen.")
        XCTAssertNil(store.token)
    }

    func testExternalRegisterWithoutSessionButLoginWorks_showsAccountExistsHint() async {
        setenv("TF_AUTH_MODE", "external", 1)
        setenv("TF_SUPABASE_URL", "https://example.supabase.co", 1)
        setenv("TF_SUPABASE_ANON_KEY", "dummy", 1)
        let store = InMemoryTokenStore()

        let api = MockAuthAPI(
            loginHandler: { _, _ in
                XCTFail("local login should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            registerHandler: { _, _ in
                XCTFail("local register should not be called")
                return ClientAuthSession(token: "", userId: 0, userEmail: "", expiresAt: "")
            },
            externalLoginHandler: { _, _ in
                ClientAuthSession(token: "external", userId: 0, userEmail: "x@example.com", expiresAt: "")
            },
            externalRegisterHandler: { _, _ in
                ExternalRegisterResult(session: nil, requiresEmailVerification: false)
            },
            meHandler: { _ in
                XCTFail("me should not be called")
                return ClientUser(id: 1, email: "x@example.com")
            }
        )

        let vm = AuthViewModel(api: api, tokenStore: store)
        vm.email = "ext@example.com"
        vm.password = "secret123"
        vm.mode = .register
        vm.submitAuth()

        try? await Task.sleep(nanoseconds: 200_000_000)

        XCTAssertEqual(vm.statusText, "Konto scheint bereits zu existieren. Bitte einloggen.")
        XCTAssertFalse(vm.isLoggedIn)
    }
}
