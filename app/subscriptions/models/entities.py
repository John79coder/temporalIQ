from app.extensions import db
from app.utils.time_zone import TimeZone


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)


class UserSubscriptions(db.Model, TimestampMixin):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    plan_type = db.Column(db.String, nullable=False, default='free')  # e.g., 'free', 'basic', 'premium'
    status = db.Column(db.String, nullable=False, default='active')  # e.g., 'active', 'canceled', 'past_due'
    start_date = db.Column(db.DateTime(timezone=True), nullable=False)
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    stripe_id = db.Column(db.String, nullable=True)
    __table_args__ = (
        db.Index('idx_subscription_user_id', 'user_id'),
    )
