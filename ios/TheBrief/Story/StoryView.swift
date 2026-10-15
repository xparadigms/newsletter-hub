import SwiftUI

/// An issue as a deck of full-screen cards (web/components/story/StoryViewer).
/// Tap the right two-thirds or swipe left for the next card, the left third or
/// swipe right for the previous one, and drag down to put the story away.
@MainActor
struct StoryView: View {
    let post: Post
    @Environment(Store.self) private var store
    @Environment(\.dismiss) private var dismiss
    @AppStorage(SettingsKey.langs) private var langs = LangMode.jaKo.rawValue
    @AppStorage(SettingsKey.furigana) private var furigana = true

    @State private var current: Post
    @State private var issue: PreparedIssue?
    @State private var cards: [StoryCard] = []
    @State private var index = 0
    @State private var forward = true
    @State private var dragY: CGFloat = 0
    /// Decided once per drag: a sideways drag pages, a downward one dismisses.
    @State private var dragAxis: Axis?
    /// Whether the card's text is scrolled to its top. Dragging down is also
    /// how you scroll back up, so the story only follows the finger from there.
    @State private var atTop = true
    @State private var failed = false
    @State private var audio = AudioReader()

    init(post: Post) {
        self.post = post
        _current = State(initialValue: post)
    }

    private var section: NewsSection { Sections.get(current.section) }
    private var mode: LangMode { LangMode(rawValue: langs) ?? .jaKo }

