"""Bounded source-cadence learning for adaptive coordinator intervals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any


class PollingPolicy:
    """Estimate publication cadence from distinct source markers only."""

    def __init__(self, minimum: timedelta, maximum: timedelta, margin: float = 0.1) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self.margin = min(max(margin, 0.0), 0.5)
        self._markers: dict[str, list[datetime]] = {}
        self._last_marker: dict[str, str] = {}

    def observe(self, value: dict[str, Any]) -> timedelta:
        """Record a new source capture marker and return a bounded interval."""
        for dataset, marker in _markers(value):
            if self._last_marker.get(dataset) == marker:
                continue
            self._last_marker[dataset] = marker
            parsed = _parse_timestamp(marker)
            history = self._markers.setdefault(dataset, [])
            if parsed is not None and (not history or parsed > history[-1]):
                history.append(parsed)
                self._markers[dataset] = history[-6:]
        return self.interval

    @property
    def interval(self) -> timedelta:
        """Return median observed cadence plus safety margin within bounds."""
        estimates: list[float] = []
        for markers in self._markers.values():
            if len(markers) < 3:
                continue
            gaps = [
                (right - left).total_seconds()
                for left, right in zip(markers, markers[1:], strict=False)
                if right > left
            ]
            if len(gaps) >= 2:
                estimates.append(median(gaps) * (1 + self.margin))
        if not estimates:
            return self.maximum
        seconds = min(estimates)
        return timedelta(
            seconds=min(max(seconds, self.minimum.total_seconds()), self.maximum.total_seconds())
        )


def _markers(value: Any, path: str = "root") -> list[tuple[str, str]]:
    """Collect source timestamps independently for nested datasets."""
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        if value.get("error") is None and value.get("source_stale") is not True:
            for key in ("captured_at", "source_timestamp", "updated_at"):
                marker = value.get(key)
                if isinstance(marker, (str, int, float)) and not isinstance(marker, bool):
                    found.append((path, str(marker)))
                    break
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                found.extend(_markers(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, list)):
                found.extend(_markers(item, f"{path}.{index}"))
    return found


def _parse_timestamp(marker: str) -> datetime | None:
    """Parse ISO or epoch source timestamps without using local wall time."""
    try:
        if marker.isdigit():
            numeric = int(marker)
            if numeric > 10_000_000_000:
                numeric /= 1000
            return datetime.fromtimestamp(numeric, UTC)
        parsed = datetime.fromisoformat(marker.replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
