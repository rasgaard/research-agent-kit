import XCTest
@testable import DTUHPC

final class SnapshotTests: XCTestCase {
    private let cliJSON = """
    {
      "generated_at": "2026-10-23T12:00:00.123456+00:00",
      "host": "login9.hpc.dtu.dk",
      "ok": true,
      "records": [
        {"elapsed_seconds": 600, "job_id": "123", "index": "4", "key": "123[4]",
         "name": "train", "queue": "gpua100", "run_time": "00:10:00", "stat": "RUN",
         "start_time": "Oct 23 11:50:00 2026", "submit_time": "Oct 23 11:40"},
        {"elapsed_seconds": null, "job_id": "124", "index": null, "key": "124",
         "name": "eval", "queue": "p1", "run_time": "", "stat": "PEND",
         "start_time": "", "submit_time": "Oct 23 11:45"},
        {"elapsed_seconds": 5, "job_id": "125", "index": null, "key": "125",
         "name": "broken", "queue": "p1", "run_time": "00:00:05", "stat": "EXIT",
         "start_time": "", "submit_time": ""},
        {"elapsed_seconds": 9, "job_id": "126", "index": null, "key": "126",
         "name": "done", "queue": "p1", "run_time": "00:00:09", "stat": "DONE",
         "start_time": "", "submit_time": ""}
      ]
    }
    """

    private let fetched = Date(timeIntervalSince1970: 1_800_000_000)

    func testDecodesCLIEnvelopeAndWrapsWithFetchTime() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        XCTAssertTrue(snapshot.ok)
        XCTAssertEqual(snapshot.host, "login9.hpc.dtu.dk")
        XCTAssertEqual(snapshot.generatedAt, "2026-10-23T12:00:00.123456+00:00")
        XCTAssertEqual(snapshot.records.count, 4)
        XCTAssertEqual(snapshot.records[0].key, "123[4]")
        XCTAssertEqual(snapshot.records[0].elapsedSeconds, 600)
        XCTAssertNil(snapshot.records[1].elapsedSeconds)
    }

    func testCountsGroupLSFStates() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        XCTAssertEqual(snapshot.counts, JobCounts(running: 1, pending: 1, failed: 1, done: 1))
    }

    func testPrioritizedPutsFailuresThenRunningFirst() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        XCTAssertEqual(snapshot.prioritized().map(\.stat), ["EXIT", "RUN", "PEND", "DONE"])
    }

    func testFreshOKSnapshotDisplaysOK() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        XCTAssertEqual(snapshot.displayState(now: fetched.addingTimeInterval(60)), .ok)
    }

    func testOldSnapshotIsStale() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        let later = fetched.addingTimeInterval(snapshot.staleAfter + 1)
        XCTAssertEqual(snapshot.displayState(now: later), .stale)
    }

    func testStaleThresholdFollowsRefreshInterval() {
        let snapshot = StatusRunner.failure(host: "h", error: "x", message: "y", refreshSeconds: 600)
        XCTAssertEqual(snapshot.staleAfter, 1200)
    }

    func testRefreshIntervalDefaultsAndClamps() {
        XCTAssertEqual(WidgetSettings.refreshSeconds(fromMinutes: nil), 600)
        XCTAssertEqual(WidgetSettings.refreshSeconds(fromMinutes: "garbage"), 600)
        XCTAssertEqual(WidgetSettings.refreshSeconds(fromMinutes: "5"), 300)
        XCTAssertEqual(WidgetSettings.refreshSeconds(fromMinutes: " 0 "), 60)
        XCTAssertEqual(WidgetSettings.refreshSeconds(fromMinutes: "500"), 3600)
    }

    func testDecodedSnapshotCarriesRefreshInterval() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched,
                                                          refreshSeconds: 300))
        XCTAssertEqual(snapshot.refreshSeconds, 300)
        XCTAssertEqual(snapshot.staleAfter, 600)
    }

    func testRunningJobShowsRunningTimeAndPendingSaysPending() throws {
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        XCTAssertEqual(snapshot.records[0].runningLabel, "10m")
        XCTAssertEqual(snapshot.records[1].runningLabel, "pending")
        XCTAssertEqual(snapshot.records[1].queue, "p1")
    }

    func testRunningTimeFormatsHoursAndDays() throws {
        func job(_ seconds: Int) throws -> JobRecord {
            try JSONDecoder().decode(JobRecord.self, from: Data("""
            {"job_id": "1", "key": "1", "stat": "RUN", "queue": "p1", "name": "x",
             "run_time": "", "elapsed_seconds": \(seconds)}
            """.utf8))
        }
        XCTAssertEqual(try job(45).runningLabel, "0m")
        XCTAssertEqual(try job(14652).runningLabel, "4h 4m")
        XCTAssertEqual(try job(90_000).runningLabel, "1d 1h")
    }

    func testRecordWithoutElapsedStillDecodes() throws {
        let job = try JSONDecoder().decode(JobRecord.self, from: Data("""
        {"job_id": "1", "key": "1", "stat": "RUN", "queue": "p1", "name": "x", "run_time": ""}
        """.utf8))
        XCTAssertEqual(job.runningLabel, "")
    }

    func testAuthErrorRequiresLoginAndDecodesWithoutRecords() throws {
        let json = """
        {"ok": false, "host": "login9.hpc.dtu.dk", "generated_at": "2026-10-23T12:00:00+00:00",
         "error": "auth", "message": "no live SSH master for login9.hpc.dtu.dk; run: hpc login"}
        """
        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(json.utf8), fetchedAt: fetched))
        XCTAssertEqual(snapshot.records, [])
        XCTAssertEqual(snapshot.displayState(now: fetched), .loginRequired)
    }

    func testFailedFetchIsAnExplicitError() {
        let snapshot = StatusRunner.failure(host: "h", error: "missing", message: "no hpc")
        XCTAssertEqual(snapshot.displayState(now: Date()), .error("no hpc"))
    }

    func testUnparseableOutputDecodesToNil() {
        XCTAssertNil(StatusRunner.decode(Data("Job <999> is not found".utf8), fetchedAt: fetched))
    }

    func testSnapshotRoundTripsThroughAtomicFile() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let url = directory.appendingPathComponent("widget.json")
        defer { try? FileManager.default.removeItem(at: directory) }

        let snapshot = try XCTUnwrap(StatusRunner.decode(Data(cliJSON.utf8), fetchedAt: fetched))
        try SnapshotStore.save(snapshot, to: url)
        let loaded = try XCTUnwrap(SnapshotStore.load(from: url))
        XCTAssertEqual(loaded, snapshot)
    }

    func testMissingFileLoadsNil() {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("widget.json")
        XCTAssertNil(SnapshotStore.load(from: url))
    }
}
