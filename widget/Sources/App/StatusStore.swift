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

    static func configuredHost() -> String {
        let url = SnapshotStore.homeDirectory.appendingPathComponent(".config/dtu-hpc/config.ini")
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return "" }
        var inHPC = false
        for raw in text.split(separator: "\n") {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("[") { inHPC = line == "[hpc]"; continue }
            guard inHPC, let eq = line.firstIndex(of: "=") else { continue }
            if line[..<eq].trimmingCharacters(in: .whitespaces) == "host" {
                return line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            }
        }
        return ""
    }

    static func fetch() async -> StatusSnapshot {
        let host = configuredHost()
        guard let hpc = locateHPC() else {
            return failure(host: host, error: "missing",
                           message: "hpc CLI not found at ~/.local/bin/hpc")
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
        if let decoded = decode(data, fetchedAt: Date()) {
            return decoded
        }
        let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        return failure(host: host, error: "ssh",
                       message: detail.isEmpty ? "hpc status exited with code \(code)" : String(detail.prefix(500)))
    }

    static func decode(_ data: Data, fetchedAt: Date) -> StatusSnapshot? {
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
                              records: envelope.records ?? [])
    }

    static func failure(host: String, error: String, message: String) -> StatusSnapshot {
        StatusSnapshot(ok: false, host: host, generatedAt: "", fetchedAt: Date(),
                       error: error, message: message)
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

/// Owns the snapshot, polls every five minutes, and reloads widget timelines.
@MainActor
final class StatusStore: ObservableObject {
    static let interval: TimeInterval = 300

    @Published private(set) var snapshot: StatusSnapshot?
    @Published private(set) var refreshing = false
    @Published private(set) var launchAtLogin = LoginItem.isEnabled
    @Published private(set) var errorMessage: String?

    private var timer: Timer?

    init() {
        snapshot = SnapshotStore.load()
    }

    func start() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: Self.interval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        timer?.tolerance = 30
    }

    func refresh() {
        guard !refreshing else { return }
        refreshing = true
        Task {
            let fresh = await StatusRunner.fetch()
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
