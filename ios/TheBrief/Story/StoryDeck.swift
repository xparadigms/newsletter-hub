import Foundation

// A port of web/lib/story.ts: an issue becomes a deck of full-screen cards.
// Each heading starts a card; the blocks under it become its body, paired by
// translation unit. The comments in the TypeScript explain each rule.

enum StoryCard: Identifiable {
    case cover(Cover)
    case section(SectionDivider)
    case content(Content)

    struct Cover {
        let sectionLabel: String
        let sectionNumber: String
        let series: String?
        let title: String
        let summary: String?
        let date: String?
        let minutes: Int
        let count: Int
        var image: IssueCover? = nil
    }

    struct SectionDivider {
        let heading: String
        let index: Int
        let total: Int
    }

    struct Content {
        let heading: String?
        let subtitle: String?
        let kicker: String?
        var blocks: [AnnotatedBlock]
    }

    // Cards are addressed by position in the deck; this is only for ForEach.
    var id: String {
        switch self {
        case let .cover(c): return "cover-\(c.title)"
        case let .section(s): return "section-\(s.index)"
        case let .content(c): return "content-\(c.heading ?? "")-\(c.blocks.count)-\(c.blocks.first.map { Annotate.blockText($0.block).prefix(16) } ?? "")"
        }
    }

    var content: Content? { if case let .content(c) = self { return c } else { return nil } }
}

enum StoryDeck {
    // ── Three Companies ──────────────────────────────────────────────────
    private static let stockCardLines = 7

    private static func estimateLines(_ text: String, ja: Bool) -> Int {
        var units = 0.0
        for s in text.unicodeScalars {
            let v = s.value
            let wide = (0x3000...0x30FF).contains(v) || (0x3400...0x9FFF).contains(v)
                || (0xAC00...0xD7A3).contains(v) || (0xFF00...0xFFEF).contains(v)
            units += wide ? 1 : 0.55
        }
        return max(1, Int(ceil(units / (ja ? 17 : 20))))
    }

    private static let jaSentence = "[^。！？]*[。！？]+[」』）)]*|[^。！？]+$"

