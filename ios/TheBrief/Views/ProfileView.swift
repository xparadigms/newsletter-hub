import SwiftUI

/// The reader's own page, laid out like an Instagram profile: who, a row of
/// counts, then a grid of the issues saved or read — or The Brief's timeline,
/// when each newsletter began.
@MainActor
struct ProfileView: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @State private var showing: Shelf = .saved

    enum Shelf: String, CaseIterable, Identifiable {
        case saved, read, timeline
        var id: String { rawValue }
        func symbol(selected: Bool) -> String {
            switch self {
            case .saved: return selected ? "bookmark.fill" : "bookmark"
            case .read: return selected ? "clock.fill" : "clock"
            case .timeline: return selected ? "calendar.badge.clock" : "calendar"
            }
        }
        var label: String {
            switch self {
            case .saved: return "Saved"
            case .read: return "Read"
            case .timeline: return "Timeline"
            }
        }
    }

    /// Everything opened, newest first. Only issues still in the loaded lists
    /// can be shown, which in practice is the whole archive.
    private var readPosts: [Post] {
        store.latest(Int.max).filter { store.seen.contains($0.routeID) }
    }

    var body: some View {
        let posts = showing == .saved ? store.saved : readPosts
        ScrollView {
            VStack(spacing: 0) {
                header
                shelfPicker
                if showing == .timeline {
                    BriefTimeline()
                } else if posts.isEmpty {
                    empty.padding(.top, 50)
                } else {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 3), spacing: 2) {
                        ForEach(posts) { PostTile(post: $0, savedShelf: showing == .saved) }
                    }
                }
            }
        }
        .onAppear {
            if let name = router.requestedShelf, let shelf = Shelf(rawValue: name) { showing = shelf }
            router.requestedShelf = nil
        }
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsMenu() } }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 24) {
                ZStack {
                    Circle().fill(Color(white: 0.06))
                    VStack(spacing: 5) {
                        Text("TB").font(.system(size: 28, weight: .heavy)).foregroundStyle(.white)
                        Capsule().fill(Color.brandAccent).frame(width: 26, height: 3)
                    }
                }
                .frame(width: 86, height: 86)
                .overlay(Circle().strokeBorder(SectionAvatar.ring, lineWidth: 3).padding(-5))
                .padding(5)

                HStack(spacing: 0) {
                    stat(store.saved.count, "saved")
                    stat(readPosts.count, "read")
                    stat(Sections.nav.count, "sections")
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text("Heechang").font(.system(size: 15, weight: .semibold))
                Text("The Brief · daily newsletters on startups, finance, Japan and China")
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }

    private func stat(_ n: Int, _ label: String) -> some View {
        VStack(spacing: 2) {
            Text("\(n)").font(.system(size: 17, weight: .semibold))
            Text(label).font(.system(size: 13)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    /// Instagram's icon tabs above the grid, with the underline on the open one.
    private var shelfPicker: some View {
        HStack(spacing: 0) {
            ForEach(Shelf.allCases) { shelf in
                Button {
                    withAnimation(.easeOut(duration: 0.15)) { showing = shelf }
                } label: {
                    VStack(spacing: 10) {
                        Image(systemName: shelf.symbol(selected: showing == shelf))
                            .font(.system(size: 20))
                            .foregroundStyle(showing == shelf ? Color.primary : Color.secondary)
                        Rectangle()
                            .fill(showing == shelf ? Color.primary : .clear)
                            .frame(height: 1)
                    }
                    .padding(.top, 8)
                    .frame(maxWidth: .infinity)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(shelf.label)
            }
        }
        .overlay(alignment: .bottom) { Divider() }
    }

    private var empty: some View {
        VStack(spacing: 10) {
            Image(systemName: showing == .saved ? "bookmark" : "clock.arrow.circlepath")
                .font(.system(size: 40, weight: .light))
            Text(showing == .saved ? "Nothing saved yet" : "Nothing read yet")
                .font(.system(size: 20, weight: .bold))
            Text(showing == .saved
                 ? "Tap the bookmark on an issue, or double-tap it in Home, to keep it here."
                 : "Issues you open as an article or a story collect here.")
                .font(.system(size: 14))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 40)
    }
}

/// A square in a profile grid — yours or a section's: the issue's headline on
/// its section's card.
@MainActor
struct PostTile: View {
    let post: Post
    var savedShelf = false
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.storyMode) private var storyMode = false

    var body: some View {
        let section = Sections.get(post.section)
        Button {
            if storyMode { router.playStories(from: post, queue: []) } else { router.push(.post(post)) }
        } label: {
            ZStack(alignment: .topLeading) {
                SectionBackground(section: section)
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: section.symbol)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.75))
                    Spacer(minLength: 0)
                    Text(post.title)
                        .font(.system(size: 12.5, weight: .bold))
                        .foregroundStyle(.white)
                        .lineLimit(5)
                        .multilineTextAlignment(.leading)
                    Text(Format.shortDate(post.date))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.55))
                }
                .padding(9)
            }
            .aspectRatio(1, contentMode: .fit)
            .clipped()
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button { router.push(.post(post)) } label: { Label("Read Article", systemImage: "doc.plaintext") }
            Button { router.playStories(from: post, queue: []) } label: { Label("Play Story", systemImage: "play.rectangle") }
            Button(role: savedShelf ? .destructive : nil) {
                withAnimation { store.toggleSaved(post) }
            } label: {
                store.isSaved(post)
                    ? Label("Remove from Saved", systemImage: "bookmark.slash")
                    : Label("Save", systemImage: "bookmark")
            }
        }
    }
}

