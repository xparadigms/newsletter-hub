import SwiftUI

/// A link to an issue. With story mode on it opens the full-screen story
/// instead of pushing the article — a reading preference, as on the site.
@MainActor
struct PostLink<Label: View>: View {
    let post: Post
    @ViewBuilder var label: () -> Label
    @Environment(Router.self) private var router
    @AppStorage(SettingsKey.storyMode) private var storyMode = false

    var body: some View {
        if storyMode {
            Button { router.story = post } label: { label().contentShape(Rectangle()) }
                .buttonStyle(.plain)
        } else {
            NavigationLink(value: Route.post(post)) { label() }
        }
    }
}

/// Small uppercase monospaced label, the site's `.label`.
@MainActor
struct Eyebrow: View {
    let text: String
    var color: Color = .secondary
    init(_ text: String, color: Color = .secondary) {
        self.text = text
        self.color = color
    }
    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 11, weight: .regular, design: .monospaced))
            .tracking(0.8)
            .foregroundStyle(color)
    }
}

@MainActor
struct PostRow: View {
    let post: Post
    var showSection = false

    var body: some View {
        PostLink(post: post) {
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(showSection
                        ? "\(Sections.get(post.section).label) · \(Format.shortDate(post.date))"
                        : Format.shortDate(post.date))
                Text(post.title)
                    .font(.body.weight(.medium))
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.leading)
                if let series = post.series, !series.isEmpty {
                    Text(series)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// Story mode, language, furigana and appearance — the site's nav bar toggles.
@MainActor
struct SettingsMenu: View {
    @AppStorage(SettingsKey.storyMode) private var storyMode = false
    @AppStorage(SettingsKey.langs) private var langs = LangMode.jaKo.rawValue
    @AppStorage(SettingsKey.furigana) private var furigana = true
    @AppStorage(SettingsKey.appearance) private var appearance = Appearance.system.rawValue

    var body: some View {
        Menu {
            Toggle(isOn: $storyMode) { Label("Story Mode", systemImage: "rectangle.portrait.on.rectangle.portrait") }
            Toggle(isOn: $furigana) { Label("Furigana", systemImage: "character.ja") }
            Picker(selection: $langs) {
                ForEach(LangMode.allCases) { Text($0.label(source: "日本語/中文")).tag($0.rawValue) }
            } label: { Label("Languages", systemImage: "globe") }
            Picker(selection: $appearance) {
                Text("System").tag(Appearance.system.rawValue)
                Text("Light").tag(Appearance.light.rawValue)
                Text("Dark").tag(Appearance.dark.rawValue)
            } label: { Label("Appearance", systemImage: "circle.lefthalf.filled") }
        } label: {
            Image(systemName: storyMode ? "rectangle.portrait.on.rectangle.portrait.fill" : "slider.horizontal.3")
        }
        .accessibilityLabel("Reading settings")
    }
}

@MainActor
struct ErrorBanner: View {
    let message: String
    var body: some View {
        Label(message, systemImage: "wifi.exclamationmark")
            .font(.footnote)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}
