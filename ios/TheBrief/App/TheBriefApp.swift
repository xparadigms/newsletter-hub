import SwiftUI
import AVFoundation

@main
@MainActor
struct TheBriefApp: App {
    @State private var store = Store()
    @State private var router = Router()
    @AppStorage(SettingsKey.appearance) private var appearance = Appearance.system.rawValue

    init() {
        // Read-aloud keeps going with the screen locked or the switch on silent.
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .environment(router)
                .preferredColorScheme(Appearance(rawValue: appearance)?.scheme)
                .tint(.brandAccent)
        }
    }
}

@MainActor
struct RootView: View {
    @Environment(Store.self) private var store
    @Environment(Router.self) private var router

    var body: some View {
        @Bindable var router = router
        TabView(selection: Binding(get: { router.tab }, set: { router.select($0) })) {
            NavigationStack(path: $router.today) {
                TodayView().routes()
            }
            .tabItem { Label("Home", systemImage: "house") }
            .tag(AppTab.today)

            NavigationStack(path: $router.sections) {
                SectionsView().routes()
            }
            .tabItem { Label("Sections", systemImage: "square.grid.2x2") }
            .tag(AppTab.sections)

            NavigationStack(path: $router.search) {
                SearchView().routes()
            }
            .tabItem { Label("Search", systemImage: "magnifyingglass") }
            .tag(AppTab.search)
        }
        .onOpenURL { router.open($0, store: store) }
        .fullScreenCover(item: $router.story, onDismiss: { router.storyQueue = [] }) { post in
            StoryView(post: post)
        }
        // Opens on the saved lists at once, then brings them up to date.
        .task {
            #if DEBUG
            // `simctl launch … -openURL thebrief://…` opens a screen directly,
            // without the system's "Open in The Brief?" prompt.
            if let link = UserDefaults.standard.string(forKey: "openURL"), let url = URL(string: link) {
                router.open(url, store: store)
            }
            #endif
            await store.refresh()
        }
    }
}

extension View {
    /// The destinations every tab's stack can reach.
    func routes() -> some View {
        navigationDestination(for: Route.self) { route in
            switch route {
            case let .section(key): SectionView(section: Sections.get(key))
            case let .post(post): ArticleView(post: post)
            }
        }
    }
}
