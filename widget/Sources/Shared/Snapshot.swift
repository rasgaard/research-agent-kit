import Foundation

/// One job row from `hpc status --json` (`records[]`).
struct JobRecord: Codable, Equatable, Identifiable {
    let jobId: String
    let index: String?
    let key: String
    let stat: String
    let queue: String
    let name: String
    let runTime: String
    let startTime: String
    let elapsedSeconds: Int?

    var id: String { key }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobId = try container.decode(String.self, forKey: .jobId)
        index = try container.decodeIfPresent(String.self, forKey: .index)
        key = try container.decode(String.self, forKey: .key)
        stat = try container.decode(String.self, forKey: .stat)
        queue = try container.decode(String.self, forKey: .queue)
        name = try container.decode(String.self, forKey: .name)
        runTime = try container.decode(String.self, forKey: .runTime)
        startTime = try container.decodeIfPresent(String.self, forKey: .startTime) ?? ""
        elapsedSeconds = try container.decodeIfPresent(Int.self, forKey: .elapsedSeconds)
    }

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case index, key, stat, queue, name
        case runTime = "run_time"
        case startTime = "start_time"
        case elapsedSeconds = "elapsed_seconds"
    }

    /// LSF prints start times as `Oct 23 08:54:12 2026` in cluster-local time.
    var startDate: Date? {
        guard !startTime.isEmpty else { return nil }
        return Self.startFormatter.date(from: startTime)
    }

    /// `since 08:54` for jobs started today, otherwise `since Oct 22 08:54`.
    var startedLabel: String {
        guard let date = startDate else { return "not started" }
        if Calendar.current.isDateInToday(date) {
            return "since " + date.formatted(date: .omitted, time: .shortened)
        }
        return "since " + date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    private static let startFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "MMM d HH:mm:ss yyyy"
        return formatter
    }()
}

/// Widget settings from `~/.config/dtu-hpc/config.ini` `[widget]`.
enum WidgetSettings {
    static let defaultRefreshSeconds = 10 * 60

    /// `refresh_minutes`, clamped to 1–60; missing or invalid values fall back to 10.
    static func refreshSeconds(fromMinutes text: String?) -> Int {
        guard let text, let minutes = Int(text.trimmingCharacters(in: .whitespaces)) else {
            return defaultRefreshSeconds
        }
        return min(max(minutes, 1), 60) * 60
    }
}

/// Job counts by LSF state group.
struct JobCounts: Equatable {
    var running = 0
    var pending = 0
    var failed = 0
    var done = 0
}

/// What the widget and app should show for a snapshot.
enum DisplayState: Equatable {
    case ok
    case stale
    case loginRequired
    case error(String)
}

/// Snapshot written by the host app to `~/.local/state/dtu-hpc/widget.json`.
/// Wraps the `hpc status --json` envelope with the time the app fetched it.
struct StatusSnapshot: Codable, Equatable {
    let ok: Bool
    let host: String
    let generatedAt: String
    let fetchedAt: Date
    let error: String?
    let message: String?
    let records: [JobRecord]
    let refreshSeconds: Int

    init(ok: Bool, host: String, generatedAt: String, fetchedAt: Date,
         error: String? = nil, message: String? = nil, records: [JobRecord] = [],
         refreshSeconds: Int = WidgetSettings.defaultRefreshSeconds) {
        self.ok = ok
        self.host = host
        self.generatedAt = generatedAt
        self.fetchedAt = fetchedAt
        self.error = error
        self.message = message
        self.records = records
        self.refreshSeconds = refreshSeconds
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ok = try container.decode(Bool.self, forKey: .ok)
        host = try container.decodeIfPresent(String.self, forKey: .host) ?? ""
        generatedAt = try container.decodeIfPresent(String.self, forKey: .generatedAt) ?? ""
        fetchedAt = try container.decode(Date.self, forKey: .fetchedAt)
        error = try container.decodeIfPresent(String.self, forKey: .error)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        records = try container.decodeIfPresent([JobRecord].self, forKey: .records) ?? []
        refreshSeconds = try container.decodeIfPresent(Int.self, forKey: .refreshSeconds)
            ?? WidgetSettings.defaultRefreshSeconds
    }

    enum CodingKeys: String, CodingKey {
        case ok, host, error, message, records
        case generatedAt = "generated_at"
        case fetchedAt = "fetched_at"
        case refreshSeconds = "refresh_seconds"
    }

    /// Two missed polls mean stale.
    var staleAfter: TimeInterval { 2 * TimeInterval(refreshSeconds) }

    var counts: JobCounts {
        var counts = JobCounts()
        for record in records {
            switch record.stat {
            case "RUN": counts.running += 1
            case "PEND", "PSUSP": counts.pending += 1
            case "EXIT", "ZOMBI": counts.failed += 1
            case "DONE": counts.done += 1
            default: break
            }
        }
        return counts
    }

    /// Failed jobs first, then running, pending, and everything else.
    func prioritized() -> [JobRecord] {
        func rank(_ stat: String) -> Int {
            switch stat {
            case "EXIT", "ZOMBI": return 0
            case "RUN": return 1
            case "PEND", "PSUSP": return 2
            default: return 3
            }
        }
        return records.enumerated()
            .sorted { lhs, rhs in
                let (a, b) = (rank(lhs.element.stat), rank(rhs.element.stat))
                return a == b ? lhs.offset < rhs.offset : a < b
            }
            .map(\.element)
    }

    func displayState(now: Date) -> DisplayState {
        if error == "auth" { return .loginRequired }
        if !ok { return .error(message ?? error ?? "status unavailable") }
        if now.timeIntervalSince(fetchedAt) > staleAfter { return .stale }
        return .ok
    }
}

enum SnapshotStore {
    static var homeDirectory: URL {
        if let entry = getpwuid(getuid()), let dir = entry.pointee.pw_dir {
            return URL(fileURLWithPath: String(cString: dir), isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }

    static var stateDirectory: URL {
        homeDirectory.appendingPathComponent(".local/state/dtu-hpc", isDirectory: true)
    }

    static var snapshotURL: URL {
        stateDirectory.appendingPathComponent("widget.json")
    }

    static func load(from url: URL = snapshotURL) -> StatusSnapshot? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? decoder.decode(StatusSnapshot.self, from: data)
    }

    static func save(_ snapshot: StatusSnapshot, to url: URL = snapshotURL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try encoder.encode(snapshot).write(to: url, options: .atomic)
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
