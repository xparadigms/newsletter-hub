import SwiftUI

// Story mode, built the way Instagram Stories behaves:
//
// · each issue is one "account": its cards sit on a rounded card in the
//   section's colours, under a row of segment bars that fill as a timer runs;
// · tap the right side for the next card, the left for the previous one —
//   cards cut, they do not slide;
// · press and hold to pause, and the chrome steps aside while you read;
// · swipe sideways, or run off either end, to turn to the neighbouring issue
//   on a cube;
// · swipe down to put the story away, swipe up to open the full article.
//
// Listen turns a card into a "video": the timer stops, the card's sentences
// are read aloud, and the story moves on — still reading — when they end.

@MainActor
struct StoryView: View {
    let post: Post
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(SettingsKey.langs) private var langs = LangMode.jaKo.rawValue
    @AppStorage(SettingsKey.furigana) private var furigana = true

    @State private var deck: Deck?
    @State private var index = 0
    @State private var failed = false
    /// Direction of the last turn between issues, for the cube.
    @State private var forward = true

    @State private var clock = StoryClock()
    @State private var holding = false
    @State private var pressStart: Date?
    @State private var dragAxis: Axis?
    @State private var dragY: CGFloat = 0
    @State private var atTop = true

    @State private var audio = AudioReader()
    /// Listen was pressed and stays on across cards until stopped.
    @State private var listening = false

    private var mode: LangMode { LangMode(rawValue: langs) ?? .jaKo }
    private var section: NewsSection { Sections.get(deck?.post.section ?? post.section) }
    private var cards: [StoryCard] { deck?.cards ?? [] }

