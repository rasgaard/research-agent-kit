import Foundation
import ServiceManagement
import WidgetKit

/// Runs `hpc status --json` and turns its output into a snapshot.
enum StatusRunner {
    static func locateHPC() -> URL? {
        let home = SnapshotStore.homeDirectory
        let candidates = [
            home.appendingPathComponent(".local/bin/hpc"),
            URL(fileURLWithPath: "/opt/homebrew/bin/hpc"),
            URL(fileURLWithPath: "/usr/local/bin/hpc"),
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    static func configValue(section wanted: String, key: String) -> String? {
        let url = SnapshotStore.homeDirectory.appendingPathComponent(".config/dtu-hpc/config.ini")
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        var inSection = false
        for raw in text.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("[") { inSection = line == "[\(wanted)]"; continue }
            guard inSection, let eq = line.firstIndex(of: "=") else { continue }
            if line[..<eq].trimmingCharacters(in: .whitespaces) == key {
                return line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            }
        }
        return nil
    }

    static func configuredHost() -> String {
        configValue(section: "hpc", key: "host") ?? ""
    }

    static func refreshSeconds() -> Int {
        WidgetSettings.refreshSeconds(fromMinutes: configValue(section: "widget", key: "refresh_minutes"))
    }

    static func fetch(refreshSeconds: Int) async -> StatusSnapshot {
        let host = configuredHost()
        guard let hpc = locateHPC() else {
            return failure(host: host, error: "missing",
                           message: "hpc CLI not found at ~/.local/bin/hpc",
                           refreshSeconds: refreshSeconds)
        }
        let output = await Task.detached { () -> (Data, Int32, String) in
            let process = Process()
            process.executableURL = hpc
            process.arguments = ["status", "--json"]
            let stdout = Pipe()
            let stderr = Pipe()
            process.standardOutput = stdout
            process.standardError = stderr
            do {
                try process.run()
            } catch {
                return (Data(), -1, error.localizedDescription)
            }
            let data = stdout.fileHandleForReading.readDataToEndOfFile()
            let errors = stderr.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return (data, process.terminationStatus, String(decoding: errors, as: UTF8.self))
        }.value

        let (data, code, stderr) = output
        if let decoded = decode(data, fetchedAt: Date(), refreshSeconds: refreshSeconds) {
            return decoded
        }
        let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        return failure(host: host, error: "ssh",
                       message: detail.isEmpty ? "hpc status exited with code \(code)" : String(detail.prefix(500)),
                       refreshSeconds: refreshSeconds)
    }

    static func decode(_ data: Data, fetchedAt: Date,
                       refreshSeconds: Int = WidgetSettings.defaultRefreshSeconds) -> StatusSnapshot? {
        struct Envelope: Decodable {
            let ok: Bool
            let host: String
            let generated_at: String
            let error: String?
            let message: String?
            let records: [JobRecord]?
        }
        guard let envelope = try? JSONDecoder().decode(Envelope.self, from: data) else { return nil }
        return StatusSnapshot(ok: envelope.ok, host: envelope.host,
                              generatedAt: envelope.generated_at, fetchedAt: fetchedAt,
                              error: envelope.error, message: envelope.message,
                              records: envelope.records ?? [], refreshSeconds: refreshSeconds)
    }

    static func failure(host: String, error: String, message: String,
                        refreshSeconds: Int = WidgetSettings.defaultRefreshSeconds) -> StatusSnapshot {
        StatusSnapshot(ok: false, host: host, generatedAt: "", fetchedAt: Date(),
                       error: error, message: message, refreshSeconds: refreshSeconds)
    }

    static func openLogin() {
        let script = NSAppleScript(source: """
            tell application "Terminal"
                activate
                do script "hpc login"
            end tell
            """)
        var error: NSDictionary?
        script?.executeAndReturnError(&error)
    }
}

/// Owns the snapshot, polls on the configured interval, and reloads widget timelines.
@MainActor
final class StatusStore: ObservableObject {
    @Published private(set) var snapshot: StatusSnapshot?
    @Published private(set) var refreshing = false
    @Published private(set) var launchAtLogin = LoginItem.isEnabled
    @Published private(set) var errorMessage: String?

    private let refreshSeconds = StatusRunner.refreshSeconds()
    private var timer: Timer?

    init() {
        snapshot = SnapshotStore.load()
    }

    func start() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: TimeInterval(refreshSeconds), repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        timer?.tolerance = 30
    }

    func refresh() {
        guard !refreshing else { return }
        refreshing = true
        Task {
            let fresh = await StatusRunner.fetch(refreshSeconds: refreshSeconds)
            do {
                try SnapshotStore.save(fresh)
                errorMessage = nil
            } catch {
                errorMessage = "could not write widget snapshot: \(error.localizedDescription)"
            }
            snapshot = fresh
            refreshing = false
            WidgetReloader.reload()
        }
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        do {
            try LoginItem.set(enabled)
            errorMessage = nil
        } catch {
            errorMessage = "launch at login: \(error.localizedDescription)"
        }
        launchAtLogin = LoginItem.isEnabled
    }

    func loginToHPC() {
        StatusRunner.openLogin()
    }
}

enum WidgetReloader {
    static func reload() {
        WidgetCenter.shared.reloadAllTimelines()
    }
}

enum LoginItem {
    static var isEnabled: Bool {
        SMAppService.mainApp.status == .enabled
    }

    static func set(_ enabled: Bool) throws {
        if enabled {
            try SMAppService.mainApp.register()
        } else {
            try SMAppService.mainApp.unregister()
        }
    }
}
