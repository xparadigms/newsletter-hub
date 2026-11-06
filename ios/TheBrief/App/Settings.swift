import SwiftUI

/// Which languages an issue shows, as on the site: the source language with
/// Korean (the default), English alone, or everything.
enum LangMode: String, CaseIterable, Identifiable {
    case jaKo = "ja-ko"
    case en
    case all
    var id: String { rawValue }

    func label(source: String) -> String {
        switch self {
        case .jaKo: return "\(source) · 한국어"
        case .en: return "English"
        case .all: return "All"
        }
    }

    /// Mirrors the site's CSS filter. `multi` is false for an English-only
    /// issue, which must never render blank in the default mode.
    func shows(_ lang: Lang?, multi: Bool) -> Bool {
        guard let lang else { return true }
        switch self {
        case .jaKo: return !(multi && lang == .en)
        case .en: return lang == .en
        case .all: return true
        }
    }
}

enum Appearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var scheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

/// Which half of The Brief the app shows. The Japanese-learning newsletters
/// and the Chinese-learning ones are read for different reasons, so each mode
/// keeps to its own: Home, the story tray, Feed, Sections and Explore all
/// follow it. Profile — your saves and history — shows everything.
enum AppMode: String, CaseIterable, Identifiable {
    case japan, china
    var id: String { rawValue }

    var title: String { self == .japan ? "Japan" : "China" }
    var flag: String { self == .japan ? "🇯🇵" : "🇨🇳" }

    var sections: [SectionKey] {
        switch self {
        case .japan: return [.startup, .business, .fintech, .stocks]
        case .china: return [.china, .mandarin]
        }
    }

    /// The ones with an hourly news feed — Mandarin Basics is a lesson.
    var feedSections: [SectionKey] {
        sections.filter { $0 != .mandarin }
    }
}

enum SettingsKey {
    static let mode = "mode"
    static let langs = "langs"
    static let furigana = "furigana"
    static let storyMode = "storyMode"
    static let appearance = "appearance"
}

extension Color {
    static let brandAccent = Color("AccentColor")
    static let gold = Color(red: 0.78, green: 0.66, blue: 0.32)
}
