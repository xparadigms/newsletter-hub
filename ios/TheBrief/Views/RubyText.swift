import SwiftUI
import UIKit
import CoreText

/// Text with readings set above it: furigana over kanji, pinyin over hanzi.
///
/// SwiftUI's Text cannot draw ruby, but Core Text can, and UILabel renders its
/// ruby annotations — so this wraps a UILabel. Hiding the readings makes them
/// transparent rather than removing them, the way the site does it, so the
/// lines keep their breaks and the text does not jump when toggled.
struct RubyText: UIViewRepresentable {
    let segments: [RubySegment]
    var fontSize: CGFloat = 19
    var showReadings = true
    /// Pinyin draws a rule under every word, as the site does.
    var underlineWords = false
    var language = "ja"
    var color: UIColor = .label

    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        label.setContentHuggingPriority(.defaultHigh, for: .vertical)
        return label
    }

    func updateUIView(_ label: UILabel, context: Context) {
        let traits = UITraitCollection(userInterfaceStyle: context.environment.colorScheme == .dark ? .dark : .light)
        label.attributedText = attributed(traits: traits)
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView label: UILabel, context: Context) -> CGSize? {
        let width = proposal.width ?? UIScreen.main.bounds.width - 40
        guard width > 0, width.isFinite else { return nil }
        label.preferredMaxLayoutWidth = width
        let size = label.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        return CGSize(width: width, height: ceil(size.height))
    }

    private func font() -> UIFont {
        if language.hasPrefix("zh"), let f = UIFont(name: "PingFangSC-Regular", size: fontSize) { return f }
        return UIFont.systemFont(ofSize: fontSize)
    }

    private func attributed(traits: UITraitCollection) -> NSAttributedString {
        let font = font()
        let style = NSMutableParagraphStyle()
        // Room above every line for the reading row, whether or not this line
        // has one, so lines keep an even rhythm (the site's line-height: 2.35).
        style.minimumLineHeight = fontSize * 2.05
        style.lineBreakStrategy = .standard

        let rubyColor = (showReadings ? UIColor.secondaryLabel : UIColor.clear).resolvedColor(with: traits).cgColor
        let ruleColor = UIColor(red: 0.78, green: 0.66, blue: 0.32, alpha: 0.6)
        let base: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: color.resolvedColor(with: traits),
            .paragraphStyle: style,
            NSAttributedString.Key(kCTLanguageAttributeName as String): language,
        ]

        let out = NSMutableAttributedString()
        for (i, seg) in segments.enumerated() {
            var attrs = base
            if let reading = seg.reading, !reading.isEmpty {
                let rubyAttrs: [CFString: Any] = [
                    kCTRubyAnnotationSizeFactorAttributeName: underlineWords ? 0.5 : 0.55,
                    kCTForegroundColorAttributeName: rubyColor,
                ]
                let ruby = CTRubyAnnotationCreateWithAttributes(
                    .auto, .auto, .before, reading as CFString, rubyAttrs as CFDictionary)
                attrs[NSAttributedString.Key(kCTRubyAnnotationAttributeName as String)] = ruby
                if underlineWords {
                    attrs[.underlineStyle] = NSUnderlineStyle.single.rawValue
                    attrs[.underlineColor] = ruleColor
                }
            }
            out.append(NSAttributedString(string: seg.text, attributes: attrs))
            // A break opportunity between two words, which UILabel would
            // otherwise not take inside an unbroken run of hanzi.
            if underlineWords, seg.reading != nil, i + 1 < segments.count, segments[i + 1].reading != nil {
                out.append(NSAttributedString(string: "\u{200B}", attributes: base))
            }
        }
        return out
    }
}
