import Foundation

// A port of web/lib/text.ts. The site and the app must agree on which language
// every paragraph is and where furigana attaches, so this follows the
// TypeScript line for line; the comments there explain the why of each rule.

enum Lang: String {
    case en, ja, ko, zh
}

struct RubySegment: Hashable, Codable {
    var text: String
    var reading: String?
}

struct AnnotatedBlock: Hashable {
    var block: Block
    /// nil = structural (headings, kickers, dividers, images): always visible.
    var lang: Lang?
    var kicker: Bool
    /// Set when a ふりがな toggle supplied readings for this paragraph.
    var ruby: [RubySegment]?
    /// Anchor for the table of contents (headings only).
    var headingID: String?
}

struct TocItem: Identifiable, Hashable {
    let id: String
    let text: String
    let level: Int
}

enum Annotate {
    static let rubyPattern =
        "([\\u4E00-\\u9FFF\\u3400-\\u4DBF\\u3005\\u3006\\u30F6]+|[A-Za-z0-9]+)\\uFF08([\\u3040-\\u30FF\\u30FC]+)\\uFF09"

    static func parseRuby(_ text: String) -> [RubySegment] {
        let ns = text as NSString
        var out: [RubySegment] = []
        var last = 0
        for m in Rx.all(rubyPattern, text) {
            if m.range.location > last {
                out.append(RubySegment(text: ns.substring(with: NSRange(location: last, length: m.range.location - last))))
            }
            out.append(RubySegment(text: m.groups[1], reading: m.groups[2]))
            last = m.range.location + m.range.length
        }
        if last < ns.length { out.append(RubySegment(text: ns.substring(from: last))) }
        return out
    }

    static func stripFurigana(_ text: String) -> String {
        Rx.replace(rubyPattern, text, with: "$1")
    }

    static func normalize(_ text: String) -> String {
        String(text.filter { !$0.isWhitespace })
    }

    static func plainText(_ block: Block) -> String {
        switch block {
        case let .paragraph(text, _): return text
        case let .list(_, items): return items.joined()
        default: return ""
        }
    }

    static func isKicker(_ text: String) -> Bool {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.count >= 3 && t.count <= 80
            && Rx.matches("[A-Z]{2}", t)
            && !Rx.matches("[a-z]", t)
            && !Rx.matches("[\\uAC00-\\uD7A3\\u3040-\\u30FF\\u4E00-\\u9FFF\\u3400-\\u4DBF]", t)
    }

    struct Counts { let hangul, kana, han, latin: Int }

    static func scriptCounts(_ text: String) -> Counts {
        var hangul = 0, kana = 0, han = 0, latin = 0
        for s in text.unicodeScalars {
            switch s.value {
            case 0xAC00...0xD7A3: hangul += 1
            case 0x3040...0x30FF: kana += 1
            case 0x4E00...0x9FFF, 0x3400...0x4DBF: han += 1
            case 0x41...0x5A, 0x61...0x7A: latin += 1
            default: break
            }
        }
        return Counts(hangul: hangul, kana: kana, han: han, latin: latin)
    }

    /// A generator-emitted source link: "🔗 https://…" on its own line.
    static func isSourceLine(_ text: String) -> Bool {
        text.drop { $0.isWhitespace }.hasPrefix("\u{1F517}")
    }

    static func classifyLang(_ text: String, hanLang: SourceLang = .ja) -> Lang {
        let c = scriptCounts(text)
        if c.hangul >= 3 && c.hangul > c.kana { return .ko }
        if c.kana > 0 && c.kana + c.han > c.latin { return .ja }
        if c.kana == 0 && c.han >= 3 && c.han > c.latin { return hanLang == .zh ? .zh : .ja }
        return .en
    }

