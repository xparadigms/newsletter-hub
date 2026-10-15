import SwiftUI

/// An issue prepared for reading: annotated once, then filtered per setting.
struct PreparedIssue {
    let detail: PostDetail
    let annotated: [AnnotatedBlock]
    let multi: Bool
    let hasRuby: Bool
    let toc: [TocItem]
    let minutes: Int

    init(_ detail: PostDetail, section: NewsSection) {
        self.detail = detail
        annotated = Annotate.annotate(detail.blocks, hanLang: section.sourceLang)
        multi = annotated.contains { $0.lang == .ja || $0.lang == .ko || $0.lang == .zh }
        hasRuby = annotated.contains { $0.ruby?.contains { $0.reading != nil } == true }
        toc = Annotate.toc(annotated)
        minutes = Annotate.readingTime(annotated)
    }
}

@MainActor
struct ArticleView: View {
    let post: Post
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.langs) private var langs = LangMode.jaKo.rawValue
    @AppStorage(SettingsKey.furigana) private var furigana = true
    @State private var issue: PreparedIssue?
    @State private var failed = false

    private var section: NewsSection { Sections.get(post.section) }
    private var mode: LangMode { LangMode(rawValue: langs) ?? .jaKo }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    header
                    if let issue {
                        let visible = issue.annotated.enumerated().filter { mode.shows($0.element.lang, multi: issue.multi) }
                        if visible.isEmpty {
                            Text("This entry has no content yet.").foregroundStyle(.secondary).padding(.top, 20)
                        }
                        ForEach(visible, id: \.offset) { _, item in
                            AnnotatedBlockView(item: item, section: section)
                        }
                        adjacent.padding(.top, 48)
                    } else if failed {
                        ContentUnavailableView {
                            Label("Couldn't load this issue", systemImage: "wifi.exclamationmark")
                        } actions: {
                            Button("Try Again") { Task { await load() } }
                        }
                        .padding(.top, 40)
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            }
            .toolbar { toolbar(proxy) }
        }
        .navigationTitle(section.label)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            store.markSeen(post)
            await load()
        }
    }

    private var header: some View {
        // The fetched copy when there is one: a post opened from a link
        // arrives with nothing but its slug.
        let post = issue?.detail.post ?? self.post
        return VStack(alignment: .leading, spacing: 12) {
            Eyebrow([post.series, Format.longDate(post.date), issue.map { "\($0.minutes) min read" }]
                .compactMap { $0 }.joined(separator: " · "))
            Text(post.title)
                .font(.system(size: 30, weight: .bold))
                .tracking(-0.4)
                .textSelection(.enabled)
            if let summary = post.summary, !summary.isEmpty {
                Text(summary).font(.callout).foregroundStyle(.secondary)
            }
            Divider().padding(.top, 8)
        }
        .padding(.top, 8)
    }

    @ViewBuilder private var adjacent: some View {
        let adj = store.adjacent(to: post)
        let prev = adj.prev, next = adj.next
        if prev != nil || next != nil {
            VStack(alignment: .leading, spacing: 0) {
                Divider()
                if let prev {
                    PostLink(post: prev) { adjacentRow("← Previous · \(Format.shortDate(prev.date))", prev.title) }
                }
                if prev != nil && next != nil { Divider() }
                if let next {
                    PostLink(post: next) { adjacentRow("Next · \(Format.shortDate(next.date)) →", next.title) }
                }
            }
        }
    }

    private func adjacentRow(_ label: String, _ title: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(label)
            Text(title).font(.body.weight(.medium)).foregroundStyle(.primary).multilineTextAlignment(.leading)
        }
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ToolbarContentBuilder
    private func toolbar(_ proxy: ScrollViewProxy) -> some ToolbarContent {
        ToolbarItemGroup(placement: .topBarTrailing) {
            if let issue {
                if issue.toc.count > 1 {
                    Menu {
                        ForEach(issue.toc) { item in
                            Button(item.level >= 3 ? "   " + item.text : item.text) {
                                withAnimation(.smooth) { proxy.scrollTo(item.id, anchor: .top) }
                            }
                        }
                    } label: { Image(systemName: "list.bullet") }
                    .accessibilityLabel("Contents")
                }
                if issue.multi {
                    Menu {
                        Picker("Languages", selection: $langs) {
                            ForEach(LangMode.allCases) { Text($0.label(source: section.sourceLabel)).tag($0.rawValue) }
                        }
                        if issue.hasRuby {
                            Toggle("Furigana", isOn: $furigana)
                        }
                    } label: { Image(systemName: "character.bubble") }
                    .accessibilityLabel("Reading language")
                }
            }
            Button { router.story = post } label: { Image(systemName: "rectangle.portrait.on.rectangle.portrait") }
                .accessibilityLabel("Story mode")
            SaveButton(post: post)
            ShareLink(item: URL(string: "https://heechang-newsletter.vercel.app/post/\(post.section.rawValue)/\(post.id)")!)
        }
    }

    private func load() async {
        failed = false
        if issue == nil, let cached = store.cachedDetail(post) {
            issue = PreparedIssue(cached, section: section)
        }
        do {
            if let fresh = try await store.detail(post) {
                issue = PreparedIssue(fresh, section: section)
            } else if issue == nil {
                failed = true
            }
        } catch {
            if issue == nil { failed = true }
        }
    }
}
