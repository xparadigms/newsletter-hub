import Foundation

enum Format {
    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static func formatter(_ template: String) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.timeZone = TimeZone(identifier: "UTC")
        f.setLocalizedDateFormatFromTemplate(template)
        return f
    }

    private static let long = formatter("MMMMdyyyy")
    private static let short = formatter("MMMdd")
    private static let month = formatter("MMMMyyyy")

    static func date(_ s: String?) -> Date? { s.flatMap { parser.date(from: $0) } }

    /// "October 15, 2026"
    static func longDate(_ s: String?) -> String? {
        guard let s else { return nil }
        return date(s).map(long.string(from:)) ?? s
    }

    /// "Oct 15"
    static func shortDate(_ s: String?) -> String {
        guard let s else { return "—" }
        return date(s).map(short.string(from:)) ?? s
    }

    /// "October 2026", for the month groups in a section.
    static func month(_ s: String?) -> String {
        guard let d = date(s) else { return "Undated" }
        return month.string(from: d)
    }

    static func today() -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US")
        f.setLocalizedDateFormatFromTemplate("EEEEMMMMdyyyy")
        return f.string(from: Date())
    }
}
