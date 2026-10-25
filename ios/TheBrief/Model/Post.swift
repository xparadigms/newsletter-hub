import Foundation

/// An issue's cover (shared/covers.py): its source's preview image, or a
/// freely licensed photo, with the credit to show beside it. Hotlinked.
struct Cover: Hashable, Codable {
    let url: String
    let credit: String
    let link: String
    let kind: String?
}

struct Post: Identifiable, Hashable, Codable {
    /// The slug. Unique within a section, which is how every lookup keys it.
    let id: String
    let section: SectionKey
    let title: String
    let series: String?
    /// "YYYY-MM-DD", date only.
    let date: String?
    let summary: String?
    var cover: Cover? = nil

    var routeID: String { "\(section.rawValue)/\(id)" }
}

struct PostDetail: Codable {
    let post: Post
    let blocks: [Block]
}

struct PinyinWord: Codable, Hashable {
    let text: String
    let pinyin: String?
}

/// The web's Block union (web/lib/types.ts), as stored in Supabase's `blocks`.
indirect enum Block: Codable, Hashable {
    case paragraph(text: String, audio: String?)
    case heading(level: Int, text: String)
    case list(ordered: Bool, items: [String])
    case quote(text: String)
    case callout(text: String, children: [Block])
    case toggle(text: String, children: [Block])
    case code(text: String, language: String)
    case image(url: String, caption: String)
    case pinyin(words: [PinyinWord], audio: String?)
    case divider

    private enum Keys: String, CodingKey {
        case type, text, audio, level, ordered, items, children, language, url, caption, words
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        let type = try c.decode(String.self, forKey: .type)
        func str(_ k: Keys) -> String { (try? c.decode(String.self, forKey: k)) ?? "" }
        func kids() -> [Block] { (try? c.decode(LossyBlocks.self, forKey: .children).blocks) ?? [] }
        switch type {
        case "paragraph": self = .paragraph(text: str(.text), audio: try? c.decode(String.self, forKey: .audio))
        case "heading": self = .heading(level: (try? c.decode(Int.self, forKey: .level)) ?? 2, text: str(.text))
        case "list":
            self = .list(ordered: (try? c.decode(Bool.self, forKey: .ordered)) ?? false,
                         items: (try? c.decode([String].self, forKey: .items)) ?? [])
        case "quote": self = .quote(text: str(.text))
        case "callout": self = .callout(text: str(.text), children: kids())
        case "toggle": self = .toggle(text: str(.text), children: kids())
        case "code": self = .code(text: str(.text), language: str(.language))
        case "image": self = .image(url: str(.url), caption: str(.caption))
        case "pinyin":
            self = .pinyin(words: (try? c.decode([PinyinWord].self, forKey: .words)) ?? [],
                           audio: try? c.decode(String.self, forKey: .audio))
        case "divider": self = .divider
        default:
            throw DecodingError.dataCorruptedError(forKey: .type, in: c, debugDescription: "Unknown block \(type)")
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Keys.self)
        switch self {
        case let .paragraph(text, audio):
            try c.encode("paragraph", forKey: .type); try c.encode(text, forKey: .text)
            try c.encodeIfPresent(audio, forKey: .audio)
        case let .heading(level, text):
            try c.encode("heading", forKey: .type); try c.encode(level, forKey: .level); try c.encode(text, forKey: .text)
        case let .list(ordered, items):
            try c.encode("list", forKey: .type); try c.encode(ordered, forKey: .ordered); try c.encode(items, forKey: .items)
        case let .quote(text):
            try c.encode("quote", forKey: .type); try c.encode(text, forKey: .text)
        case let .callout(text, children):
            try c.encode("callout", forKey: .type); try c.encode(text, forKey: .text); try c.encode(children, forKey: .children)
        case let .toggle(text, children):
            try c.encode("toggle", forKey: .type); try c.encode(text, forKey: .text); try c.encode(children, forKey: .children)
        case let .code(text, language):
            try c.encode("code", forKey: .type); try c.encode(text, forKey: .text); try c.encode(language, forKey: .language)
        case let .image(url, caption):
            try c.encode("image", forKey: .type); try c.encode(url, forKey: .url); try c.encode(caption, forKey: .caption)
        case let .pinyin(words, audio):
            try c.encode("pinyin", forKey: .type); try c.encode(words, forKey: .words)
            try c.encodeIfPresent(audio, forKey: .audio)
        case .divider:
            try c.encode("divider", forKey: .type)
        }
    }

    var isHeading: Bool { if case .heading = self { return true } else { return false } }
    var isDivider: Bool { if case .divider = self { return true } else { return false } }
    var isParagraph: Bool { if case .paragraph = self { return true } else { return false } }
    var isList: Bool { if case .list = self { return true } else { return false } }
    var isImage: Bool { if case .image = self { return true } else { return false } }

    /// Paragraph text, or "" for anything else.
    var paragraphText: String { if case let .paragraph(text, _) = self { return text } else { return "" } }
}

/// Decodes a block array, dropping any block of a type this build does not
/// know, so a new block type on the server never blanks a whole issue.
struct LossyBlocks: Codable {
    var blocks: [Block]

    init(from decoder: Decoder) throws {
        var c = try decoder.unkeyedContainer()
        var out: [Block] = []
        while !c.isAtEnd {
            if let b = try? c.decode(Block.self) {
                out.append(b)
            } else {
                _ = try? c.decode(Skip.self)
            }
        }
        blocks = out
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        try c.encode(blocks)
    }

    private struct Skip: Decodable {}
}
