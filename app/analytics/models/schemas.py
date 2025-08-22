from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class EventType(str, Enum):
    """Standard event types for analytics"""
    # Authentication events
    USER_SIGNUP = "user_signup"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"

    # Integration events
    NOTION_CONNECTED = "notion_connected"
    NOTION_DISCONNECTED = "notion_disconnected"
    ICLOUD_CONNECTED = "icloud_connected"
    ICLOUD_DISCONNECTED = "icloud_disconnected"

    # Task events
    TASK_CREATED = "task_created"
    TASK_SCHEDULED = "task_scheduled"
    TASK_COMPLETED = "task_completed"
    TASK_DELETED = "task_deleted"

    # Sync events
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"

    # Feature usage
    FEATURE_USED = "feature_used"
    SETTINGS_CHANGED = "settings_changed"

    # Subscription events
    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription_downgraded"

    # Generic
    API_REQUEST = "api_request"
    PAGE_VIEW = "page_view"
    CUSTOM = "custom"


class EventProperties(BaseModel):
    """Base schema for event properties"""

    class Config:
        extra = "allow"  # Allow additional fields


class TaskEventProperties(EventProperties):
    """Properties for task-related events"""
    task_id: int
    task_title: Optional[str] = None
    calendar_id: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: Optional[str] = None


class SyncEventProperties(EventProperties):
    """Properties for sync events"""
    sync_type: str  # 'notion', 'icloud', 'full'
    success: bool
    duration_ms: float
    error_message: Optional[str] = None
    items_synced: Optional[int] = None


class FeatureEventProperties(EventProperties):
    """Properties for feature usage events"""
    feature_name: str
    feature_category: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SubscriptionEventProperties(EventProperties):
    """Properties for subscription events"""
    plan_name: str
    plan_tier: str
    price: Optional[float] = None
    billing_period: Optional[str] = None  # 'monthly', 'yearly'


class UserEventIn(BaseModel):
    """Schema for creating a new user event"""
    user_id: int
    event_name: str
    properties: Optional[Dict[str, Any]] = Field(default_factory=dict)
    session_id: Optional[str] = None
    timestamp: Optional[datetime] = None

    @validator('event_name')
    def validate_event_name(cls, v):
        """Validate event name format"""
        if not v or len(v) > 100:
            raise ValueError("Event name must be between 1 and 100 characters")
        return v.lower().replace(' ', '_')


class UserEventOut(BaseModel):
    """Schema for returning user event data"""
    id: int
    user_id: int
    event_name: str
    properties: Dict[str, Any]
    session_id: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class EventAggregateOut(BaseModel):
    """Schema for returning aggregated event data"""
    user_id: int
    date: datetime
    event_name: str
    count: int
    sum_value: Optional[float]
    avg_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]

    class Config:
        from_attributes = True


class MetricsSummary(BaseModel):
    """Schema for user metrics summary"""
    user_id: int
    start_date: datetime
    end_date: datetime
    total_events: int
    unique_event_types: int
    daily_average: float
    events_by_type: Dict[str, int]
    trends: List[Dict[str, Any]]


class FunnelStep(BaseModel):
    """Schema for funnel analysis steps"""
    step_name: str
    event_name: str
    users_entered: int
    users_completed: int
    conversion_rate: float
    avg_time_to_complete: Optional[float]  # in seconds


class FunnelAnalysis(BaseModel):
    """Schema for complete funnel analysis"""
    funnel_name: str
    start_date: datetime
    end_date: datetime
    steps: List[FunnelStep]
    overall_conversion: float
    total_users: int
    completed_users: int


class CohortMetrics(BaseModel):
    """Schema for cohort analysis metrics"""
    cohort_name: str
    cohort_date: datetime
    size: int
    retention_rates: Dict[str, float]  # {"day_1": 0.8, "day_7": 0.6, etc.}
    lifetime_value: Optional[float]
    churn_rate: float