    static func blockText(_ block: Block) -> String {
        switch block {
        case let .paragraph(text, _), let .heading(_, text), let .quote(text), let .code(text, _):
            return text
        case let .list(_, items):
            return items.joined(separator: " ")
        case let .pinyin(words, _):
            return words.map(\.text).joined()
        case let .callout(text, children), let .toggle(text, children):
            return ([text] + children.map(blockText)).joined(separator: " ")
        default:
            return ""
        }
    }

    static func blockAudio(_ block: Block) -> String? {
        switch block {
        case let .paragraph(_, audio), let .pinyin(_, audio): return audio
        default: return nil
        }
    }

    private static let prefixMatch = 12

    /// The remainder of `text` after `count` non-whitespace characters.
    static func sliceAfterNormalized(_ text: String, _ count: Int) -> String {
        var seen = 0
        var i = text.startIndex
        while i < text.endIndex && seen < count {
            if !text[i].isWhitespace { seen += 1 }
            i = text.index(after: i)
        }
        return String(text[i...])
    }

    /// Split one furigana string back across several paragraphs, given the
    /// plain length each paragraph should receive.
    static func splitRubyAcross(_ furigana: String, _ sizes: [Int]) -> [[RubySegment]] {
        let segments = parseRuby(furigana)
        var buckets: [[RubySegment]] = sizes.map { _ in [] }
        var bi = 0
        var filled = 0

        func advance() {
            while bi < sizes.count && filled >= sizes[bi] {
                filled -= sizes[bi]
                bi += 1
            }
        }

        for seg in segments {
            if seg.reading != nil {
                buckets[min(bi, buckets.count - 1)].append(seg)
                filled += normalize(seg.text).count
                advance()
                continue
            }
            var text = Substring(seg.text)
            while !text.isEmpty {
                if bi >= sizes.count {
                    buckets[buckets.count - 1].append(RubySegment(text: String(text)))
                    break
                }
                let remain = sizes[bi] - filled
                var take = text.startIndex
                var counted = 0
                while take < text.endIndex && counted < remain {
                    if !text[take].isWhitespace { counted += 1 }
                    take = text.index(after: take)
                }
                while take < text.endIndex && text[take].isWhitespace { take = text.index(after: take) }
                buckets[bi].append(RubySegment(text: String(text[..<take])))
                filled += counted
                text = text[take...]
                advance()
            }
        }
        return buckets
    }

    /// Attach a ふりがな toggle's readings to the run of earlier Japanese
    /// blocks it reproduces. Returns false when nothing matched.
    static func attachFurigana(_ out: inout [AnnotatedBlock], _ furigana: String) -> Bool {
        let plain = normalize(stripFurigana(furigana))
        if plain.isEmpty { return false }

        var run: [Int] = []
        var i = out.count - 1
        while i >= 0 {
            let a = out[i]
            if a.block.isHeading { break }
            if (a.block.isParagraph || a.block.isList) && a.lang == .ja && a.ruby == nil {
                run.insert(i, at: 0)
            }
            i -= 1
        }

        for idx in run {
            let written = plainText(out[idx].block)
            let nWritten = normalize(written)
            if nWritten.isEmpty { continue }

            if nWritten == plain {
                out[idx].ruby = parseRuby(furigana)
                return true
            }
            if nWritten.hasPrefix(plain) && Double(plain.count) >= Double(nWritten.count) * 0.6 {
                var segments = parseRuby(furigana)
                let tail = sliceAfterNormalized(written, plain.count)
                if !tail.isEmpty { segments.append(RubySegment(text: tail)) }
                out[idx].ruby = segments
                return true
            }
            if nWritten.count >= prefixMatch && plain.count >= prefixMatch
                && nWritten.prefix(prefixMatch) == plain.prefix(prefixMatch) {
                out[idx].ruby = parseRuby(furigana)
                return true
            }
        }

        if run.count >= 2 {
            for k in 2...run.count {
                var from = 0
                while from + k <= run.count {
                    let slice = Array(run[from..<(from + k)])
                    let texts = slice.map { normalize(plainText(out[$0].block)) }
                    let sizes = texts.map(\.count)
                    if sizes.reduce(0, +) > 0 && texts.joined() == plain {
                        let parts = splitRubyAcross(furigana, sizes)
                        for (j, idx) in slice.enumerated() where j < parts.count && !parts[j].isEmpty {
                            out[idx].ruby = parts[j]
                        }
                        return true
                    }
                    from += 1
                }
            }
        }
        return false
    }

