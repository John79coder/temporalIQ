import os
from typing import Dict, List


class AnalyticsConfig:
    """Configuration for analytics module"""

    # Event tracking settings
    EVENT_BUFFER_SIZE = int(os.getenv('ANALYTICS_BUFFER_SIZE', 100))
    EVENT_FLUSH_INTERVAL = int(os.getenv('ANALYTICS_FLUSH_INTERVAL', 60))  # seconds

    # Data retention settings
    RAW_EVENTS_RETENTION_DAYS = int(os.getenv('ANALYTICS_RAW_RETENTION', 90))
    AGGREGATES_RETENTION_DAYS = int(os.getenv('ANALYTICS_AGGREGATE_RETENTION', 365))

    # Aggregation settings
    AGGREGATION_BATCH_SIZE = 1000
    AGGREGATION_TIME = "02:00"  # Run at 2 AM

    # Feature flags
    ENABLE_REAL_TIME_ANALYTICS = os.getenv('ENABLE_REAL_TIME_ANALYTICS', 'false').lower() == 'true'
    ENABLE_EXPORT_TO_EXTERNAL = os.getenv('ENABLE_ANALYTICS_EXPORT', 'false').lower() == 'true'

    # External integrations (if enabled)
    AMPLITUDE_API_KEY = os.getenv('AMPLITUDE_API_KEY', '')
    MIXPANEL_API_KEY = os.getenv('MIXPANEL_API_KEY', '')
    SEGMENT_WRITE_KEY = os.getenv('SEGMENT_WRITE_KEY', '')

    # Events to track (whitelist)
    TRACKED_EVENTS: List[str] = [
        'user_signup',
        'user_login',
        'notion_connected',
        'icloud_connected',
        'task_scheduled',
        'sync_completed',
        'subscription_started',
        'feature_used'
    ]

    # Events that trigger notifications
    NOTIFICATION_EVENTS: Dict[str, str] = {
        'subscription_started': 'email',
        'sync_failed': 'in_app',
        'task_scheduled': 'none'
    }

    # Funnel definitions for analysis
    FUNNELS = {
        'onboarding': [
            'user_signup',
            'user_login',
            'notion_connected',
            'task_scheduled'
        ],
        'activation': [
            'user_login',
            'notion_connected',
            'icloud_connected',
            'task_scheduled'
        ]
    }

    # Metrics to compute in aggregation
    AGGREGATE_METRICS = [
        'count',
        'unique_users',
        'avg_duration',
        'success_rate'
    ]