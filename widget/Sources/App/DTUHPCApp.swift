import AppKit
import SwiftUI

@main
@MainActor
final class DTUHPCApp: NSObject, NSApplicationDelegate {
    static func main() {
        let app = NSApplication.shared
        let delegate = DTUHPCApp()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) {
            app.run()
        }
    }

    private let store = StatusStore()
    private var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        store.start()
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.store.refresh() }
        }
        if !CommandLine.arguments.contains("--background") {
            showWindow()
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        showWindow()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    private func showWindow() {
        if window == nil {
            let hosting = NSHostingView(rootView: SettingsView(store: store))
            let created = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 460, height: 560),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered, defer: false)
            created.title = "DTU HPC Status"
            created.isReleasedWhenClosed = false
            created.contentView = hosting
            created.center()
            window = created
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}
