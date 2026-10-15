import AVFoundation
import Observation

/// One sentence to read: its pre-generated clip when the issue has one, and
/// otherwise its text, spoken by the phone's own voice for the language.
enum Utterance: Equatable {
    case clip(URL)
    case speech(String, language: String)
}

/// Reads a card aloud, sentence by sentence.
///
/// The clips are made with OpenAI's speech API when an issue is published.
/// When that fails — no credit, no key — a sentence simply has no clip, and
/// rather than going silent the card falls back to the system voice. A clip
/// that will not load falls back the same way, so a card always finishes.
@MainActor
@Observable
final class AudioReader {
    private(set) var playing = false
    /// Called when a card's last sentence ends on its own — not on stop().
    var onFinish: (() -> Void)?

    @ObservationIgnored private var queue: [Utterance] = []
    @ObservationIgnored private var cursor = 0
    @ObservationIgnored private var player: AVPlayer?
    @ObservationIgnored private var observers: [NSObjectProtocol] = []
    @ObservationIgnored private let synthesizer = AVSpeechSynthesizer()
    @ObservationIgnored private let speechDone = SpeechDelegate()

    init() {
        synthesizer.delegate = speechDone
        speechDone.finished = { [weak self] in self?.advance() }
    }

    func play(_ items: [Utterance]) {
        stop()
        guard !items.isEmpty else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        queue = items
        cursor = 0
        playing = true
        start(queue[0])
    }

    func stop() {
        queue = []
        cursor = 0
        clearPlayer()
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        playing = false
    }

    private func start(_ item: Utterance) {
        switch item {
        case let .clip(url):
            let entry = AVPlayerItem(url: url)
            let center = NotificationCenter.default
            observers.append(center.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: entry,
                                                queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.advance() }
            })
            observers.append(center.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: entry,
                                                queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.advance() }
            })
            let player = AVPlayer(playerItem: entry)
            self.player = player
            player.play()
        case let .speech(text, language):
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = Self.voice(for: language)
            // A little under natural pace, as the generated clips are asked to be.
            utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9
            utterance.postUtteranceDelay = 0.15
            synthesizer.speak(utterance)
        }
    }

    private func advance() {
        guard playing else { return }
        clearPlayer()
        cursor += 1
        if cursor < queue.count {
            start(queue[cursor])
        } else {
            stop()
            onFinish?()
        }
    }

    private func clearPlayer() {
        player?.pause()
        player = nil
        for o in observers { NotificationCenter.default.removeObserver(o) }
        observers.removeAll()
    }

    /// The best installed voice for the language: Premium, then Enhanced, then
    /// the default. Better ones can be downloaded in Settings > Accessibility >
    /// Spoken Content > Voices, and are picked up from then on.
    static func voice(for language: String) -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices().filter { $0.language == language }
        return voices.max { $0.quality.rawValue < $1.quality.rawValue } ?? AVSpeechSynthesisVoice(language: language)
    }
}

private final class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    var finished: (() -> Void)?

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        DispatchQueue.main.async { self.finished?() }
    }
}
