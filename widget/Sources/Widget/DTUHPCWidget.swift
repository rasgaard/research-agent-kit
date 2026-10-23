import SwiftUI
import WidgetKit

struct StatusEntry: TimelineEntry {
    let date: Date
    let snapshot: StatusSnapshot?
}

struct StatusProvider: TimelineProvider {
    func placeholder(in context: Context) -> StatusEntry {
        StatusEntry(date: Date(), snapshot: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (StatusEntry) -> Void) {
        completion(StatusEntry(date: Date(), snapshot: SnapshotStore.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<StatusEntry>) -> Void) {
        let now = Date()
        let entry = StatusEntry(date: now, snapshot: SnapshotStore.load())
        let refresh = entry.snapshot?.refreshSeconds ?? WidgetSettings.defaultRefreshSeconds
        completion(Timeline(entries: [entry], policy: .after(now.addingTimeInterval(TimeInterval(refresh)))))
    }
}

struct StatusWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: StatusEntry

    var body: some View {
        content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .widgetURL(URL(string: "dtuhpc://open"))
    }

    @ViewBuilder
    private var content: some View {
        if let snapshot = entry.snapshot {
            switch snapshot.displayState(now: entry.date) {
            case .loginRequired:
                notice("Login required", detail: "Open DTU HPC Status and click Login to HPC.", color: .orange)
            case .error(let text):
                notice("Status unavailable", detail: text, color: .red)
            case .stale:
                jobs(snapshot, stale: true)
            case .ok:
                jobs(snapshot, stale: false)
            }
        } else {
            notice("No status yet", detail: "Open DTU HPC Status to start polling.", color: .secondary)
        }
    }

    private var jobLimit: Int {
        switch family {
        case .systemSmall: return 3
        case .systemMedium: return 4
        default: return 10
        }
    }

    private func jobs(_ snapshot: StatusSnapshot, stale: Bool) -> some View {
        let counts = snapshot.counts
        let visible = Array(snapshot.prioritized().prefix(jobLimit))
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Text("▶ \(counts.running)").foregroundStyle(.green)
                Text("⏳ \(counts.pending)").foregroundStyle(.orange)
                Text("✖ \(counts.failed)").foregroundStyle(counts.failed > 0 ? .red : .secondary)
            }
            .font(.headline)
            if family == .systemSmall {
                CompactJobList(jobs: visible)
            } else {
                JobTable(jobs: visible)
            }
            Spacer(minLength: 0)
            Text((stale ? "Stale · " : "") + "Updated \(snapshot.fetchedAt.formatted(date: .omitted, time: .shortened))")
                .font(.caption2)
                .foregroundStyle(stale ? .orange : .secondary)
        }
    }

    private func notice(_ title: String, detail: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.headline).foregroundStyle(color)
            Text(detail).font(.caption).foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
    }
}

struct DTUHPCStatusWidget: Widget {
    let kind = "DTUHPCStatus"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: StatusProvider()) { entry in
            StatusWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("DTU HPC Jobs")
        .description("Running, pending, and failed LSF jobs.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

@main
struct DTUHPCWidgetBundle: WidgetBundle {
    var body: some Widget {
        DTUHPCStatusWidget()
    }
}
