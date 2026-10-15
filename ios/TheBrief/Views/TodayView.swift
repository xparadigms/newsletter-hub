import SwiftUI

/// Home, laid out like Instagram's: a tray of section "stories" across the
/// top, then a feed with one post per issue — header, a typographic picture,
/// actions and a caption. Double-tap the picture to save the issue.
@MainActor
struct TodayView: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router

    var body: some View {
        let feed = store.latest(40)
        ScrollView {
            LazyVStack(spacing: 0) {
                StoryTray()
                Divider().opacity(0.6)
                if let error = store.error {
                    ErrorBanner(message: error).padding(.horizontal, 16).padding(.vertical, 10)
                }
                if feed.isEmpty && store.isLoading {
                    ProgressView().padding(.top, 60)
                }
                ForEach(feed) { post in
                    FeedPost(post: post)
                }
            }
        }
        .scrollIndicators(.hidden)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Text("The Brief")
                    .font(.system(size: 26, weight: .black, design: .serif))
                    .tracking(-0.6)
                    .fixedSize()
            }
            ToolbarItem(placement: .topBarTrailing) { SettingsMenu() }
        }
        .refreshable { await store.refresh() }
    }
}

/// A section's round avatar. The ring is Instagram's gradient while the
/// section's newest issue is unread, and a thin grey line once it has been.
struct SectionAvatar: View {
    let section: NewsSection
    var size: CGFloat = 64
    var unseen = false

    static let ring = AngularGradient(
        colors: [Color(red: 1, green: 0.78, blue: 0.2), Color(red: 0.98, green: 0.35, blue: 0.2),
                 Color(red: 0.86, green: 0.15, blue: 0.5), Color(red: 0.55, green: 0.2, blue: 0.85),
                 Color(red: 1, green: 0.78, blue: 0.2)],
        center: .center, startAngle: .degrees(90), endAngle: .degrees(450))

    var body: some View {
        ZStack {
            Circle()
                .fill(Color(white: 0.09))
                .overlay(Circle().fill(section.storyTint.opacity(0.35)))
            Image(systemName: section.symbol)
                .font(.system(size: size * 0.36, weight: .semibold))
                .foregroundStyle(.white)
        }
        .frame(width: size, height: size)
        .padding(size * 0.06)
        .overlay {
            if unseen {
                Circle().strokeBorder(Self.ring, lineWidth: size * 0.05)
            } else {
                Circle().strokeBorder(Color.secondary.opacity(0.35), lineWidth: 1)
            }
        }
    }
}

@MainActor
private struct StoryTray: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router

    var body: some View {
        // One story per section: its newest issue. Unread sections come first,
        // as Instagram puts unseen accounts first.
        let entries: [(NewsSection, Post)] = Sections.nav.compactMap { s in
            store.posts(in: s.key).first.map { (s, $0) }
        }
        let ordered = entries.filter { store.hasUnseen($0.0.key) } + entries.filter { !store.hasUnseen($0.0.key) }
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 14) {
                ForEach(ordered, id: \.1.routeID) { entry in
                    let (section, post) = entry
                    Button {
                        router.playStories(from: post, queue: ordered.map(\.1))
                    } label: {
                        VStack(spacing: 6) {
                            SectionAvatar(section: section, size: 64, unseen: store.hasUnseen(section.key))
                            Text(section.label)
                                .font(.system(size: 12))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                        }
                        .frame(width: 76)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
        }
        .scrollIndicators(.hidden)
    }
}

