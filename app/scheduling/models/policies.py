# app/scheduling/models/policies.py


class SchedulingPolicy:
    """Encapsulates domain rules for scheduling tasks."""

    URGENCY_THRESHOLD = 0.7
    MIN_DURATION_MINUTES = 15
    MAX_DURATION_MINUTES = 120

    @staticmethod
    def should_prioritize_early(urgency: float) -> bool:
        """Determine if a task should be scheduled early based on urgency."""
        return urgency > SchedulingPolicy.URGENCY_THRESHOLD

    @staticmethod
    def clamp_duration(duration: float) -> int:
        """Clamp duration to valid range."""
        return max(SchedulingPolicy.MIN_DURATION_MINUTES, min(int(duration), SchedulingPolicy.MAX_DURATION_MINUTES))


# NEW: Shared mappings for consistency
PRIORITY_TO_URGENCY = {"high": 1.0, "medium": 0.66, "low": 0.33, None: 0.0}
PRIORITY_TO_WEIGHT = {"high": 3, "medium": 2, "low": 1, None: 0}


def get_urgency_float(value: str | float | None) -> float:
    """Utility to convert priority/urgency to float."""
    if isinstance(value, float):
        return value
    return PRIORITY_TO_URGENCY.get(value, 0.0)
