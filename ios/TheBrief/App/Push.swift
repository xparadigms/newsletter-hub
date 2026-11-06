import SwiftUI
import UIKit
import UserNotifications

/// Notifications when a newsletter is published.
///
/// The app asks once, registers with Apple, and leaves its device token — and
/// which mode it is in, so a China-mode phone hears about China Daily rather
/// than the stock picks — with Supabase through `register_device`, a function
/// that can only add or update a token. The newsletter jobs send the pushes
/// (shared/push.py). Tapping one opens the issue.
final class PushDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    static let openLink = Notification.Name("TheBriefOpenLink")

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async { application.registerForRemoteNotifications() }
        }
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(token, forKey: "pushToken")
        Task { await PushRegistration.register() }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("push registration failed: \(error)")
    }

    /// Shown as a banner even with the app open.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list])
    }

    /// Tapping a notification opens its issue: the payload carries a
    /// thebrief:// link, which Router.open already understands.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let link = response.notification.request.content.userInfo["link"] as? String, let url = URL(string: link) {
            DispatchQueue.main.async { NotificationCenter.default.post(name: Self.openLink, object: url) }
        }
        completionHandler()
    }
}

enum PushRegistration {
    /// Sends this phone's token and current mode to Supabase. Called when the
    /// token arrives and whenever the mode changes.
    static func register() async {
        guard let token = UserDefaults.standard.string(forKey: "pushToken") else { return }
        let mode = UserDefaults.standard.string(forKey: SettingsKey.mode) ?? AppMode.japan.rawValue
        try? await SupabaseClient.shared.registerDevice(token: token, mode: mode)
    }
}