    var body: some View {
        GeometryReader { geo in
            let insets = geo.safeAreaInsets
            VStack(spacing: 0) {
                ZStack {
                    if let deck {
                        cardFace(deck, size: geo.size)
                            .id(deck.post.routeID)
                            .transition(.cube(forward: forward, width: geo.size.width))
                    } else {
                        loadingFace
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.top, insets.top)

                bottomBar
                    .padding(.bottom, max(insets.bottom, 12))
                    .opacity(holding ? 0 : 1)
            }
            .background(Color.black)
            .clipShape(RoundedRectangle(cornerRadius: dragY > 0 ? 44 : 0, style: .continuous))
            .scaleEffect(1 - min(0.1, dragY / 3000))
            .offset(y: dragY)
        }
        .ignoresSafeArea()
        .environment(\.colorScheme, .dark)
        .presentationBackground(.clear)
        .statusBarHidden()
        .task { await open(post) }
        .task(id: TimerKey(card: cards.isEmpty ? nil : index, issue: deck?.post.routeID, paused: isPaused)) {
            await runTimer()
        }
        .onChange(of: index) { cardChanged() }
        .onChange(of: isPaused) { _, paused in paused ? clock.pause() : clock.resume() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active { clock.pause() } else if !isPaused { clock.resume() }
        }
        .onAppear { audio.onFinish = { if listening { go(1) } } }
        .onDisappear { audio.stop() }
    }

    // MARK: Faces

    private func cardFace(_ deck: Deck, size: CGSize) -> some View {
        let card = deck.cards.indices.contains(index) ? deck.cards[index] : deck.cards[0]
        return ZStack(alignment: .top) {
            SectionBackground(section: Sections.get(deck.post.section))

            StoryCardView(card: card, issue: deck.issue, section: Sections.get(deck.post.section), mode: mode) {
                atTop = $0
            }
            .environment(\.storyCard, true)
            .padding(.top, 76)

            header(deck)
                .opacity(holding ? 0 : 1)
                .animation(.easeOut(duration: 0.18), value: holding)
        }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .contentShape(Rectangle())
        .simultaneousGesture(press(size: size))
    }

    private var loadingFace: some View {
        ZStack {
            SectionBackground(section: section)
            if failed {
                VStack(spacing: 14) {
                    Text("Couldn't load this issue").foregroundStyle(.white.opacity(0.85))
                    Button("Try Again") { Task { await open(post) } }.buttonStyle(.bordered)
                }
            } else {
                ProgressView().tint(.white)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(alignment: .topTrailing) { closeButton.padding(12) }
    }

    // MARK: Chrome

    private func header(_ deck: Deck) -> some View {
        VStack(spacing: 10) {
            HStack(spacing: 4) {
                ForEach(deck.cards.indices, id: \.self) { i in
                    SegmentBar(state: i < index ? .done : i == index ? .active : .todo, clock: clock)
                }
            }
            HStack(spacing: 10) {
                let s = Sections.get(deck.post.section)
                Image(systemName: s.symbol)
                    .font(.system(size: 14, weight: .semibold))
                    .frame(width: 32, height: 32)
                    .background(Circle().fill(.white.opacity(0.18)))
                    .overlay(Circle().strokeBorder(.white.opacity(0.9), lineWidth: 1.5))
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        Text(s.title).font(.system(size: 14, weight: .semibold))
                        Text(Format.shortDate(deck.post.date)).font(.system(size: 13)).foregroundStyle(.white.opacity(0.65))
                    }
                    Text(deck.post.title)
                        .font(.system(size: 12))
                        .foregroundStyle(.white.opacity(0.75))
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                if deck.issue.multi {
                    Menu {
                        Picker("Languages", selection: $langs) {
                            ForEach(LangMode.allCases) { Text($0.label(source: s.sourceLabel)).tag($0.rawValue) }
                        }
                    } label: {
                        Image(systemName: "character.bubble")
                            .font(.system(size: 18))
                            .frame(width: 36, height: 36)
                    }
                }
                closeButton
            }
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 10)
        .padding(.top, 8)
        .background(alignment: .top) {
            LinearGradient(colors: [.black.opacity(0.35), .clear], startPoint: .top, endPoint: .bottom)
                .frame(height: 110)
                .allowsHitTesting(false)
        }
    }

    private var closeButton: some View {
        Button { dismiss() } label: {
            Image(systemName: "xmark")
                .font(.system(size: 20, weight: .medium))
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .foregroundStyle(.white)
        .accessibilityLabel("Close story")
    }

    /// Instagram's reply row, holding this app's reading controls instead.
    private var bottomBar: some View {
        let urls = cardAudio
        let hasRuby = deck?.issue.hasRuby == true
        return HStack(spacing: 10) {
            if hasRuby {
                pill(furigana ? "ふりがな" : "ふりがな off", systemImage: nil, on: furigana) { furigana.toggle() }
            }
            if !urls.isEmpty && mode != .en {
                pill(listening ? "Stop" : "Listen", systemImage: listening ? "stop.fill" : "speaker.wave.2.fill",
                     on: listening) { toggleListening(urls) }
            }
            Spacer(minLength: 0)
            Button { openArticle() } label: {
                Image(systemName: "doc.plaintext").font(.system(size: 21))
                    .frame(width: 40, height: 40)
            }
            .accessibilityLabel("Open the article")
            if let deck {
                ShareLink(item: URL(string: "https://heechang-newsletter.vercel.app/post/\(deck.post.section.rawValue)/\(deck.post.id)")!) {
                    Image(systemName: "paperplane").font(.system(size: 21))
                        .frame(width: 40, height: 40)
                }
            }
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .frame(height: 58, alignment: .top)
    }

    private func pill(_ title: String, systemImage: String?, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let systemImage { Image(systemName: systemImage).font(.system(size: 13)) }
                Text(title).font(.system(size: 14, weight: .medium))
            }
            .padding(.horizontal, 16)
            .frame(height: 40)
            .background(Capsule().fill(on ? .white.opacity(0.16) : .clear))
            .overlay(Capsule().strokeBorder(.white.opacity(0.45), lineWidth: 1))
        }
    }

    // MARK: Gestures

    private var isPaused: Bool { holding || listening || audio.playing }

    /// One gesture for the whole card, as in Instagram: a quick tap moves by a
    /// card, holding pauses, a sideways swipe turns the issue, a pull down
    /// closes and a push up opens the article. Simultaneous, so the card's text
    /// still scrolls when it runs long.
    private func press(size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                if pressStart == nil {
                    pressStart = Date()
                    // Holding is only "holding" once it outlasts a tap.
                    Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 220_000_000)
                        if pressStart != nil && dragAxis == nil { holding = true }
                    }
                }
                let dx = value.translation.width, dy = value.translation.height
                if dragAxis == nil && hypot(dx, dy) > 12 {
                    dragAxis = abs(dx) > abs(dy) ? .horizontal : .vertical
                }
                if dragAxis == .vertical && atTop { dragY = max(0, dy) }
            }
            .onEnded { value in
                let held = Date().timeIntervalSince(pressStart ?? Date())
                let dx = value.translation.width, dy = value.translation.height
                let axis = dragAxis
                pressStart = nil
                dragAxis = nil
                holding = false

                switch axis {
                case .horizontal:
                    if abs(dx) > 50 || abs(value.predictedEndTranslation.width) > 200 { turnIssue(dx < 0 ? 1 : -1) }
                case .vertical:
                    if dragY > 130 || (dragY > 40 && value.predictedEndTranslation.height > 400) {
                        dismiss()
                    } else if dy < -80 && value.startLocation.y > size.height * 0.7 {
                        // Swipe up from the bottom of the card, as for a story's link.
                        openArticle()
                    } else {
                        withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) { dragY = 0 }
                    }
                case nil:
                    // A tap, not a hold: move by a card. The header's own buttons
                    // sit above the first 76 points and must not also page.
                    if held < 0.22 && value.startLocation.y > 76 {
                        go(value.location.x < size.width * 0.3 ? -1 : 1)
                    }
                }
            }
    }

    // MARK: Moving

    private func go(_ step: Int) {
        guard let deck else { return }
        let next = index + step
        if deck.cards.indices.contains(next) {
            setIndex(next)
            return
        }
        turnIssue(step)
    }

    /// The neighbouring issue in the same section, turned to on the cube. Past
    /// the newest one, the story closes.
    private func turnIssue(_ step: Int) {
        guard let deck else { return }
        let adj = store.adjacent(to: deck.post)
        guard let target = step > 0 ? adj.next : adj.prev else {
            if step > 0 { dismiss() } else { setIndex(0) }
            return
        }
        forward = step > 0
        Task { await open(target, animated: true) }
    }

    private func open(_ target: Post, animated: Bool = false) async {
        failed = false
        let section = Sections.get(target.section)
        func show(_ detail: PostDetail) {
            let next = Deck(detail: detail, section: section)
            if animated {
                withAnimation(.easeInOut(duration: 0.42)) { deck = next; index = 0 }
            } else {
                deck = next
                index = 0
            }
            clock.restart(duration: duration(for: 0))
            if isPaused { clock.pause() }
        }
        if let cached = store.cachedDetail(target) {
            show(cached)
            // Refresh quietly; only rebuild if this is still the issue on screen.
            if let fresh = try? await store.detail(target), deck?.post.routeID == target.routeID,
               fresh.blocks != cached.blocks {
                deck = Deck(detail: fresh, section: section)
                if index >= cards.count { index = 0 }
            }
        } else {
            do {
                if let fresh = try await store.detail(target) { show(fresh) } else if deck == nil { failed = true }
            } catch {
                if deck == nil { failed = true }
            }
        }
        #if DEBUG
        // `simctl launch … -storyIndex N` starts on card N, for screenshots.
        let start = UserDefaults.standard.integer(forKey: "storyIndex")
        if !animated, start > 0, start < cards.count { setIndex(start) }
        #endif
        prefetchNeighbours()
    }

    /// The next and previous issues load in the background, so turning to
    /// them is instant — the cube has something to show.
    private func prefetchNeighbours() {
        guard let deck else { return }
        let adj = store.adjacent(to: deck.post)
        for p in [adj.next, adj.prev].compactMap({ $0 }) where store.cachedDetail(p) == nil {
            Task { _ = try? await store.detail(p) }
        }
    }

    /// The clock restarts here, before the index moves, so the timer task the
    /// new index starts never reads the finished card's clock.
    private func setIndex(_ i: Int) {
        clock.restart(duration: duration(for: i))
        if isPaused { clock.pause() }
        index = i
    }

    private func cardChanged() {
        atTop = true
        if listening {
            let urls = cardAudio
            if urls.isEmpty { audio.stop() } else { audio.play(urls) }
        }
    }

    private func toggleListening(_ urls: [String]) {
        if listening {
            listening = false
            audio.stop()
        } else {
            listening = true
            audio.play(urls)
        }
    }

    private func openArticle() {
        guard let deck else { return }
        let target = deck.post
        dismiss()
        router.push(.post(target))
    }

    // MARK: Timer

    private func runTimer() async {
        guard deck != nil, !isPaused else { return }
        let remaining = clock.remaining
        try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
        guard !Task.isCancelled else { return }
        go(1)
    }

    private struct TimerKey: Equatable {
        let card: Int?
        let issue: String?
        let paused: Bool
    }

    /// Long enough to read the card at a learner's pace: Instagram's five
    /// seconds for a picture, more for every line of text.
    private func duration(for i: Int) -> Double {
        guard cards.indices.contains(i) else { return 5 }
        switch cards[i] {
        case .cover: return 6
        case .section: return 3.5
        case let .content(c):
            var units = 0.0
            for b in c.blocks where mode.shows(b.lang, multi: deck?.issue.multi ?? true) {
                for s in Annotate.blockText(b.block).unicodeScalars {
                    units += s.value >= 0x2E80 ? 1 : 0.3
                }
            }
            return min(60, max(6, 3 + units / 9))
        }
    }

    private var cardAudio: [String] {
        guard cards.indices.contains(index), let c = cards[index].content else { return [] }
        return c.blocks.filter { mode.shows($0.lang, multi: true) }.compactMap { Annotate.blockAudio($0.block) }
    }
}