    var body: some View {
        // Laid out edge to edge and padded by hand, so the dark card — not the
        // safe area — is what gets rounded and moved while dragging down.
        GeometryReader { geo in
            VStack(spacing: 0) {
                progress
                topBar
                stage
                controls
                Text(cards.isEmpty ? " " : "\(index + 1) / \(cards.count)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.38))
                    .padding(.vertical, 8)
            }
            .padding(.top, geo.safeAreaInsets.top)
            .padding(.bottom, geo.safeAreaInsets.bottom)
            .frame(width: geo.size.width, height: geo.size.height)
            .background(Color(red: 0.043, green: 0.043, blue: 0.047))
            .clipShape(RoundedRectangle(cornerRadius: dragY > 0 ? 44 : 0, style: .continuous))
            .scaleEffect(1 - min(0.08, dragY / 4000))
            .offset(y: dragY)
        }
        .ignoresSafeArea()
        .environment(\.colorScheme, .dark)
        // What shows around the card as it is dragged down is the app beneath.
        .presentationBackground(.clear)
        .simultaneousGesture(drag)
        .statusBarHidden()
        .task(id: current) { await load() }
        .onChange(of: index) { audio.stop() }
        .onDisappear { audio.stop() }
    }

    // MARK: Chrome

    private var progress: some View {
        HStack(spacing: 3) {
            ForEach(cards.indices, id: \.self) { i in
                Capsule()
                    .fill(.white.opacity(i <= index ? 1 : 0.26))
                    .frame(height: 2.5)
            }
        }
        .padding(.horizontal, 10)
        .padding(.top, 10)
        .animation(.smooth(duration: 0.3), value: index)
    }

    private var topBar: some View {
        HStack(spacing: 12) {
            Text(current.title.uppercased())
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.white.opacity(0.82))
                .lineLimit(1)
            Spacer(minLength: 0)
            if issue?.multi == true {
                Menu {
                    Picker("Languages", selection: $langs) {
                        ForEach(LangMode.allCases) { Text($0.label(source: section.sourceLabel)).tag($0.rawValue) }
                    }
                } label: {
                    Image(systemName: "character.bubble")
                        .frame(width: 34, height: 34)
                        .background(.ultraThinMaterial, in: Circle())
                }
            }
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .semibold))
                    .frame(width: 34, height: 34)
                    .background(.ultraThinMaterial, in: Circle())
            }
            .accessibilityLabel("Close story")
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 16)
        .padding(.top, 12)
    }

    @ViewBuilder private var controls: some View {
        let urls = cardAudio
        let hasRuby = issue?.hasRuby == true
        if hasRuby || (!urls.isEmpty && mode != .en) {
            HStack(spacing: 4) {
                if hasRuby {
                    chip("ふりがな", on: furigana) { furigana.toggle() }
                }
                if !urls.isEmpty && mode != .en {
                    chip(audio.playing ? "Stop" : "Listen", systemImage: audio.playing ? "stop.fill" : "speaker.wave.2",
                         on: audio.playing) {
                        audio.playing ? audio.stop() : audio.play(urls)
                    }
                }
            }
            .padding(5)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(.top, 6)
        }
    }

    private func chip(_ title: String, systemImage: String? = nil, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let systemImage { Image(systemName: systemImage) }
                Text(title)
            }
            .font(.system(size: 12, weight: .medium, design: .monospaced))
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(on ? Color(white: 0.17) : .clear, in: Capsule())
        }
        .foregroundStyle(.white)
    }

    // MARK: Cards

    private var stage: some View {
        GeometryReader { geo in
            ZStack {
                if cards.indices.contains(index) {
                    StoryCardView(card: cards[index], issue: issue, section: section, mode: mode) { atTop = $0 }
                        .id(index)
                        .transition(.asymmetric(
                            insertion: .offset(x: forward ? 32 : -32).combined(with: .opacity),
                            removal: .opacity))
                } else if failed {
                    VStack(spacing: 14) {
                        Text("Couldn't load this issue").foregroundStyle(.white.opacity(0.8))
                        Button("Try Again") { Task { await load() } }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ProgressView().tint(.white).frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .contentShape(Rectangle())
            .onTapGesture(coordinateSpace: .local) { point in
                if point.x < geo.size.width * 0.32 { go(-1) } else { go(1) }
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 4)
    }

    /// One gesture for both directions, so neither can swallow the other.
    /// Sideways pages through the cards; downward follows the finger and puts
    /// the story away past a threshold or on a flick, the way a full-screen
    /// sheet behaves.
    private var drag: some Gesture {
        DragGesture(minimumDistance: 12)
            .onChanged { value in
                let dx = value.translation.width, dy = value.translation.height
                if dragAxis == nil { dragAxis = abs(dx) > abs(dy) ? .horizontal : .vertical }
                if dragAxis == .vertical && atTop { dragY = max(0, dy) }
            }
            .onEnded { value in
                let dx = value.translation.width
                defer { dragAxis = nil }
                if dragAxis == .horizontal {
                    if abs(dx) > 48 || abs(value.predictedEndTranslation.width) > 160 { go(dx < 0 ? 1 : -1) }
                    return
                }
                if dragY > 140 || (dragY > 40 && value.predictedEndTranslation.height > 400) {
                    dismiss()
                } else if dragY > 0 {
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) { dragY = 0 }
                }
            }
    }

    private var cardAudio: [String] {
        guard let c = cards.indices.contains(index) ? cards[index].content : nil else { return [] }
        return c.blocks.filter { mode.shows($0.lang, multi: true) }.compactMap { Annotate.blockAudio($0.block) }
    }

    private func go(_ step: Int) {
        let next = index + step
        if cards.indices.contains(next) {
            forward = step > 0
            atTop = true
            withAnimation(.spring(response: 0.42, dampingFraction: 0.9)) { index = next }
            UIImpactFeedbackGenerator(style: .soft).impactOccurred(intensity: 0.5)
            return
        }
        // Past either end, roll on to the neighbouring issue like a story feed;
        // past the newest, close.
        let adj = store.adjacent(to: current)
        if step > 0 {
            if let newer = adj.next { current = newer } else { dismiss() }
        } else if let older = adj.prev {
            current = older
        }
    }

    private func load() async {
        failed = false
        let cached = store.cachedDetail(current)
        if let cached { prepare(cached) }
        do {
            if let fresh = try await store.detail(current) { prepare(fresh) }
            else if cached == nil { failed = true }
        } catch {
            if cached == nil { failed = true }
        }
    }

    private func prepare(_ detail: PostDetail) {
        let prepared = PreparedIssue(detail, section: section)
        let built = StoryDeck.build(prepared.annotated, post: detail.post, section: section, minutes: prepared.minutes)
        if issue?.detail.post.id != detail.post.id { index = 0; forward = true; atTop = true }
        issue = prepared
        cards = built
        if index >= cards.count { index = 0 }
    }
}

@MainActor
private struct StoryCardView: View {
    let card: StoryCard
    let issue: PreparedIssue?
    let section: NewsSection
    let mode: LangMode
    var onTopChange: (Bool) -> Void = { _ in }

    var body: some View {
        switch card {
        case let .cover(c):
            VStack(alignment: .leading, spacing: 0) {
                Spacer()
                Eyebrow("\(c.sectionNumber) / \(c.sectionLabel)", color: .brandAccent)
                Text(c.title)
                    .font(.system(size: 34, weight: .bold))
                    .tracking(-0.8)
                    .foregroundStyle(.white)
                    .padding(.top, 14)
                if let summary = c.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.body)
                        .foregroundStyle(.white.opacity(0.82))
                        .lineLimit(5)
                        .padding(.top, 16)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Eyebrow([c.series, c.date, "\(c.minutes) min read"].compactMap { $0 }.joined(separator: " · "),
                            color: .white.opacity(0.58))
                    Eyebrow("\(c.count) cards · tap to begin", color: .white.opacity(0.58))
                }
                .padding(.top, 26)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
            .padding(.bottom, 8)
        case let .section(s):
            VStack(spacing: 14) {
                Eyebrow("Section \(s.index) of \(s.total)", color: .brandAccent)
                headingText(s.heading)
                    .font(.system(size: 26, weight: .bold))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case let .content(c):
            let visible = c.blocks.filter { mode.shows($0.lang, multi: issue?.multi ?? true) }
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if let kicker = c.kicker { Eyebrow(kicker, color: .brandAccent) }
                    if let heading = c.heading {
                        headingText(heading)
                            .font(.system(size: 22, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.top, 10)
                    }
                    if let subtitle = c.subtitle, mode != .en {
                        Text(subtitle)
                            .font(.system(size: 15))
                            .foregroundStyle(.white.opacity(0.62))
                            .padding(.top, 6)
                    }
                    ForEach(Array(visible.enumerated()), id: \.offset) { _, item in
                        AnnotatedBlockView(item: item, section: section, compact: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 16)
                .background(GeometryReader { g in
                    Color.clear.preference(key: CardTopKey.self, value: g.frame(in: .named("card")).minY)
                })
            }
            .coordinateSpace(name: "card")
            .scrollBounceBehavior(.basedOnSize)
            .onPreferenceChange(CardTopKey.self) { onTopChange($0 >= -1) }
        }
    }
}

private struct CardTopKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}
