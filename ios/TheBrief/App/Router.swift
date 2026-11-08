import SwiftUI
import Observation

enum Route: Hashable {
    case section(SectionKey)
    case post(Post)
    /// Every newsletter, as a list — reached from the top of Explore.
    case allSections
}

enum AppTab: Hashable {
    case today, feed, podcasts, search, profile
}

@MainActor
@Observable
final class Router {
    var tab: AppTab = .today
    var today: [Route] = []
    var podcasts: [Route] = []
    var search: [Route] = []
    var profile: [Route] = []
    var feed: [Route] = []
    /// The issue open in story mode, presented full screen over everything.
    var story: Post?
    /// Set when a story is opened from the tray: finishing one section's issue
    /// moves on to the next section's, as Instagram moves between accounts.
    var storyQueue: [Post] = []

    func playStories(from post: Post, queue: [Post]) {
        storyQueue = queue
        story = post
    }

    /// Set by the story's own article button, the one deliberate way from a
    /// story to the full text.
    private var keepArticleOnClose = false

    /// The fullScreenCover's onDismiss. A story is put away back to the list it
    /// came from: if it was opened over an article — the article's Story
    /// button, or a link at its foot in story mode — the article goes too.
    func storyClosed() {
        storyQueue = []
        if !keepArticleOnClose, case .post? = currentPath.last { popCurrent() }
        keepArticleOnClose = false
    }

    /// From the story to an issue's full text. An article already under the
    /// story is replaced rather than stacked on.
    func openArticle(_ post: Post) {
        keepArticleOnClose = true
        if case let .post(top)? = currentPath.last {
            if top.routeID == post.routeID { return }
            popCurrent()
        }
        push(.post(post))
    }

    private var currentPath: [Route] {
        switch tab {
        case .today: return today
        case .podcasts: return podcasts
        case .search: return search
        case .profile: return profile
        case .feed: return feed
        }
    }

    private func popCurrent() {
        switch tab {
        case .today: today.removeLast()
        case .podcasts: podcasts.removeLast()
        case .search: search.removeLast()
        case .profile: profile.removeLast()
        case .feed: feed.removeLast()
        }
    }

    /// Tapping the tab you are already on pops to its root, as on iOS.
    func select(_ next: AppTab) {
        if next == tab {
            switch next {
            case .today: today.removeAll()
            case .podcasts: podcasts.removeAll()
            case .search: search.removeAll()
            case .profile: profile.removeAll()
            case .feed: feed.removeAll()
            }
        }
        tab = next
    }

    /// thebrief://section/<key>, thebrief://post/<section>/<slug> and
    /// thebrief://story/<section>/<slug> — the site's paths, under the app's scheme.
    /// Which shelf Profile should show, when a link asks for one.
    var requestedShelf: String?

    func open(_ url: URL, store: Store) {
        let parts = [url.host ?? ""] + url.pathComponents.filter { $0 != "/" }
        // thebrief://explore and thebrief://profile[/saved|read|timeline]
        if parts[0] == "explore" { tab = .search; return }
        if parts[0] == "feed" { tab = .feed; return }
        if parts[0] == "podcasts" { tab = .podcasts; podcasts = []; return }
        // thebrief://mode/japan or thebrief://mode/china
        if parts[0] == "mode", parts.count > 1, let mode = AppMode(rawValue: parts[1]) {
            UserDefaults.standard.set(mode.rawValue, forKey: SettingsKey.mode)
            tab = .today
            return
        }
        if parts[0] == "profile" {
            tab = .profile
            requestedShelf = parts.count > 1 ? parts[1] : nil
            return
        }
        guard parts.count >= 2, let key = SectionKey(rawValue: parts[1]) else { return }
        if parts[0] == "section" {
            // Every newsletter's profile lives under Explore now; Podcast Hub
            // is its own tab.
            if key == .podcasts { tab = .podcasts; podcasts = []; return }
            tab = .search
            search = [.section(key)]
            return
        }
        guard parts.count >= 3 else { return }
        let post = store.posts(in: key).first { $0.id == parts[2] }
            ?? Post(id: parts[2], section: key, title: "", series: nil, date: nil, summary: nil)
        switch parts[0] {
        case "story": story = post
        case "post" where key == .podcasts:
            tab = .podcasts
            podcasts = [.post(post)]
        case "post":
            tab = .today
            today = [.post(post)]
        default: break
        }
    }

    func push(_ route: Route) {
        switch tab {
        case .today: today.append(route)
        case .podcasts: podcasts.append(route)
        case .search: search.append(route)
        case .profile: profile.append(route)
        case .feed: feed.append(route)
        }
    }
}
