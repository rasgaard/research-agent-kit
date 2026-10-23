import SwiftUI

struct SettingsView: View {
    @ObservedObject var store: StatusStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            Divider()
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            Divider()
            footer
        }
        .padding(16)
        .frame(minWidth: 420, minHeight: 420)
    }

    private var header: some View {
        HStack {
            Text("DTU HPC").font(.title2.bold())
            Spacer()
            if let host = store.snapshot?.host, !host.isEmpty {
                Text(host).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if let snapshot = store.snapshot {
            switch snapshot.displayState(now: Date()) {
            case .loginRequired:
                message("Login required. Click Login to HPC and authenticate in Terminal.", color: .orange)
            case .error(let text):
                message(text, color: .red)
            case .stale:
                message("Status is stale (last fetched \(snapshot.fetchedAt.formatted(date: .omitted, time: .shortened))). Refresh to update.", color: .orange)
                jobList(snapshot)
            case .ok:
                jobList(snapshot)
            }
        } else {
            message("No status yet. Refreshing…", color: .secondary)
        }
    }

    private func message(_ text: String, color: Color) -> some View {
        Text(text).foregroundStyle(color).fixedSize(horizontal: false, vertical: true)
    }

    private func jobList(_ snapshot: StatusSnapshot) -> some View {
        let counts = snapshot.counts
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 16) {
                Label("\(counts.running) running", systemImage: "play.fill")
                Label("\(counts.pending) pending", systemImage: "clock")
                Label("\(counts.failed) failed", systemImage: "xmark.octagon.fill")
                    .foregroundStyle(counts.failed > 0 ? .red : .secondary)
            }
            .font(.callout)
            List(snapshot.prioritized()) { job in
                HStack {
                    Text(job.stat)
                        .font(.caption.monospaced())
                        .foregroundStyle(color(for: job.stat))
                        .frame(width: 48, alignment: .leading)
                    Text(job.key).font(.caption.monospaced())
                    Text(job.name).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Text(job.runningLabel).font(.caption).foregroundStyle(.secondary)
                    Text(job.queue).font(.caption).foregroundStyle(.secondary)
                }
            }
            .listStyle(.inset(alternatesRowBackgrounds: true))
        }
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Button("Refresh now") { store.refresh() }
                    .disabled(store.refreshing)
                Button("Login to HPC") { store.loginToHPC() }
                Spacer()
                if store.refreshing { ProgressView().controlSize(.small) }
            }
            Toggle("Launch at login", isOn: Binding(
                get: { store.launchAtLogin },
                set: { store.setLaunchAtLogin($0) }))
            if let error = store.errorMessage {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            if let snapshot = store.snapshot {
                Text("Updated \(snapshot.fetchedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func color(for stat: String) -> Color {
        switch stat {
        case "EXIT", "ZOMBI": return .red
        case "RUN": return .green
        case "PEND", "PSUSP": return .orange
        default: return .secondary
        }
    }
}
