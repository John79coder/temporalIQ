# app/icloud/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone

class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)

class iCloudConnection(db.Model, TimestampMixin):
    __tablename__ = "icloud_connections"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    encrypted_app_password = db.Column(db.String, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    __table_args__ = (
        db.Index('idx_icloud_user_id', 'user_id'),
    )

class CalendarSelection(db.Model):
    __tablename__ = "icloud_calendar_selections"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    calendar_id = db.Column(db.String, nullable=False)
    display_name = db.Column(db.String)
    timezone = db.Column(db.String, default="UTC")
    is_default = db.Column(db.Boolean, default=True)
    __table_args__ = (
        db.UniqueConstraint('user_id', 'is_default', name='unique_user_default'),
        db.Index('idx_calendar_user_id', 'user_id'),
    )