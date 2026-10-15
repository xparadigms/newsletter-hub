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

    func push(_ route: Route) {
        switch tab {
        case .today: today.append(route)
        case .sections: sections.append(route)
        case .search: search.append(route)
        }
    }
}
