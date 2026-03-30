# Copyright 2026 Protocol Wealth LLC
# Licensed under the MIT License
# https://github.com/Protocol-Wealth/pw-router

"""Tests for usage tracking."""

from pw_router.usage import UsageTracker


class TestUsageTracker:
    def test_record_request(self):
        tracker = UsageTracker()
        tracker.record_request("app-1", "claude-sonnet", 100, 50, 450.0)

        snap = tracker.snapshot()
        assert snap["totals"]["requests"] == 1
        assert snap["totals"]["prompt_tokens"] == 100
        assert snap["totals"]["completion_tokens"] == 50
        assert snap["totals"]["total_tokens"] == 150
        assert snap["by_client"]["app-1"]["claude-sonnet"]["requests"] == 1
        assert snap["by_client"]["app-1"]["claude-sonnet"]["avg_latency_ms"] == 450.0

    def test_multiple_clients(self):
        tracker = UsageTracker()
        tracker.record_request("app-1", "claude-sonnet", 100, 50, 400.0)
        tracker.record_request("app-2", "claude-sonnet", 200, 100, 600.0)
        tracker.record_request("app-1", "local-llama", 50, 25, 200.0)

        snap = tracker.snapshot()
        assert snap["totals"]["requests"] == 3
        assert snap["totals"]["prompt_tokens"] == 350
        assert snap["totals"]["total_tokens"] == 525
        assert len(snap["by_client"]) == 2
        assert len(snap["by_client"]["app-1"]) == 2
        assert snap["by_client"]["app-2"]["claude-sonnet"]["requests"] == 1

    def test_record_error(self):
        tracker = UsageTracker()
        tracker.record_error("app-1", "claude-sonnet")
        tracker.record_error("app-1", "claude-sonnet")

        snap = tracker.snapshot()
        assert snap["totals"]["errors"] == 2
        assert snap["by_client"]["app-1"]["claude-sonnet"]["errors"] == 2

    def test_record_stream_request(self):
        tracker = UsageTracker()
        tracker.record_stream_request("app-1", "claude-sonnet")

        snap = tracker.snapshot()
        assert snap["totals"]["requests"] == 1
        assert snap["totals"]["prompt_tokens"] == 0  # Unknown for streams

    def test_avg_latency(self):
        tracker = UsageTracker()
        tracker.record_request("app-1", "claude-sonnet", 100, 50, 400.0)
        tracker.record_request("app-1", "claude-sonnet", 100, 50, 600.0)

        snap = tracker.snapshot()
        assert snap["by_client"]["app-1"]["claude-sonnet"]["avg_latency_ms"] == 500.0

    def test_snapshot_has_uptime(self):
        tracker = UsageTracker()
        snap = tracker.snapshot()
        assert "uptime_seconds" in snap
        assert snap["uptime_seconds"] >= 0

    def test_empty_snapshot(self):
        tracker = UsageTracker()
        snap = tracker.snapshot()
        assert snap["totals"]["requests"] == 0
        assert snap["by_client"] == {}
