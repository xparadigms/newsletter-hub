import SwiftUI
import SafariServices

/// The Feed tab: the latest from every newsletter's sources, collected each
/// hour (shared/news_feed.py) — the news itself, before it becomes an issue.
/// Each item opens on its publisher's site, inside the app.
@MainActor
struct FeedView: View {
    @AppStorage(SettingsKey.mode) private var modeRaw = AppMode.japan.rawValue
    @State private var filter: SectionKey?
    @State private var items: [NewsItem] = []
    @State private var loading = false
    @State private var failed = false
    @State private var opened: URL?

    private var mode: AppMode { AppMode(rawValue: modeRaw) ?? .japan }
    /// The mode's newsletters that have a news feed.
    private var feedSections: [SectionKey] { mode.feedSections }

    var body: some View {
        List {
            Section {
                if items.isEmpty {
                    Group {
                        if loading { ProgressView() }
                        else if failed { Text("Couldn't load the feed.").foregroundStyle(.secondary) }
                        else { Text("Nothing collected yet — the feed fills every hour.").foregroundStyle(.secondary) }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
                    .listRowSeparator(.hidden)
                }
                ForEach(items) { item in
                    Button { opened = URL(string: item.url) } label: { NewsRow(item: item) }
                        .buttonStyle(.plain)
                        .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
                }
            }
        }
        .listStyle(.plain)
        .safeAreaInset(edge: .bottom) {
            FilterBar(sections: feedSections, selection: $filter)
        }
        .navigationTitle("\(mode.flag) Feed")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await load() }
        .task(id: "\(modeRaw)/\(filter?.rawValue ?? "all")") { await load() }
        .onChange(of: modeRaw) { filter = nil }
        .sheet(item: $opened) { SafariView(url: $0).ignoresSafeArea() }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            items = try await SupabaseClient.shared.feed(sections: filter.map { [$0] } ?? feedSections)
            failed = false
        } catch {
            failed = items.isEmpty
        }
    }
}

private struct NewsRow: View {
    let item: NewsItem

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    SectionAvatar(section: Sections.get(item.section), size: 16, unseen: false)
                    Text(item.source ?? Sections.get(item.section).label)
                    if let date = item.published {
                        Text("·")
                        Text(date, format: .relative(presentation: .numeric, unitsStyle: .abbreviated))
                    }
                }
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                Text(item.title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                if let summary = item.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let image = item.image_url, let url = URL(string: image) {
                AsyncImage(url: url) { phase in
                    if case let .success(img) = phase { img.resizable().scaledToFill() }
                    else { Color.primary.opacity(0.06) }
                }
                .frame(width: 84, height: 84)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .contentShape(Rectangle())
    }
}

/// Safari, inside the app, for a publisher's page.
struct SafariView: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> SFSafariViewController { SFSafariViewController(url: url) }
    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}

extension URL: @retroactive Identifiable {
    public var id: String { absoluteString }
}