/// An issue made into a deck.
struct Deck {
    let post: Post
    let issue: PreparedIssue
    let cards: [StoryCard]

    init(detail: PostDetail, section: NewsSection) {
        post = detail.post
        issue = PreparedIssue(detail, section: section)
        cards = StoryDeck.build(issue.annotated, post: detail.post, section: section, minutes: issue.minutes)
    }
}

/// The running time of the card on screen. The segment bar redraws from it
/// every frame without the rest of the story re-rendering.
@MainActor
@Observable
final class StoryClock {
    private(set) var duration: Double = 6
    private(set) var paused = false
    /// Bumped on every restart, so the bars know to start from empty.
    private(set) var generation = 0
    @ObservationIgnored private var startedAt = Date()
    @ObservationIgnored private var banked: Double = 0

    func restart(duration: Double) {
        self.duration = duration
        banked = 0
        startedAt = Date()
        paused = false
        generation += 1
    }

    func pause() {
        guard !paused else { return }
        banked += Date().timeIntervalSince(startedAt)
        paused = true
    }

    func resume() {
        guard paused else { return }
        startedAt = Date()
        paused = false
    }

    func fraction(at now: Date) -> Double {
        let elapsed = paused ? banked : banked + now.timeIntervalSince(startedAt)
        return min(1, max(0, elapsed / duration))
    }

