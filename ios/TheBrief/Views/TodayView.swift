import SwiftUI

/// The front page: the newest issue as the lead, the next few beneath it, and
/// each section's latest issues.
struct TodayView: View {
    @Environment(Store.self) private var store

    var body: some View {
        let latest = store.latest(20)
        let lead = latest.first
        let rest = Array(latest.dropFirst())

        List {
            Section {
                VStack(alignment: .leading, spacing: 2) {
                    Eyebrow(Format.today())
                    Eyebrow("Daily newsletters by Heechang")
                }
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets(top: 0, leading: 4, bottom: 4, trailing: 4))
                if let error = store.error {
                    ErrorBanner(message: error).listRowBackground(Color.clear)
                }
            }

            if let lead {
                Section {
                    LeadCard(post: lead)
                    ForEach(rest.prefix(3)) { PostRow(post: $0, showSection: true) }
                }
                if rest.count > 3 {
                    Section("Latest") {
                        ForEach(rest.dropFirst(3).prefix(6)) { PostRow(post: $0, showSection: true) }
                    }
                }
            } else if store.isLoading {
                Section { ProgressView().frame(maxWidth: .infinity) }
                    .listRowBackground(Color.clear)
            }

            ForEach(Sections.nav) { section in
                let posts = store.posts(in: section.key)
                if !posts.isEmpty {
                    Section {
                        ForEach(posts.prefix(4)) { PostRow(post: $0) }
                        NavigationLink(value: Route.section(section.key)) {
                            Text("View all").foregroundStyle(Color.brandAccent)
                        }
                    } header: {
                        HStack(spacing: 6) {
                            Image(systemName: section.symbol)
                            Text("\(section.number) · \(section.title)")
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("The Brief")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await store.refresh() }
    }
}

private struct LeadCard: View {
    let post: Post

    var body: some View {
        let section = Sections.get(post.section)
        PostLink(post: post) {
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("\(section.number) / \(section.label)", color: .brandAccent)
                Text(post.title)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.leading)
                if let summary = post.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(5)
                }
                if let date = Format.longDate(post.date) { Eyebrow(date) }
            }
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
