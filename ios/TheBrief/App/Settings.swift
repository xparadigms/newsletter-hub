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

enum SettingsKey {
    static let langs = "langs"
    static let furigana = "furigana"
    static let storyMode = "storyMode"
    static let appearance = "appearance"
}

extension Color {
    static let brandAccent = Color("AccentColor")
    static let gold = Color(red: 0.78, green: 0.66, blue: 0.32)
}
