# app/entitlements/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)


class SubscriptionTier(db.Model, TimestampMixin):
    __tablename__ = "subscription_tiers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    tier = db.Column(db.String, nullable=False, default='free')  # 'free', 'starter', 'pro', 'business'
    status = db.Column(db.String, nullable=False, default='active')  # 'active', 'trial', 'canceled', 'past_due'
    trial_ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    stripe_subscription_id = db.Column(db.String, nullable=True)
    stripe_customer_id = db.Column(db.String, nullable=True)
    annual_billing = db.Column(db.Boolean, default=False)
    __table_args__ = (
        db.Index('idx_subscription_tier_user_id', 'user_id'),
        db.Index('idx_subscription_tier_stripe_subscription_id', 'stripe_subscription_id'),
    )


class UsageMetrics(db.Model, TimestampMixin):
    __tablename__ = "usage_metrics"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    metric_type = db.Column(db.String, nullable=False)  # 'ai_generations', 'calendar_writes', etc.
    count = db.Column(db.Integer, default=0)
    period_start = db.Column(db.DateTime(timezone=True), nullable=False)
    period_end = db.Column(db.DateTime(timezone=True), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('user_id', 'metric_type', 'period_start', name='unique_user_metric_period'),
        db.Index('idx_usage_metrics_user_id', 'user_id'),
        db.Index('idx_usage_metrics_period', 'period_start', 'period_end'),
    )


class CreditPack(db.Model, TimestampMixin):
    __tablename__ = "credit_packs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    credit_type = db.Column(db.String, nullable=False)  # 'ai_generations', 'calendar_writes'
    credits_purchased = db.Column(db.Integer, nullable=False)
    credits_remaining = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    stripe_payment_intent_id = db.Column(db.String, nullable=True)
    __table_args__ = (
        db.Index('idx_credit_pack_user_id', 'user_id'),
    )


class TeamWorkspace(db.Model, TimestampMixin):
    __tablename__ = "team_workspaces"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = db.Column(db.String, nullable=True)
    seat_count = db.Column(db.Integer, default=3)
    __table_args__ = (
        db.Index('idx_team_workspace_owner_id', 'owner_user_id'),
    )


class TeamMembership(db.Model, TimestampMixin):
    __tablename__ = "team_memberships"
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("team_workspaces.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String, nullable=False, default='member')  # 'owner', 'admin', 'member'
    __table_args__ = (
        db.UniqueConstraint('workspace_id', 'user_id', name='unique_workspace_user'),
        db.Index('idx_team_membership_workspace_id', 'workspace_id'),
        db.Index('idx_team_membership_user_id', 'user_id'),
    )