/// The bookmark used in the article bar, the story bar and the feed.
@MainActor
struct SaveButton: View {
    let post: Post
    @Environment(Store.self) private var store

    var body: some View {
        let saved = store.isSaved(post)
        Button {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.5)) { store.toggleSaved(post) }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            Image(systemName: saved ? "bookmark.fill" : "bookmark")
                .contentTransition(.symbolEffect(.replace))
        }
        .accessibilityLabel(saved ? "Remove from Saved" : "Save")
    }
}

/// When each newsletter began, oldest first, as a vertical timeline: the
/// launch, how many issues since, and for a paused one, when it stopped.
@MainActor
private struct BriefTimeline: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let entries = store.timeline {
                ForEach(Array(entries.enumerated()), id: \.element.id) { i, entry in
                    row(entry, isFirst: i == 0)
                }
                today
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 18)
        .padding(.bottom, 40)
        .task { await store.loadTimeline() }
    }

    private func row(_ entry: Store.SectionHistory, isFirst: Bool) -> some View {
        let s = entry.section
        return Button { router.push(.section(s.key)) } label: {
            HStack(alignment: .top, spacing: 14) {
                // The rail: the date's dot on a line running down the page.
                VStack(spacing: 0) {
                    Rectangle().fill(isFirst ? .clear : Color.secondary.opacity(0.3)).frame(width: 1.5, height: 10)
                    SectionAvatar(section: s, size: 34, unseen: false)
                    Rectangle().fill(Color.secondary.opacity(0.3)).frame(width: 1.5).frame(maxHeight: .infinity)
                }
                .frame(width: 40)

                VStack(alignment: .leading, spacing: 4) {
                    Text((Format.longDate(entry.first) ?? entry.first).uppercased())
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(Color.brandAccent)
                    Text("\(s.title) started")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(.primary)
                    Text(s.description)
                        .font(.system(size: 13))
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .multilineTextAlignment(.leading)
                    HStack(spacing: 6) {
                        Text("\(entry.count) issues")
                        if s.hideInNav, let last = entry.last {
                            Text("·")
                            Text("Paused since \(Format.longDate(last) ?? last)")
                        }
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.secondary)
                }
                .padding(.top, 10)
                .padding(.bottom, 22)
                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var today: some View {
        let total = store.timeline?.reduce(0) { $0 + $1.count } ?? 0
        return HStack(alignment: .top, spacing: 14) {
            VStack(spacing: 0) {
                Rectangle().fill(Color.secondary.opacity(0.3)).frame(width: 1.5, height: 10)
                Circle().fill(Color.brandAccent).frame(width: 12, height: 12).padding(11)
            }
            .frame(width: 40)
            VStack(alignment: .leading, spacing: 4) {
                Text("TODAY")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Color.brandAccent)
                Text("\(total) issues across \(store.timeline?.count ?? 0) newsletters")
                    .font(.system(size: 16, weight: .semibold))
            }
            .padding(.top, 10)
        }
    }
}
