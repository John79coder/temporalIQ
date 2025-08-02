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