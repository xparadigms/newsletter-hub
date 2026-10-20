import SwiftUI

@MainActor
struct SectionsView: View {
    @Environment(Store.self) private var store

    var body: some View {
        List {
            Section {
                ForEach(Sections.nav) { row($0) }
            }
            Section("Paused") {
                ForEach(Sections.paused) { row($0) }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Sections")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await store.refresh() }
    }

    private func row(_ section: NewsSection) -> some View {
        NavigationLink(value: Route.section(section.key)) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: section.symbol)
                    .font(.title3)
                    .foregroundStyle(Color.brandAccent)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 4) {
                    Text(section.title).font(.headline)
                    Text(section.description)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                    if let newest = store.posts(in: section.key).first {
                        Eyebrow("Latest · \(Format.shortDate(newest.date))")
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }
}

@MainActor
/// A section's page, laid out like an Instagram profile: its avatar (ringed
/// while there is something unread — tap it to play the newest issue as a
/// story), a row of counts, its description as the bio, then every issue it
/// has published as a grid, or as a list by month.
struct SectionView: View {
    let section: NewsSection
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @State private var layout: Layout = .grid

    enum Layout: CaseIterable { case grid, list }

    var body: some View {
        let posts = store.posts(in: section.key)
        ScrollView {
            VStack(spacing: 0) {
                header(posts)
                tabs
                if posts.isEmpty {
                    Group {
                        if store.isLoading { ProgressView() } else {
                            Text("Nothing published here yet.").foregroundStyle(.secondary)
                        }
                    }
                    .padding(.top, 48)
                } else if layout == .grid {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 3), spacing: 2) {
                        ForEach(posts) { PostTile(post: $0) }
                    }
                } else {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(monthGroups(posts)) { group in
                            Text(group.month.uppercased())
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 16)
                                .padding(.top, 18)
                                .padding(.bottom, 4)
                            ForEach(group.posts) { post in
                                PostRow(post: post)
                                    .padding(.horizontal, 16)
                                Divider().padding(.leading, 16)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(section.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await store.refresh() }
    }

    private func header(_ posts: [Post]) -> some View {
        let newest = posts.first
        let read = posts.filter { store.seen.contains($0.routeID) }.count
        let saved = store.saved.filter { $0.section == section.key }.count
        return VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 22) {
                Button {
                    if let newest { router.playStories(from: newest, queue: []) }
                } label: {
                    SectionAvatar(section: section, size: 84, unseen: store.hasUnseen(section.key))
                }
                .buttonStyle(.plain)
                .disabled(newest == nil)
                .accessibilityLabel("Play the newest issue as a story")

                HStack(spacing: 0) {
                    stat(posts.count, "posts")
                    stat(read, "read")
                    stat(saved, "saved")
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(section.title).font(.system(size: 15, weight: .semibold))
                Text(section.description)
                    .font(.system(size: 14))
                    .foregroundStyle(.primary.opacity(0.85))
                    .fixedSize(horizontal: false, vertical: true)
                if let newest {
                    Text("Latest · \(Format.longDate(newest.date) ?? "")")
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 8) {
                Button {
                    if let newest { router.playStories(from: newest, queue: []) }
                } label: {
                    Label("Play Story", systemImage: "play.fill")
                        .font(.system(size: 14, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .frame(height: 34)
                }
                .buttonStyle(.borderedProminent)
                .disabled(newest == nil)
                ShareLink(item: URL(string: "https://heechang-newsletter.vercel.app/section/\(section.key.rawValue)")!) {
                    Text("Share")
                        .font(.system(size: 14, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .frame(height: 34)
                }
                .buttonStyle(.bordered)
            }
            .buttonBorderShape(.roundedRectangle(radius: 9))

            GenerateControls(section: section)
                .padding(.top, 2)
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 14)
    }

    private func stat(_ n: Int, _ label: String) -> some View {
        VStack(spacing: 2) {
            Text("\(n)").font(.system(size: 17, weight: .semibold))
            Text(label).font(.system(size: 13)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    /// Instagram's icon tabs over the grid: every issue as squares, or as a
    /// list grouped by month.
    private var tabs: some View {
        HStack(spacing: 0) {
            ForEach(Layout.allCases, id: \.self) { option in
                Button {
                    withAnimation(.easeOut(duration: 0.15)) { layout = option }
                } label: {
                    VStack(spacing: 10) {
                        Image(systemName: option == .grid ? "square.grid.3x3" : "list.bullet")
                            .font(.system(size: 19, weight: layout == option ? .semibold : .regular))
                            .foregroundStyle(layout == option ? Color.primary : Color.secondary)
                        Rectangle()
                            .fill(layout == option ? Color.primary : .clear)
                            .frame(height: 1)
                    }
                    .padding(.top, 8)
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(option == .grid ? "Grid" : "List")
            }
        }
        .overlay(alignment: .bottom) { Divider() }
    }

    private struct MonthGroup: Identifiable {
        let month: String
        var posts: [Post]
        var id: String { month }
    }

    private func monthGroups(_ posts: [Post]) -> [MonthGroup] {
        var out: [MonthGroup] = []
        for post in posts {
            let month = Format.month(post.date)
            if out.last?.month == month { out[out.count - 1].posts.append(post) }
            else { out.append(MonthGroup(month: month, posts: [post])) }
        }
        return out
    }
}

@MainActor
struct SearchView: View {
    @Environment(Store.self) private var store
    @State private var query = ""

    var body: some View {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let results: [Post] = q.isEmpty ? [] : Array(store.latest(Int.max).filter { post in
            post.title.lowercased().contains(q)
                || (post.series ?? "").lowercased().contains(q)
                || Sections.get(post.section).label.lowercased().contains(q)
        }.prefix(50))

        List {
            if q.isEmpty {
                Section("Sections") {
                    ForEach(Sections.nav) { section in
                        NavigationLink(value: Route.section(section.key)) {
                            Label(section.title, systemImage: section.symbol)
                        }
                    }
                }
            } else if results.isEmpty {
                ContentUnavailableView.search(text: query)
            } else {
                ForEach(results) { PostRow(post: $0, showSection: true) }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("Search")
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always),
                    prompt: "Search every issue")
    }
}
