"""
Analytics module for tracking user behavior and business metrics.
Separate from application logging - focuses on product analytics.
"""

from app.analytics.services.event_tracker import EventTracker
from app.analytics.services.metrics_aggregator import MetricsAggregator
from app.analytics.config import AnalyticsConfig

__all__ = [
    'EventTracker',
    'MetricsAggregator',
    'AnalyticsConfig'
]

# Module version
__version__ = '1.0.0'