import Foundation

// Prints how the app annotates and decks each issue in a samples file, in the
// same format as web/scripts/parity-dump.ts, so the two can be diffed. Built
// on the Mac by ios/Parity/run.sh from the app's own model and text sources.

struct Row: Decodable {
    let slug: String
    let section: SectionKey
    let title: String
    let series: String?
    let issue_date: String?
    let summary: String?
    let blocks: LossyBlocks
}

let data = try! Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
for r in try! JSONDecoder().decode([Row].self, from: data) {
    let section = Sections.get(r.section)
    let blocks = r.section == .stocks ? numberParts(r.blocks.blocks) : r.blocks.blocks
    let post = Post(id: r.slug, section: r.section, title: r.title, series: r.series, date: r.issue_date, summary: r.summary)
    let a = Annotate.annotate(blocks, hanLang: section.sourceLang)
    let minutes = Annotate.readingTime(a)
    print("# \(r.section.rawValue)/\(r.slug) minutes=\(minutes)")
    for x in a {
        let readings = x.ruby.map { $0.filter { $0.reading != nil }.count } ?? -1
        let type: String
        switch x.block {
        case .paragraph: type = "paragraph"
        case .heading: type = "heading"
        case .list: type = "list"
        case .quote: type = "quote"
        case .callout: type = "callout"
        case .toggle: type = "toggle"
        case .code: type = "code"
        case .image: type = "image"
        case .pinyin: type = "pinyin"
        case .divider: type = "divider"
        }
        print("A \(type) \(x.lang?.rawValue ?? "-") \(x.kicker ? "K" : ".") \(readings)")
    }
    for c in StoryDeck.build(a, post: post, section: section, minutes: minutes) {
        switch c {
        case let .content(c):
            print("C content \(c.blocks.count) \(c.blocks.map { $0.lang?.rawValue ?? "-" }.joined()) \(c.subtitle != nil ? "S" : ".") \(c.kicker != nil ? "K" : ".")")
        case .cover: print("C cover")
        case .section: print("C section")
        }
    }
}
