import SwiftUI

/// Home: every issue as a row in the Feed tab's style — source and date,
/// headline, a line of summary, the cover beside it — for the current mode's
/// newsletters, with a row of filters just above the tab bar where the thumb
/// already is. Tap the title to switch between Japan and China.
@MainActor
struct TodayView: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.mode) private var modeRaw = AppMode.japan.rawValue
    @State private var filter: SectionKey?

    private var mode: AppMode { AppMode(rawValue: modeRaw) ?? .japan }

    var body: some View {
        let feed = store.feed(60, sections: filter.map { [$0] } ?? mode.sections)
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    Color.clear.frame(height: 0).id("top")
                    if let error = store.error {
                        ErrorBanner(message: error).padding(.horizontal, 16).padding(.vertical, 10)
                    }
                    if feed.isEmpty && store.isLoading {
                        ProgressView().padding(.top, 60)
                    }
                    ForEach(feed) { post in
                        HomeRow(post: post)
                        Divider().padding(.leading, 16)
                    }
                }
            }
            .scrollIndicators(.hidden)
            .safeAreaInset(edge: .bottom) {
                FilterBar(sections: mode.sections, selection: $filter)
            }
            .onChange(of: filter) { withAnimation { proxy.scrollTo("top", anchor: .top) } }
        }
        .onChange(of: modeRaw) { filter = nil }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                // The mode switch, where Instagram puts its account switcher.
                Menu {
                    Picker("Mode", selection: $modeRaw) {
                        ForEach(AppMode.allCases) { m in
                            Text("\(m.flag) \(m.title) — \(m.sections.map { Sections.get($0).label }.joined(separator: ", "))")
                                .tag(m.rawValue)
                        }
                    }
                } label: {
                    HStack(spacing: 6) {
                        Text("The Brief")
                            .font(.system(size: 26, weight: .black, design: .serif))
                            .tracking(-0.6)
                        Text(mode.flag).font(.system(size: 18))
                        Image(systemName: "chevron.down")
                            .font(.system(size: 12, weight: .bold))
                    }
                    .foregroundStyle(.primary)
                    .fixedSize()
                }
                .accessibilityLabel("The Brief, \(mode.title) mode. Switch mode")
            }
            ToolbarItem(placement: .topBarTrailing) { SettingsMenu() }
        }
        .refreshable { await store.refresh() }
    }
}

/// "All" and one chip per newsletter, in a glass strip that floats just above
/// the tab bar — the same filter on Home and on Feed.
struct FilterBar: View {
    let sections: [SectionKey]
    @Binding var selection: SectionKey?

    var body: some View {
        if sections.count > 1 {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    chip("All", on: selection == nil) { selection = nil }
                    ForEach(sections, id: \.self) { key in
                        chip(Sections.get(key).label, on: selection == key) { selection = key }
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 6)
            }
            .background(.ultraThinMaterial, in: Capsule())
            .overlay(Capsule().strokeBorder(Color.primary.opacity(0.08)))
            .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12)
            .padding(.bottom, 6)
        }
    }

    private func chip(_ title: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button {
            withAnimation(.snappy(duration: 0.2)) { action() }
            UISelectionFeedbackGenerator().selectionChanged()
        } label: {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(on ? Color.primary : Color.primary.opacity(0.06), in: Capsule())
                .foregroundStyle(on ? Color(uiColor: .systemBackground) : Color.primary)
        }
        .buttonStyle(.plain)
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

/// One issue on Home, in the Feed tab's style. Tap to read (or play, with
/// story mode on); long-press for the rest.
@MainActor
private struct HomeRow: View {
    let post: Post
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.storyMode) private var storyMode = false

    private var section: NewsSection { Sections.get(post.section) }

    var body: some View {
        Button {
            if storyMode { router.playStories(from: post, queue: []) } else { router.push(.post(post)) }
        } label: {
            HStack(alignment: .top, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 6) {
                        SectionAvatar(section: section, size: 16, unseen: !store.seen.contains(post.routeID))
                        Text(section.title)
                        Text("·")
                        Text(Format.shortDate(post.date))
                    }
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    Text(post.title)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(3)
                        .multilineTextAlignment(.leading)
                    if let summary = post.summary, !summary.isEmpty {
                        Text(summary)
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                    } else if let series = post.series, !series.isEmpty {
                        Text(series)
                            .font(.system(size: 13))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                // The cover, or the section's card when there is none.
                SectionBackground(section: section, cover: post.cover)
                    .overlay {
                        if post.cover == nil {
                            Image(systemName: section.symbol).font(.system(size: 22)).foregroundStyle(.white.opacity(0.8))
                        }
                    }
                    .frame(width: 84, height: 84)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button { router.push(.post(post)) } label: { Label("Read Article", systemImage: "doc.plaintext") }
            Button { router.playStories(from: post, queue: []) } label: { Label("Play Story", systemImage: "play.rectangle") }
            Button { router.push(.section(post.section)) } label: { Label("Go to \(section.title)", systemImage: section.symbol) }
            Button { withAnimation { store.toggleSaved(post) } } label: {
                store.isSaved(post) ? Label("Remove from Saved", systemImage: "bookmark.slash") : Label("Save", systemImage: "bookmark")
            }
            ShareLink(item: URL(string: "https://heechang-newsletter.vercel.app/post/\(post.section.rawValue)/\(post.id)")!) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
        }
    }
}
