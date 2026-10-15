import AVFoundation
import Observation

/// Reads a card aloud: its sentences' pre-generated clips, one after another.
/// A clip that fails to load is skipped rather than stopping the card.
@MainActor
@Observable
final class AudioReader {
    private(set) var playing = false
    /// Called when a card's last clip ends on its own — not on stop().
    var onFinish: (() -> Void)?
    private var player: AVQueuePlayer?
    private var observers: [NSObjectProtocol] = []

    func play(_ urls: [String]) {
        stop()
        let items = urls.compactMap(URL.init(string:)).map(AVPlayerItem.init(url:))
        guard let last = items.last else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        let player = AVQueuePlayer(items: items)
        let center = NotificationCenter.default
        observers.append(center.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: last,
                                            queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.stop()
                self?.onFinish?()
            }
        })
        for item in items {
            observers.append(center.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: item,
                                                queue: .main) { [weak player] _ in
                MainActor.assumeIsolated { player?.advanceToNextItem() }
            })
        }
        self.player = player
        player.play()
        playing = true
    }

    func stop() {
        player?.pause()
        player?.removeAllItems()
        player = nil
        for o in observers { NotificationCenter.default.removeObserver(o) }
        observers.removeAll()
        playing = false
    }
}
