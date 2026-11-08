import SwiftUI

/// Podcast Hub: one article per new episode of the shows the generator
/// follows (podcasts-newsletter/main.py), newest first, in Home's row style,
/// with a show filter floating above the tab bar.
@MainActor
struct PodcastsView: View {
    @Environment(Store.self) private var store
    @State private var show: String?

    var body: some View {
        let episodes = store.posts(in: .podcasts)
        // Shows in the order their latest episodes came out.
        var shows: [String] = []
        for e in episodes { if let s = e.series, !shows.contains(s) { shows.append(s) } }
        let shown = show.map { s in episodes.filter { $0.series == s } } ?? Array(episodes.prefix(80))

        return ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    Color.clear.frame(height: 0).id("top")
                    if let error = store.error {
                        ErrorBanner(message: error).padding(.horizontal, 16).padding(.vertical, 10)
                    }
                    if shown.isEmpty {
                        if store.isLoading {
                            ProgressView().padding(.top, 60)
                        } else {
                            ContentUnavailableView(
                                "No episodes yet", systemImage: "headphones",
                                description: Text("Every new episode of All-In, Masters of Scale, Lenny's Podcast and more becomes an article here."))
                                .padding(.top, 60)
                        }
                    }
                    ForEach(shown) { post in
                        HomeRow(post: post, source: post.series ?? "Podcast")
                        Divider().padding(.leading, 16)
                    }
                }
            }
            .scrollIndicators(.hidden)
            .safeAreaInset(edge: .bottom) {
                ChipBar(options: shows, label: { $0 }, selection: $show)
            }
            .onChange(of: show) { withAnimation { proxy.scrollTo("top", anchor: .top) } }
        }
        .navigationTitle("Podcasts")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await store.refresh() }
    }
}
