import SwiftUI

func jobColor(for stat: String) -> Color {
    switch stat {
    case "EXIT", "ZOMBI": return .red
    case "RUN": return .green
    case "PEND", "PSUSP": return .orange
    default: return .secondary
    }
}

/// Aligned columns: state, name, queue, running time.
struct JobTable: View {
    let jobs: [JobRecord]

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 4) {
            ForEach(jobs) { job in
                GridRow {
                    Text(job.stat).foregroundStyle(jobColor(for: job.stat))
                    Text(job.name).lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
                    Text(job.queue).foregroundStyle(.secondary)
                    Text(job.runningLabel).foregroundStyle(.secondary).gridColumnAlignment(.trailing)
                }
            }
        }
        .font(.caption.monospaced())
    }
}

/// Two lines per job for the small widget: state and name, then queue and running time.
struct CompactJobList: View {
    let jobs: [JobRecord]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(jobs) { job in
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 4) {
                        Text(job.stat).foregroundStyle(jobColor(for: job.stat))
                        Text(job.name).lineLimit(1)
                    }
                    HStack(spacing: 4) {
                        Text(job.queue)
                        Text(job.runningLabel)
                    }
                    .foregroundStyle(.secondary)
                }
            }
        }
        .font(.caption2.monospaced())
    }
}
