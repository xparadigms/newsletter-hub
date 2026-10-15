import SwiftUI
import Observation

enum Route: Hashable {
    case section(SectionKey)
    case post(Post)
}

enum AppTab: Hashable {
    case today, sections, search
}

@MainActor
@Observable
final class Router {
    var tab: AppTab = .today
    var today: [Route] = []
    var sections: [Route] = []
    var search: [Route] = []
    /// The issue open in story mode, presented full screen over everything.
    var story: Post?

    /// Tapping the tab you are already on pops to its root, as on iOS.
    func select(_ next: AppTab) {
        if next == tab {
            switch next {
            case .today: today.removeAll()
            case .sections: sections.removeAll()
            case .search: search.removeAll()
            }
        }
        tab = next
    }

    /// thebrief://section/<key>, thebrief://post/<section>/<slug> and
    /// thebrief://story/<section>/<slug> — the site's paths, under the app's scheme.
    func open(_ url: URL, store: Store) {
        let parts = [url.host ?? ""] + url.pathComponents.filter { $0 != "/" }
        guard parts.count >= 2, let key = SectionKey(rawValue: parts[1]) else { return }
        if parts[0] == "section" {
            tab = .sections
            sections = [.section(key)]
            return
        }
        guard parts.count >= 3 else { return }
        let post = store.posts(in: key).first { $0.id == parts[2] }
            ?? Post(id: parts[2], section: key, title: "", series: nil, date: nil, summary: nil)
        switch parts[0] {
        case "story": story = post
        case "post":
            tab = .today
            today = [.post(post)]
        default: break
        }
    }

    func push(_ route: Route) {
        switch tab {
        case .today: today.append(route)
        case .sections: sections.append(route)
        case .search: search.append(route)
        }
    }
}
