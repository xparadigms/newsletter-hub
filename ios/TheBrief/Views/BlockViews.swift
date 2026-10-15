import SwiftUI

// Rendering of an issue's blocks, shared by the article and story mode — the
// native counterpart of web/components/ArticleBlocks.tsx.

enum Reading {
    static let base: CGFloat = 19
    static let small: CGFloat = 16
    static let zh: CGFloat = 23
}

/// URLs in plain text become tappable, shown without the scheme.
func linkified(_ text: String) -> AttributedString {
    guard text.contains("http") else { return AttributedString(text) }
    let parts = Rx.splitKeepingCaptures(
        "(https?://[^\\s<>\"'\\u3001\\u3002\\u300d\\uff09\\]]+)", text)
    var out = AttributedString()
    for (i, part) in parts.enumerated() {
        if i % 2 == 1, let url = URL(string: part) {
            var shown = Rx.replace("^https?://(www\\.)?", part, with: "")
            if shown.hasSuffix("/") { shown.removeLast() }
            var link = AttributedString(shown)
            link.link = url
            link.underlineStyle = .single
            out += link
        } else {
            out += AttributedString(part)
        }
    }
    return out
}

/// A leading "1." on a heading renders in gold, as on the site.
func headingText(_ text: String) -> Text {
    let m = Rx.all("^(\\d{1,2}\\.)\\s+", text)
    guard let first = m.first else { return Text(text) }
    let rest = (text as NSString).substring(from: first.range.length)
    return Text(first.groups[1]).foregroundColor(.gold) + Text(" " + rest)
}

private func isBulletLine(_ text: String) -> Bool {
    text.drop { $0.isWhitespace }.hasPrefix("・")
}

@MainActor
struct AnnotatedBlockView: View {
    let item: AnnotatedBlock
    var section: NewsSection
    var compact = false
    @AppStorage(SettingsKey.furigana) private var furigana = true

    var body: some View {
        if item.kicker, case let .paragraph(text, _) = item.block {
            Text(text)
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .tracking(1.2)
                .foregroundStyle(Color.brandAccent)
                .padding(.top, compact ? 4 : 24)
        } else if let ruby = item.ruby {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if item.block.isList { Text("•").font(.system(size: Reading.base)).foregroundStyle(.secondary) }
                RubyText(segments: ruby, fontSize: Reading.base, showReadings: furigana, language: "ja",
                         color: .label.withAlphaComponent(0.88))
            }
            .padding(.top, isBulletLine(item.block.paragraphText) ? 0 : (compact ? 2 : 8))
        } else if case let .heading(level, text) = item.block {
            headingText(text)
                .font(.system(size: level <= 1 ? Reading.base * 1.34 : level == 2 ? Reading.base * 1.15 : Reading.base,
                              weight: .bold))
                .foregroundStyle(.primary)
                .padding(.top, compact ? 0 : (level <= 1 ? 32 : 20))
                .frame(maxWidth: .infinity, alignment: .leading)
                .id(item.headingID ?? "")
        } else if case let .paragraph(text, _) = item.block, Annotate.isSourceLine(text) {
            Text(linkified(Rx.replace("^\\s*\\x{1F517}\\s*", text, with: "")))
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(.secondary)
                .tint(.secondary)
        } else {
            BlockView(block: item.block, lang: item.lang, section: section, compact: compact)
        }
    }
}

@MainActor
struct BlockView: View {
    let block: Block
    var lang: Lang? = nil
    var section: NewsSection
    var compact = false
    var size: CGFloat = Reading.base

    var body: some View {
        switch block {
        case let .paragraph(text, _):
            Text(linkified(text))
                .font(.system(size: size))
                .lineSpacing(size * 0.45)
                .foregroundStyle(.primary.opacity(0.88))
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, isBulletLine(text) ? 0 : (compact ? 2 : 10))
                .textSelection(.enabled)
        case let .heading(_, text):
            headingText(text).font(.system(size: size * 1.1, weight: .bold))
        case let .list(ordered, items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(ordered ? "\(i + 1)." : "•").foregroundStyle(.secondary)
                        Text(linkified(item)).lineSpacing(size * 0.35)
                    }
                }
            }
            .font(.system(size: size))
            .foregroundStyle(.primary.opacity(0.88))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, compact ? 2 : 10)
        case let .quote(text):
            HStack(spacing: 14) {
                Rectangle().fill(Color.brandAccent).frame(width: 3)
                Text(text).font(.system(size: size * 1.1, weight: .bold)).lineSpacing(5)
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 12)
        case let .callout(text, children):
            VStack(alignment: .leading, spacing: 4) {
                if !text.isEmpty { Eyebrow(text, color: .brandAccent) }
                ForEach(Array(children.enumerated()), id: \.offset) { _, child in
                    BlockView(block: child, section: section, compact: true, size: Reading.small)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
            .padding(.top, 14)
        case let .toggle(text, children):
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(children.enumerated()), id: \.offset) { _, child in
                        BlockView(block: child, section: section, compact: true, size: Reading.small)
                    }
                }
            } label: {
                Text(text).font(.system(size: 13, design: .monospaced)).foregroundStyle(.secondary)
            }
            .padding(.top, 14)
        case let .code(text, _):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(text).font(.system(size: 13, design: .monospaced)).padding(14)
            }
            .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 10))
            .padding(.top, 14)
        case let .image(url, caption):
            VStack(alignment: .leading, spacing: 6) {
                AsyncImage(url: URL(string: url)) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    Rectangle().fill(.quaternary).frame(height: 180)
                }
                .clipShape(RoundedRectangle(cornerRadius: 10))
                if !caption.isEmpty { Eyebrow(caption) }
            }
            .padding(.vertical, 16)
        case let .pinyin(words, _):
            RubyText(segments: words.map { RubySegment(text: $0.text, reading: $0.pinyin) },
                     fontSize: Reading.zh, showReadings: true, underlineWords: true, language: "zh-Hans",
                     color: .label.withAlphaComponent(0.9))
                .padding(.top, compact ? 2 : 10)
        case .divider:
            Divider().padding(.vertical, compact ? 8 : 22)
        }
    }
}
