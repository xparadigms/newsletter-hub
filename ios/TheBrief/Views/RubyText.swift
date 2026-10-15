import SwiftUI
import UIKit
import CoreText

/// Text with readings set above it: furigana over kanji, pinyin over hanzi.
///
/// SwiftUI's Text cannot draw ruby, but Core Text can, so this lays the text
/// out with a CTFramesetter and draws it itself. Hiding the readings makes
/// them transparent rather than removing them, the way the site does it, so
/// the lines keep their breaks and the text does not jump when toggled.
struct RubyText: UIViewRepresentable {
    let segments: [RubySegment]
    var fontSize: CGFloat = 19
    var showReadings = true
    /// Pinyin draws a rule under every word, as the site does.
    var underlineWords = false
    var language = "ja"
    var color: UIColor = .label

    func makeUIView(context: Context) -> CoreTextView {
        CoreTextView()
    }

    func updateUIView(_ view: CoreTextView, context: Context) {
        let traits = UITraitCollection(userInterfaceStyle: context.environment.colorScheme == .dark ? .dark : .light)
        view.text = attributed(traits: traits)
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView view: CoreTextView, context: Context) -> CGSize? {
        let width = proposal.width ?? UIScreen.main.bounds.width - 40
        guard width > 0, width.isFinite else { return nil }
        return CGSize(width: width, height: view.height(for: width))
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

        let rubyColor = (showReadings ? UIColor.secondaryLabel : UIColor.clear).resolvedColor(with: traits).cgColor
        let ruleColor = UIColor(red: 0.78, green: 0.66, blue: 0.32, alpha: 0.6)
        // Core Text reads its own colour keys, which take CGColor.
        let base: [NSAttributedString.Key: Any] = [
            .font: font,
            NSAttributedString.Key(kCTForegroundColorAttributeName as String): color.resolvedColor(with: traits).cgColor,
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
                // Pinyin is usually wider than its hanzi. No overhang makes Core
                // Text widen the base to fit it, as the browser's ruby does;
                // furigana may overhang the kana beside it, as print does.
                let ruby = CTRubyAnnotationCreateWithAttributes(
                    underlineWords ? .center : .auto, underlineWords ? .none : .auto, .before,
                    reading as CFString, rubyAttrs as CFDictionary)
                attrs[NSAttributedString.Key(kCTRubyAnnotationAttributeName as String)] = ruby
                if underlineWords {
                    attrs[.underlineStyle] = NSUnderlineStyle.single.rawValue
                    attrs[NSAttributedString.Key(kCTUnderlineColorAttributeName as String)] =
                        ruleColor.resolvedColor(with: traits).cgColor
                }
            }
            out.append(NSAttributedString(string: seg.text, attributes: attrs))
            // A thin space between two words: it keeps their readings from
            // running together and gives the line somewhere to break.
            if underlineWords, seg.reading != nil, i + 1 < segments.count, segments[i + 1].reading != nil {
                out.append(NSAttributedString(string: "\u{2009}", attributes: base))
            }
        }
        return out
    }
}

/// Draws an attributed string with Core Text, ruby annotations included.
final class CoreTextView: UIView {
    var text = NSAttributedString() {
        didSet {
            guard text != oldValue else { return }
            framesetter = CTFramesetterCreateWithAttributedString(text)
            setNeedsDisplay()
        }
    }
    private var framesetter = CTFramesetterCreateWithAttributedString(NSAttributedString())

    override init(frame: CGRect) {
        super.init(frame: frame)
        isOpaque = false
        backgroundColor = .clear
        contentMode = .redraw
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    func height(for width: CGFloat) -> CGFloat {
        let size = CTFramesetterSuggestFrameSizeWithConstraints(
            framesetter, CFRange(location: 0, length: text.length), nil,
            CGSize(width: width, height: .greatestFiniteMagnitude), nil)
        return ceil(size.height) + 2
    }

    override func draw(_ rect: CGRect) {
        guard let ctx = UIGraphicsGetCurrentContext() else { return }
        ctx.textMatrix = .identity
        ctx.translateBy(x: 0, y: bounds.height)
        ctx.scaleBy(x: 1, y: -1)
        let path = CGPath(rect: bounds, transform: nil)
        let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: 0, length: text.length), path, nil)
        CTFrameDraw(frame, ctx)
    }
}
