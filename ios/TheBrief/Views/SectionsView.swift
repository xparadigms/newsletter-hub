import SwiftUI

@MainActor
struct SectionsView: View {
    @Environment(Store.self) private var store

    var body: some View {
        List {
            if !store.saved.isEmpty {
                Section("Saved") {
                    ForEach(store.saved) { PostRow(post: $0, showSection: true) }
                }
            }
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
struct SectionView: View {
    let section: NewsSection
    @Environment(Store.self) private var store

    var body: some View {
        let groups = monthGroups(store.posts(in: section.key))
        List {
            Section {
                Text(section.description)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 0, leading: 4, bottom: 0, trailing: 4))
                GenerateControls(section: section)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 8, leading: 4, bottom: 8, trailing: 4))
            }
            if groups.isEmpty {
                Section {
                    if store.isLoading { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Nothing published here yet.").foregroundStyle(.secondary) }
                }
            }
            ForEach(groups) { group in
                Section(group.month) {
                    ForEach(group.posts) { PostRow(post: $0) }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(section.title)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
        .refreshable { await store.refresh() }
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
