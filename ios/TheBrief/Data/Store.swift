import Foundation
import Observation

/// Every list in the app, plus the issues that have been opened. Lists and
/// issues are written to the caches directory as they arrive, so the app opens
/// to the last thing it saw — and opened issues still read — with no network.
@MainActor
@Observable
final class Store {
    private(set) var posts: [SectionKey: [Post]] = [:]
    private(set) var isLoading = false
    private(set) var error: String?
    private var details: [String: PostDetail] = [:]

    private let client = SupabaseClient.shared
    private let cacheDir: URL = {
        let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("issues", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    init() {
        if let data = try? Data(contentsOf: cacheDir.appendingPathComponent("lists.json")),
           let cached = try? JSONDecoder().decode([SectionKey: [Post]].self, from: data) {
            posts = cached
        }
    }

    var hasContent: Bool { posts.values.contains { !$0.isEmpty } }

    func posts(in section: SectionKey) -> [Post] { posts[section] ?? [] }

    /// Newest first across every section (web/lib/feed.ts flattenLatest).
    func latest(_ limit: Int) -> [Post] {
        let all = Sections.feedOrder.flatMap { posts[$0] ?? [] }
        let order = Dictionary(uniqueKeysWithValues: Sections.feedOrder.enumerated().map { ($1, $0) })
        return Array(all.sorted { a, b in
            let ad = a.date ?? "", bd = b.date ?? ""
            if ad != bd { return ad > bd }
            return order[a.section]! < order[b.section]!
        }.prefix(limit))
    }

    /// Lists are sorted newest first, so "next" is the newer neighbour.
    func adjacent(to post: Post) -> (prev: Post?, next: Post?) {
        let list = posts(in: post.section)
        guard let i = list.firstIndex(where: { $0.id == post.id }) else { return (nil, nil) }
        return (i + 1 < list.count ? list[i + 1] : nil, i > 0 ? list[i - 1] : nil)
    }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        let client = self.client
        // A section that fails keeps what it had, rather than going blank.
        let results = await withTaskGroup(of: (SectionKey, [Post]?).self) { group in
            for key in SectionKey.allCases {
                group.addTask { (key, try? await client.posts(in: key)) }
            }
            var out: [(SectionKey, [Post]?)] = []
            for await r in group { out.append(r) }
            return out
        }
        var next = posts
        var failed = 0
        for (key, list) in results {
            if let list { next[key] = list } else { failed += 1 }
        }
        posts = next
        error = failed == results.count ? "Couldn't reach the newsletter. Showing what was saved." : nil
        if failed < results.count, let data = try? JSONEncoder().encode(next) {
            try? data.write(to: cacheDir.appendingPathComponent("lists.json"), options: .atomic)
        }
    }

    private func detailURL(_ post: Post) -> URL {
        cacheDir.appendingPathComponent("\(post.section.rawValue)--\(post.id).json")
    }

    func cachedDetail(_ post: Post) -> PostDetail? {
        if let d = details[post.routeID] { return d }
        guard let data = try? Data(contentsOf: detailURL(post)),
              let d = try? JSONDecoder().decode(PostDetail.self, from: data) else { return nil }
        details[post.routeID] = d
        return d
    }

    /// The issue from cache when there is one; then the network's copy.
    func detail(_ post: Post) async throws -> PostDetail? {
        do {
            guard let d = try await client.detail(section: post.section, slug: post.id) else { return nil }
            details[post.routeID] = d
            if let data = try? JSONEncoder().encode(d) {
                try? data.write(to: detailURL(post), options: .atomic)
            }
            return d
        } catch {
            if let cached = cachedDetail(post) { return cached }
            throw error
        }
    }
}
