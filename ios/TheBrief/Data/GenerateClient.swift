import Foundation
import Security

/// "Generate a new issue" and "Write about a company", through the website's
/// own /api/generate — the generators are GitHub Actions jobs, and the site is
/// the gate in front of them, with its password and its daily cap.
///
/// The password is asked for once and kept in the Keychain. Signing in sets
/// the site's cookie in the shared cookie store, which every later request
/// carries; when it is missing or stale, the saved password signs in again.
enum GenerateClient {
    static let site = URL(string: "https://heechang-newsletter.vercel.app")!

    enum Failure: LocalizedError {
        case needsPassword
        case wrongPassword
        case server(String)

        var errorDescription: String? {
            switch self {
            case .needsPassword: return "Enter the site password."
            case .wrongPassword: return "Wrong password."
            case let .server(message): return message
            }
        }
    }

    struct Reply: Decodable {
        let ok: Bool?
        let error: String?
        let message: String?
        let remaining: Int?
    }

    static var hasPassword: Bool { Keychain.read() != nil }

    /// Checks the password against the site and saves it if it works.
    static func signIn(_ password: String) async throws {
        var request = URLRequest(url: site.appendingPathComponent("api/auth"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["password": password])
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        // 501: the deployment has no password at all, so there is no gate.
        guard status == 200 || status == 501 else {
            if status == 401 { throw Failure.wrongPassword }
            throw Failure.server((try? JSONDecoder().decode(Reply.self, from: data))?.error ?? "Sign-in failed (\(status)).")
        }
        Keychain.save(password)
    }

    /// Starts a run; returns the site's message, e.g. "Generating… 7 left today."
    static func generate(section: SectionKey, company: String? = nil) async throws -> String {
        do {
            return try await dispatch(section: section, company: company)
        } catch Failure.needsPassword {
            guard let password = Keychain.read() else { throw Failure.needsPassword }
            do {
                try await signIn(password)
            } catch Failure.wrongPassword {
                // The site's password changed; ask again.
                Keychain.delete()
                throw Failure.needsPassword
            }
            return try await dispatch(section: section, company: company)
        }
    }

    private static func dispatch(section: SectionKey, company: String?) async throws -> String {
        var request = URLRequest(url: site.appendingPathComponent("api/generate"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body = ["section": section.rawValue]
        if let company { body["company"] = company }
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let reply = try? JSONDecoder().decode(Reply.self, from: data)
        if status == 401 { throw Failure.needsPassword }
        guard status == 200 else { throw Failure.server(reply?.error ?? "Failed (\(status)).") }
        let message = reply?.message ?? "Started."
        if let remaining = reply?.remaining { return "\(message) \(remaining) left today." }
        return message
    }
}

/// The site password, in the Keychain rather than UserDefaults.
enum Keychain {
    private static let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "com.heechangkang.thebrief",
        kSecAttrAccount as String: "site-password",
    ]

    static func save(_ value: String) {
        delete()
        var item = query
        item[kSecValueData as String] = Data(value.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(item as CFDictionary, nil)
    }

    static func read() -> String? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func delete() {
        SecItemDelete(query as CFDictionary)
    }
}