    static func splitJa(_ text: String) -> [String] {
        Rx.all(jaSentence, text).map { $0.groups[0].trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    static func splitKo(_ text: String) -> [String] {
        let chars = Array(text)
        var out: [String] = []
        var start = 0
        for i in chars.indices {
            let ch = chars[i]
            if ".!?".contains(ch) && (i + 1 == chars.count || chars[i + 1].isWhitespace) {
                if ch == ".", i > 0, chars[i - 1].isASCII, chars[i - 1].isLetter { continue }
                out.append(String(chars[start...i]).trimmingCharacters(in: .whitespacesAndNewlines))
                start = i + 1
            }
        }
        if start < chars.count {
            let rest = String(chars[start...]).trimmingCharacters(in: .whitespacesAndNewlines)
            if !rest.isEmpty { out.append(rest) }
        }
        return out.filter { !$0.isEmpty }
    }

    private static func splitRuby(_ segments: [RubySegment]) -> [[RubySegment]] {
        var out: [[RubySegment]] = []
        var current: [RubySegment] = []
        for seg in segments {
            if seg.reading != nil {
                current.append(seg)
                continue
            }
            let pieces = Rx.all(jaSentence, seg.text).map { $0.groups[0] }
            for piece in pieces.isEmpty ? [seg.text] : pieces {
                current.append(RubySegment(text: piece))
                if Rx.matches("[。！？][」』）)]*$", piece) {
                    out.append(current)
                    current = []
                }
            }
        }
        if current.contains(where: { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) {
            out.append(current)
        }
        return out
    }

    private struct SentencePair {
        var ja: [AnnotatedBlock]
        var ko: [AnnotatedBlock]
    }

    private static func sentencePairs(_ ja: AnnotatedBlock, _ ko: AnnotatedBlock?) -> [SentencePair] {
        let text = ja.block.paragraphText
        let jaTexts = splitJa(text)
        let rubies = ja.ruby.map(splitRuby)
        if jaTexts.count < 2 || (rubies != nil && rubies!.count != jaTexts.count) {
            return [SentencePair(ja: [ja], ko: ko.map { [$0] } ?? [])]
        }
        var audio: String? = nil
        if case let .paragraph(_, a) = ja.block { audio = a }
        var pairs: [SentencePair] = jaTexts.enumerated().map { i, t in
            var a = ja
            a.block = .paragraph(text: t, audio: i == 0 ? audio : nil)
            a.ruby = rubies?[i]
            return SentencePair(ja: [a], ko: [])
        }
        let koTexts = ko.map { splitKo($0.block.paragraphText) } ?? []
        for (j, t) in koTexts.enumerated() {
            let i = min(jaTexts.count - 1, (j * jaTexts.count) / koTexts.count)
            var k = ko!
            k.block = .paragraph(text: t, audio: nil)
            pairs[i].ko.append(k)
        }
        return pairs
    }

    private static func stockCards(_ heading: String, _ blocks: [AnnotatedBlock],
                                   _ subtitle: String?, _ kicker: String?) -> [StoryCard.Content] {
        func card(_ b: [AnnotatedBlock]) -> StoryCard.Content {
            StoryCard.Content(heading: heading, subtitle: subtitle, kicker: kicker, blocks: b)
        }
        let body = blocks.filter { !$0.block.isDivider }
        if body.isEmpty { return [] }
        if heading.contains("基本情報") || body.allSatisfy({ $0.lang == nil }) { return [card(body)] }

        var pairs: [SentencePair] = []
        var rest: [AnnotatedBlock] = []
        var i = 0
        while i < body.count {
            let a = body[i]
            if a.lang == .ja && a.block.isParagraph {
                let next = i + 1 < body.count ? body[i + 1] : nil
                let ko = (next?.lang == .ko && next?.block.isParagraph == true) ? next : nil
                pairs.append(contentsOf: sentencePairs(a, ko))
                if ko != nil { i += 1 }
            } else {
                rest.append(a)
            }
            i += 1
        }
        if pairs.isEmpty { return [card(body)] }

        func lines(_ p: SentencePair) -> Int {
            p.ja.reduce(0) { $0 + estimateLines($1.block.paragraphText, ja: true) }
                + p.ko.reduce(0) { $0 + estimateLines($1.block.paragraphText, ja: false) }
        }

        var cards: [StoryCard.Content] = []
        var group: [SentencePair] = []
        var used = 0
        func flush() {
            if group.isEmpty { return }
            cards.append(card(group.flatMap(\.ja) + group.flatMap(\.ko)))
            group = []
            used = 0
        }
        for p in pairs {
            let n = lines(p)
            if !group.isEmpty && used + n > stockCardLines { flush() }
            group.append(p)
            used += n
        }
        flush()
        if !rest.isEmpty { cards[cards.count - 1].blocks.append(contentsOf: rest) }
        return cards
    }

    // ── Every section ────────────────────────────────────────────────────

    static func build(_ annotated: [AnnotatedBlock], post: Post, section: NewsSection, minutes: Int) -> [StoryCard] {
        var cards: [StoryCard] = []

        struct Group {
            var heading: String?
            var subtitle: String?
            var level: Int
            var kicker: String?
            var blocks: [AnnotatedBlock]
        }
        var groups: [Group] = []

        for a in annotated {
            if a.block.isImage { continue }
            if case let .heading(level, text) = a.block {
                groups.append(Group(heading: text.trimmingCharacters(in: .whitespacesAndNewlines),
                                    subtitle: nil, level: level, kicker: nil, blocks: []))
                continue
            }
            guard !groups.isEmpty else { continue }
            let g = groups.count - 1

            if a.kicker, case let .paragraph(text, _) = a.block {
                if groups[g].kicker == nil { groups[g].kicker = text.trimmingCharacters(in: .whitespacesAndNewlines) }
                continue
            }
            if a.lang == .ko, case let .paragraph(text, _) = a.block, groups[g].subtitle == nil,
               !groups[g].blocks.contains(where: { $0.lang == .ja || $0.lang == .zh }) {
                groups[g].subtitle = text.trimmingCharacters(in: .whitespacesAndNewlines)
                continue
            }
            groups[g].blocks.append(a)
        }

        let sectionHeads = groups.filter { $0.level <= 2 && $0.blocks.isEmpty }
        var sectionSeen = 0

        func content(_ g: Group, _ blocks: [AnnotatedBlock]) -> StoryCard {
            .content(StoryCard.Content(heading: g.heading, subtitle: g.subtitle, kicker: g.kicker, blocks: blocks))
        }
        func appendToLast(_ blocks: [AnnotatedBlock]) -> Bool {
            guard case var .content(last) = cards.last else { return false }
            last.blocks.append(contentsOf: blocks)
            cards[cards.count - 1] = .content(last)
            return true
        }

        for g in groups {
            if g.level <= 2 && g.blocks.isEmpty {
                sectionSeen += 1
                cards.append(.section(StoryCard.SectionDivider(heading: g.heading ?? "", index: sectionSeen,
                                                               total: sectionHeads.count)))
                continue
            }
            if g.blocks.isEmpty { continue }

            if section.key == .stocks {
                cards.append(contentsOf: stockCards(g.heading ?? "", g.blocks, g.subtitle, g.kicker).map { .content($0) })
                continue
            }

            if section.sourceLang == .zh {
                let blocks = g.blocks.filter { !$0.block.isDivider }
                if !blocks.isEmpty { cards.append(content(g, blocks)) }
                continue
            }

            func isLabelCallout(_ a: AnnotatedBlock) -> Bool {
                if case let .callout(text, _) = a.block {
                    return text.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("日本語")
                }
                return false
            }

            var chunks: [[AnnotatedBlock]] = [[]]
            for a in g.blocks {
                if a.block.isDivider {
                    if !chunks[chunks.count - 1].isEmpty { chunks.append([]) }
                    continue
                }
                if isLabelCallout(a) { continue }
                let chunk = chunks[chunks.count - 1]
                let isEnglishLead = (a.block.isParagraph || a.block.isList)
                    && a.lang != .ja && a.lang != .zh && a.lang != .ko
                if isEnglishLead && chunk.contains(where: { $0.lang == .ko }) {
                    chunks.append([a])
                    continue
                }
                chunks[chunks.count - 1].append(a)
            }

            for chunk in chunks {
                let ja = chunk.filter { $0.lang == .ja }
                let zh = chunk.filter { $0.lang == .zh }
                let ko = chunk.filter { $0.lang == .ko }
                let en = chunk.filter { $0.lang != .ja && $0.lang != .zh && $0.lang != .ko }

                if chunk.contains(where: { $0.block.isList }) {
                    cards.append(content(g, chunk))
                    continue
                }
                let source = ja.isEmpty ? zh : ja
                if ko.count == 1 && source.count > 1 {
                    cards.append(content(g, chunk))
                    continue
                }

                let pairs = max(ja.count, zh.count, ko.count)
                if pairs == 0 {
                    if en.isEmpty { continue }
                    _ = appendToLast(en)
                    continue
                }

                let enPerCard = Int(ceil(Double(en.count) / Double(pairs)))
                for i in 0..<pairs {
                    let pair = [i < ja.count ? ja[i] : nil, i < zh.count ? zh[i] : nil, i < ko.count ? ko[i] : nil]
                        .compactMap { $0 }
                    if pair.isEmpty { continue }
                    if pair.count == 1 && i > 0 && appendToLast(pair) { continue }
                    let lo = min(en.count, i * enPerCard)
                    let hi = min(en.count, (i + 1) * enPerCard)
                    cards.append(content(g, Array(en[lo..<hi]) + pair))
                }
            }
        }

        let cover = StoryCard.Cover(
            sectionLabel: section.label, sectionNumber: section.number, series: post.series,
            title: post.title, summary: post.summary, date: Format.longDate(post.date),
            minutes: minutes, count: cards.count + 1, image: post.cover)
        return [.cover(cover)] + cards
    }
}
