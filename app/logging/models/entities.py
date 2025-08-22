from datetime import datetime
from app.extensions import db
from app.utils.time_zone import TimeZone


class AuditLog(db.Model):
    """
    Persistent audit log for compliance and security events
    """
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    success = db.Column(db.Boolean, default=True)
    ip_address = db.Column(db.String(45))  # Support IPv6
    user_agent = db.Column(db.Text)
    event_metadata = db.Column(db.JSONB)  # Changed from 'metadata' to 'event_metadata'
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=TimeZone.utc_now,
        nullable=False,
        index=True
    )

    # Relationships
    user = db.relationship('User', backref='audit_logs')

    # Indexes for common queries
    __table_args__ = (
        db.Index('idx_audit_user_time', 'user_id', 'created_at'),
        db.Index('idx_audit_category_time', 'category', 'created_at'),
        db.Index('idx_audit_event_time', 'event_type', 'created_at'),
    )