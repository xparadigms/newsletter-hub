import Foundation

/// NSRegularExpression with the JavaScript semantics the web code was written
/// against: UTF-16 offsets, ICU syntax. Compiled patterns are cached.
enum Rx {
    private static var cache: [String: NSRegularExpression] = [:]
    private static let lock = NSLock()

    static func re(_ pattern: String) -> NSRegularExpression {
        lock.lock(); defer { lock.unlock() }
        if let r = cache[pattern] { return r }
        let r = try! NSRegularExpression(pattern: pattern)
        cache[pattern] = r
        return r
    }

    static func matches(_ pattern: String, _ text: String) -> Bool {
        let ns = text as NSString
        return re(pattern).firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) != nil
    }

    static func count(_ pattern: String, _ text: String) -> Int {
        let ns = text as NSString
        return re(pattern).numberOfMatches(in: text, range: NSRange(location: 0, length: ns.length))
    }

    /// Every match, as its capture groups (index 0 is the whole match).
    static func all(_ pattern: String, _ text: String) -> [(range: NSRange, groups: [String])] {
        let ns = text as NSString
        return re(pattern).matches(in: text, range: NSRange(location: 0, length: ns.length)).map { m in
            (m.range, (0..<m.numberOfRanges).map { i in
                let r = m.range(at: i)
                return r.location == NSNotFound ? "" : ns.substring(with: r)
            })
        }
    }

    static func replace(_ pattern: String, _ text: String, with template: String) -> String {
        let ns = text as NSString
        return re(pattern).stringByReplacingMatches(
            in: text, range: NSRange(location: 0, length: ns.length), withTemplate: template)
    }

    /// Like JS String.prototype.split with a capturing pattern: the captures
    /// land at the odd indices.
    static func splitKeepingCaptures(_ pattern: String, _ text: String) -> [String] {
        let ns = text as NSString
        var out: [String] = []
        var last = 0
        for m in re(pattern).matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            out.append(ns.substring(with: NSRange(location: last, length: m.range.location - last)))
            out.append(ns.substring(with: m.range(at: 1)))
            last = m.range.location + m.range.length
        }
        out.append(ns.substring(from: last))
        return out
    }
}