@MainActor
private struct FeedPost: View {
    let post: Post
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.storyMode) private var storyMode = false
    @State private var expanded = false
    @State private var burst = false

    private var section: NewsSection { Sections.get(post.section) }
    private var shareURL: URL {
        URL(string: "https://heechang-newsletter.vercel.app/post/\(post.section.rawValue)/\(post.id)")!
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            picture
            actions
            caption
        }
        .padding(.bottom, 18)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Button { router.playStories(from: post, queue: []) } label: {
                SectionAvatar(section: section, size: 30, unseen: !store.seen.contains(post.routeID))
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 0) {
                Text(section.title).font(.system(size: 14, weight: .semibold))
                if let series = post.series, !series.isEmpty {
                    Text(series).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            Menu {
                Button { router.push(.post(post)) } label: { Label("Read Article", systemImage: "doc.plaintext") }
                Button { router.playStories(from: post, queue: []) } label: {
                    Label("Play Story", systemImage: "play.rectangle")
                }
                Button { router.push(.section(post.section)) } label: { Label("Go to \(section.title)", systemImage: section.symbol) }
                ShareLink(item: shareURL) { Label("Share", systemImage: "square.and.arrow.up") }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 16, weight: .semibold))
                    .frame(width: 36, height: 36)
                    .contentShape(Rectangle())
            }
            .foregroundStyle(.primary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    /// Text in place of a photo, as a text post on Instagram is: the issue's
    /// headline set large on the story card's dark ground.
    private var picture: some View {
        ZStack(alignment: .bottomLeading) {
            SectionBackground(section: section)
            VStack(alignment: .leading, spacing: 14) {
                Eyebrow("\(section.number) / \(section.label)", color: .white.opacity(0.7))
                Text(post.title)
                    .font(.system(size: 30, weight: .heavy))
                    .tracking(-0.6)
                    .foregroundStyle(.white)
                    .minimumScaleFactor(0.6)
                    .lineLimit(7)
                Eyebrow(Format.longDate(post.date) ?? "", color: .white.opacity(0.55))
            }
            .padding(22)
            Image(systemName: "bookmark.fill")
                .font(.system(size: 84))
                .foregroundStyle(.white)
                .shadow(radius: 12)
                .scaleEffect(burst ? 1 : 0.3)
                .opacity(burst ? 1 : 0)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .aspectRatio(4 / 5, contentMode: .fit)
        .contentShape(Rectangle())
        .onTapGesture(count: 2) { saveWithBurst() }
        .onTapGesture { open() }
    }

    private var actions: some View {
        let saved = store.isSaved(post)
        return HStack(spacing: 18) {
            Button { router.push(.post(post)) } label: { Image(systemName: "doc.plaintext") }
                .accessibilityLabel("Read article")
            Button { router.playStories(from: post, queue: []) } label: { Image(systemName: "play.rectangle") }
                .accessibilityLabel("Play story")
            ShareLink(item: shareURL) { Image(systemName: "paperplane") }
            Spacer()
            Button {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.5)) { store.toggleSaved(post) }
            } label: {
                Image(systemName: saved ? "bookmark.fill" : "bookmark")
                    .contentTransition(.symbolEffect(.replace))
            }
            .accessibilityLabel(saved ? "Unsave" : "Save")
        }
        .font(.system(size: 22))
        .foregroundStyle(.primary)
        .buttonStyle(.plain)
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 8)
    }

    @ViewBuilder private var caption: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let summary = post.summary, !summary.isEmpty {
                (Text(section.label).fontWeight(.semibold) + Text("  ") + Text(summary))
                    .font(.system(size: 14))
                    .lineLimit(expanded ? nil : 2)
                    .onTapGesture { withAnimation(.easeOut(duration: 0.2)) { expanded.toggle() } }
            }
            Text(Format.shortDate(post.date).uppercased())
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14)
    }

    private func open() {
        if storyMode { router.playStories(from: post, queue: []) } else { router.push(.post(post)) }
    }

    private func saveWithBurst() {
        if !store.isSaved(post) { store.toggleSaved(post) }
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        withAnimation(.spring(response: 0.3, dampingFraction: 0.55)) { burst = true }
        Task {
            try? await Task.sleep(nanoseconds: 700_000_000)
            withAnimation(.easeOut(duration: 0.25)) { burst = false }
        }
    }
}
