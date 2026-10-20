import Foundation

/// Read-only access to the `newsletter` table, the same rows the website reads.
///
/// The key is Supabase's publishable key, which row-level security limits to
/// reading published issues. It is not in the source: the repository is
/// public and the issues sit behind the site's password, so the key is filled
/// in at build time from the SUPABASE_PUBLISHABLE_KEY build setting (a GitHub
/// secret in CI) and read back here from Info.plist.
struct SupabaseClient: Sendable {
    static let shared = SupabaseClient()

    private let base = URL(string: "https://tgepceqzussfzlpshakp.supabase.co/rest/v1/newsletter")!
    private let key = (Bundle.main.object(forInfoDictionaryKey: "SupabasePublishableKey") as? String) ?? ""

    /// Everything a list needs. Never `blocks`: that is ~40KB a row.
    private static let listColumns = "slug,section,title,series,issue_date,summary"

    private struct Row: Decodable {
        let slug: String
        let section: SectionKey
        let title: String
        let series: String?
        let issue_date: String?
        let summary: String?
        let blocks: LossyBlocks?

        var post: Post {
            Post(id: slug, section: section, title: title, series: series, date: issue_date, summary: summary)
        }
    }

    private func get(_ query: [URLQueryItem]) async throws -> [Row] {
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        components.queryItems = query
        var request = URLRequest(url: components.url!)
        request.setValue(key, forHTTPHeaderField: "apikey")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20

        // Supabase's gateway sometimes answers a burst of list queries with a
        // 504 (the site hit this too), so retry before giving up.
        var lastError: Error = URLError(.unknown)
        for attempt in 1...3 {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                    throw URLError(.badServerResponse)
                }
                return try JSONDecoder().decode([Row].self, from: data)
            } catch {
                lastError = error
                if attempt < 3 { try await Task.sleep(nanoseconds: UInt64(400_000_000 * attempt)) }
            }
        }
        throw lastError
    }

    /// When a section's first issue came out, and how many it has published —
    /// for the timeline on The Brief's profile. Lists stop at 500, so neither
    /// can be read off them.
    func history(of section: SectionKey) async throws -> (first: String?, count: Int) {
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "select", value: "issue_date"),
            URLQueryItem(name: "section", value: "eq.\(section.rawValue)"),
            URLQueryItem(name: "order", value: "issue_date.asc,published_at.asc"),
            URLQueryItem(name: "limit", value: "1"),
        ]
        var request = URLRequest(url: components.url!)
        request.setValue(key, forHTTPHeaderField: "apikey")
        // Asks PostgREST for the total too, in Content-Range: "0-0/273".
        request.setValue("count=exact", forHTTPHeaderField: "Prefer")
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        let rows = try JSONDecoder().decode([[String: String?]].self, from: data)
        let range = http.value(forHTTPHeaderField: "Content-Range") ?? ""
        let count = Int(range.split(separator: "/").last ?? "") ?? 0
        return ((rows.first?["issue_date"] ?? nil), count)
    }

    func posts(in section: SectionKey) async throws -> [Post] {
        try await get([
            URLQueryItem(name: "select", value: Self.listColumns),
            URLQueryItem(name: "section", value: "eq.\(section.rawValue)"),
            URLQueryItem(name: "order", value: "issue_date.desc,published_at.desc"),
            URLQueryItem(name: "limit", value: "500"),
        ]).map(\.post)
    }

    func detail(section: SectionKey, slug: String) async throws -> PostDetail? {
        guard let row = try await get([
            URLQueryItem(name: "select", value: "\(Self.listColumns),blocks"),
            URLQueryItem(name: "section", value: "eq.\(section.rawValue)"),
            URLQueryItem(name: "slug", value: "eq.\(slug)"),
            URLQueryItem(name: "limit", value: "1"),
        ]).first else { return nil }
        let blocks = row.blocks?.blocks ?? []
        return PostDetail(post: row.post, blocks: section == .stocks ? numberParts(blocks) : blocks)
    }
}

/// Three Companies' parts, numbered from 0 — "0. 【基本情報】…". The site does
/// this at read time too (web/lib/posts.ts), so both number the same way.
func numberParts(_ blocks: [Block]) -> [Block] {
    var n = 0
    return blocks.map { block in
        guard case let .heading(level, text) = block else { return block }
        let trimmed = String(text.drop { $0.isWhitespace })
        guard trimmed.hasPrefix("【"), !Rx.matches(#"^\d+\.\s"#, text) else { return block }
        defer { n += 1 }
        return .heading(level: level, text: "\(n). \(trimmed)")
    }
}