    var remaining: Double { max(0, duration * (1 - fraction(at: Date()))) }
}

private struct SegmentBar: View {
    enum Phase { case done, active, todo }
    let state: Phase
    let clock: StoryClock

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.35))
                switch state {
                case .done: Capsule().fill(.white)
                case .todo: EmptyView()
                case .active:
                    TimelineView(.animation(paused: clock.paused)) { ctx in
                        Capsule().fill(.white)
                            .frame(width: geo.size.width * clock.fraction(at: ctx.date))
                    }
                    .id(clock.generation)
                }
            }
        }
        .frame(height: 2.5)
    }
}

/// The section's colours, darkened toward the bottom where the text ends.
private struct SectionBackground: View {
    let section: NewsSection

    var body: some View {
        let (a, b) = section.storyColors
        ZStack {
            LinearGradient(colors: [a, b], startPoint: .topLeading, endPoint: .bottomTrailing)
            LinearGradient(colors: [.clear, .black.opacity(0.35)], startPoint: .center, endPoint: .bottom)
        }
    }
}

extension NewsSection {
    /// Deep enough that white text and its readings stay comfortable to read.
    var storyColors: (Color, Color) {
        func c(_ r: Double, _ g: Double, _ b: Double) -> Color { Color(red: r, green: g, blue: b) }
        switch key {
        case .startup: return (c(0.85, 0.33, 0.20), c(0.45, 0.08, 0.30))
        case .business: return (c(0.20, 0.32, 0.86), c(0.30, 0.10, 0.52))
        case .fintech: return (c(0.05, 0.52, 0.45), c(0.03, 0.20, 0.32))
        case .japan: return (c(0.78, 0.16, 0.30), c(0.30, 0.05, 0.20))
        case .watch: return (c(0.52, 0.42, 0.26), c(0.16, 0.13, 0.09))
        case .china: return (c(0.78, 0.13, 0.12), c(0.34, 0.03, 0.08))
        case .mandarin: return (c(0.86, 0.45, 0.10), c(0.50, 0.12, 0.10))
        case .stocks: return (c(0.08, 0.48, 0.32), c(0.03, 0.14, 0.20))
        }
    }
}