    static func annotate(_ blocks: [Block], hanLang: SourceLang = .ja) -> [AnnotatedBlock] {
        var out: [AnnotatedBlock] = []
        var prev: Lang? = nil

        // Issues open with decorative dividers.
        var start = 0
        while start < blocks.count && blocks[start].isDivider { start += 1 }

        for block in blocks[start...] {
            if block.isDivider || block.isImage {
                out.append(AnnotatedBlock(block: block, lang: nil, kicker: false))
                continue
            }
            if case .pinyin = block {
                out.append(AnnotatedBlock(block: block, lang: .zh, kicker: false))
                prev = .zh
                continue
            }
            if case let .heading(_, text) = block {
                out.append(AnnotatedBlock(block: block, lang: nil, kicker: false,
                                          headingID: "h-\(out.count)-\(text.count)"))
                continue
            }
            if case let .paragraph(text, _) = block, isSourceLine(text) {
                out.append(AnnotatedBlock(block: block, lang: nil, kicker: false))
                continue
            }

            var lang: Lang
            var label = ""
            if case let .callout(text, _) = block { label = text.trimmingCharacters(in: .whitespacesAndNewlines) }
            if case let .toggle(text, _) = block { label = text.trimmingCharacters(in: .whitespacesAndNewlines) }

            if case .callout = block, label.hasPrefix("日本語"), label.count <= 12 {
                lang = .ja
            } else if case let .toggle(_, children) = block, Rx.matches("ふりがな|ひらがな", label) {
                let parts = children.compactMap { c -> String? in
                    if case let .paragraph(text, _) = c,
                       !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return text }
                    return nil
                }
                if !parts.isEmpty {
                    for part in parts {
                        if attachFurigana(&out, part) { continue }
                        out.append(AnnotatedBlock(
                            block: .paragraph(text: stripFurigana(part), audio: nil),
                            lang: .ja, kicker: false, ruby: parseRuby(part)))
                        prev = .ja
                    }
                    continue
                }
                lang = .ja
            } else {
                let text = blockText(block)
                lang = classifyLang(text, hanLang: hanLang)
                if lang == .en, let p = prev, p == .ja || p == .zh {
                    let c = scriptCounts(text)
                    if c.kana == 0 && c.latin == 0 && c.han > 0 { lang = p }
                }
            }
            var kicker = false
            if case let .paragraph(text, _) = block, lang == .en, isKicker(text) { kicker = true }
            out.append(AnnotatedBlock(block: block, lang: kicker ? nil : lang, kicker: kicker))
            prev = lang
        }
        return out
    }

    static func toc(_ annotated: [AnnotatedBlock]) -> [TocItem] {
        annotated.compactMap { a in
            guard case let .heading(level, text) = a.block, let id = a.headingID else { return nil }
            let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? nil : TocItem(id: id, text: t, level: level)
        }
    }

    static func readingTime(_ annotated: [AnnotatedBlock]) -> Int {
        var words = 0
        var hanzi = 0
        for a in annotated {
            if a.lang == .en {
                words += blockText(a.block).split(whereSeparator: { $0.isWhitespace }).count
            } else if a.lang == .zh {
                hanzi += blockText(a.block).unicodeScalars.filter {
                    (0x4E00...0x9FFF).contains($0.value) || (0x3400...0x4DBF).contains($0.value)
                }.count
            }
        }
        return max(1, Int((Double(words) / 230 + Double(hanzi) / 180).rounded()))
    }
}
