from datetime import datetime
from app.extensions import db
from app.utils.time_zone import TimeZone


class UserEvent(db.Model):
    """
    User behavior events for analytics
    """
    __tablename__ = 'user_events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    event_name = db.Column(db.String(100), nullable=False, index=True)
    properties = db.Column(db.JSONB)  # Event-specific data
    timestamp = db.Column(
        db.DateTime(timezone=True),
        default=TimeZone.utc_now,
        nullable=False,
        index=True
    )
    session_id = db.Column(db.String(36), index=True)  # For session analysis

    # Relationships
    user = db.relationship('User', backref='events')

    # Indexes for analytics queries
    __table_args__ = (
        db.Index('idx_events_user_time', 'user_id', 'timestamp'),
        db.Index('idx_events_name_time', 'event_name', 'timestamp'),
        db.Index('idx_events_session', 'session_id', 'timestamp'),
    )


class EventAggregate(db.Model):
    """
    Pre-aggregated metrics for performance
    """
    __tablename__ = 'event_aggregates'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    event_name = db.Column(db.String(100), nullable=False)
    count = db.Column(db.Integer, default=0)
    sum_value = db.Column(db.Float)  # For numeric metrics
    avg_value = db.Column(db.Float)
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', 'event_name', name='uq_user_date_event'),
        db.Index('idx_aggregate_user_date', 'user_id', 'date'),
    )