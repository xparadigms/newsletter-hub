import Foundation

enum SourceLang: String {
    case ja, zh
}

enum SectionKey: String, CaseIterable, Codable, Hashable, Identifiable {
    case startup, business, fintech, japan, watch, china, mandarin, stocks
    var id: String { rawValue }
}

struct NewsSection: Identifiable, Hashable {
    let key: SectionKey
    let number: String
    let label: String
    let title: String
    let description: String
    var sourceLang: SourceLang = .ja
    /// Paused: left out of the main list, but its archive still opens.
    var hideInNav = false
    let symbol: String

    var id: SectionKey { key }

    /// The toggle label for the source language, as the site shows it.
    var sourceLabel: String { sourceLang == .zh ? "中文" : "日本語" }
}

/// Mirrors SECTIONS in web/lib/config.ts. Same order, same copy.
enum Sections {
    static let all: [NewsSection] = [
        NewsSection(
            key: .startup, number: "01", label: "Startup", title: "Startup News",
            description: "Funding rounds, acquisitions, and the moves that matter across the startup landscape.",
            symbol: "paperplane"),
        NewsSection(
            key: .business, number: "02", label: "Business", title: "Business Insight",
            description: "Four pieces of business thinking a day from named founders, investors and operators — in Japanese, with a full Korean translation.",
            symbol: "lightbulb"),
        NewsSection(
            key: .fintech, number: "03", label: "Fintech", title: "Finance Infra",
            description: "A daily journal on the future of financial infrastructure — stablecoins, settlement rails, and tokenized money.",
            symbol: "chart.bar"),
        NewsSection(
            key: .japan, number: "04", label: "Japan", title: "Japan Daily Talk",
            description: "Politics, tech, and what Japan is actually talking about today — written as a conversation, in Japanese and Korean.",
            hideInNav: true, symbol: "mappin.and.ellipse"),
        NewsSection(
            key: .watch, number: "05", label: "Watch", title: "Watch Weekly",
            description: "A weekly read on the watch world — auctions, releases, and the market behind them.",
            hideInNav: true, symbol: "clock"),
        NewsSection(
            key: .china, number: "06", label: "China", title: "China Daily",
            description: "Politics, technology, and what China is actually talking about — short Chinese paragraphs with pinyin and a Korean read-through.",
            sourceLang: .zh, symbol: "building.columns"),
        NewsSection(
            key: .mandarin, number: "07", label: "Mandarin", title: "Mandarin Basics",
            description: "A daily Chinese lesson from beginner to intermediate — one grammar point, new words in context, and a short dialogue, all with pinyin and Korean.",
            sourceLang: .zh, symbol: "book"),
        NewsSection(
            key: .stocks, number: "08", label: "Stocks", title: "Three Companies",
            description: "Three public companies a day, two in the news and one wildcard, each as its own article in Japanese with furigana and a full Korean translation.",
            symbol: "chart.xyaxis.line"),
    ]

    static let nav = all.filter { !$0.hideInNav }
    static let paused = all.filter { $0.hideInNav }

    /// Tie-break order for same-day issues in the merged feed (web/lib/feed.ts).
    static let feedOrder: [SectionKey] = [.startup, .business, .stocks, .fintech, .japan, .china, .mandarin, .watch]

    static func get(_ key: SectionKey) -> NewsSection {
        all.first { $0.key == key }!
    }
}