extension AnyTransition {
    /// Instagram's turn between accounts: the outgoing card folds away on one
    /// face of a cube as the incoming one folds in on the next.
    static func cube(forward: Bool, width: CGFloat) -> AnyTransition {
        .asymmetric(
            insertion: .modifier(active: CubeFace(angle: forward ? 90 : -90, anchor: forward ? .leading : .trailing,
                                                  x: forward ? width : -width),
                                 identity: CubeFace(angle: 0, anchor: forward ? .leading : .trailing, x: 0)),
            removal: .modifier(active: CubeFace(angle: forward ? -90 : 90, anchor: forward ? .trailing : .leading,
                                                x: forward ? -width : width),
                               identity: CubeFace(angle: 0, anchor: forward ? .trailing : .leading, x: 0)))
    }
}

private struct CubeFace: ViewModifier {
    let angle: Double
    let anchor: UnitPoint
    let x: CGFloat

    func body(content: Content) -> some View {
        content
            .rotation3DEffect(.degrees(angle), axis: (0, 1, 0), anchor: anchor, perspective: 0.6)
            .offset(x: x)
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
                Eyebrow("\(c.sectionNumber) / \(c.sectionLabel)", color: .white.opacity(0.8))
                Text(c.title)
                    .font(.system(size: 38, weight: .heavy))
                    .tracking(-1)
                    .foregroundStyle(.white)
                    .padding(.top, 14)
                    .minimumScaleFactor(0.7)
                if let summary = c.summary, !summary.isEmpty {
                    Text(summary)
                        .font(.system(size: 17))
                        .foregroundStyle(.white.opacity(0.88))
                        .lineLimit(6)
                        .padding(.top, 18)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Eyebrow([c.series, c.date, "\(c.minutes) min read"].compactMap { $0 }.joined(separator: " · "),
                            color: .white.opacity(0.7))
                    Eyebrow("\(c.count) cards · tap to begin", color: .white.opacity(0.7))
                }
                .padding(.top, 26)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
            .padding(.horizontal, 22)
            .padding(.bottom, 32)
        case let .section(s):
            VStack(spacing: 16) {
                Eyebrow("Section \(s.index) of \(s.total)", color: .white.opacity(0.8))
                headingText(s.heading)
                    .font(.system(size: 32, weight: .heavy))
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 28)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        case let .content(c):
            let visible = c.blocks.filter { mode.shows($0.lang, multi: issue?.multi ?? true) }
            GeometryReader { geo in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if let kicker = c.kicker { Eyebrow(kicker, color: .white.opacity(0.75)) }
                        if let heading = c.heading {
                            headingText(heading)
                                .font(.system(size: 25, weight: .bold))
                                .foregroundStyle(.white)
                                .padding(.top, c.kicker == nil ? 0 : 10)
                        }
                        if let subtitle = c.subtitle, mode != .en {
                            Text(subtitle)
                                .font(.system(size: 16))
                                .foregroundStyle(.white.opacity(0.72))
                                .padding(.top, 8)
                        }
                        ForEach(Array(visible.enumerated()), id: \.offset) { _, item in
                            AnnotatedBlockView(item: item, section: section, compact: true)
                        }
                    }
                    .padding(.horizontal, 22)
                    .padding(.vertical, 20)
                    // Short cards sit in the middle of the card, as a text
                    // story does; long ones start at the top and scroll.
                    .frame(maxWidth: .infinity, minHeight: geo.size.height, alignment: .center)
                    .background(GeometryReader { g in
                        Color.clear.preference(key: CardTopKey.self, value: g.frame(in: .named("card")).minY)
                    })
                }
                .coordinateSpace(name: "card")
                .scrollBounceBehavior(.basedOnSize)
                .scrollIndicators(.hidden)
                .onPreferenceChange(CardTopKey.self) { onTopChange($0 >= -1) }
            }
        }
    }
}

private struct CardTopKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}
