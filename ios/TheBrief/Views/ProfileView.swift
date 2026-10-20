import SwiftUI

/// The reader's own page, laid out like an Instagram profile: who, a row of
/// counts, then a grid — the issues saved, or the ones read.
@MainActor
struct ProfileView: View {
    @Environment(Store.self) private var store
    @State private var showing: Shelf = .saved

    enum Shelf: String, CaseIterable, Identifiable {
        case saved, read
        var id: String { rawValue }
        var symbol: String { self == .saved ? "bookmark" : "clock" }
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
                if posts.isEmpty {
                    empty.padding(.top, 50)
                } else {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 3), spacing: 2) {
                        ForEach(posts) { PostTile(post: $0, savedShelf: showing == .saved) }
                    }
                }
            }
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
                        Image(systemName: showing == shelf ? shelf.symbol + ".fill" : shelf.symbol)
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
                .accessibilityLabel(shelf == .saved ? "Saved" : "Read")
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
