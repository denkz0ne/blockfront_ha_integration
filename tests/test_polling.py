"""Source-aware adaptive polling tests."""

from datetime import timedelta

from custom_components.blockfront.polling import PollingPolicy


def test_policy_learns_only_distinct_source_markers_and_honors_bounds() -> None:
    policy = PollingPolicy(timedelta(seconds=30), timedelta(minutes=30), margin=0.1)
    policy.observe({"source_timestamp": "2026-10-22T10:00:00Z"})
    policy.observe({"source_timestamp": "2026-10-22T10:00:00Z"})
    assert policy.interval == timedelta(minutes=30)
    policy.observe({"source_timestamp": "2026-10-22T10:02:00Z"})
    policy.observe({"source_timestamp": "2026-10-22T10:04:00Z"})
    assert policy.interval == timedelta(seconds=132)


def test_missing_or_non_timestamp_metadata_falls_back_without_tight_loop() -> None:
    policy = PollingPolicy(timedelta(minutes=2), timedelta(minutes=40))
    assert policy.observe({"source_timestamp": "unknown"}) == timedelta(minutes=40)
    assert policy.observe({"source_timestamp": "unknown"}) == timedelta(minutes=40)
