# app/notion/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)


class NotionConnection(db.Model, TimestampMixin):
    __tablename__ = "notion_connections"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    access_token = db.Column(db.String, nullable=False)
    refresh_token = db.Column(db.String, nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    workspace_id = db.Column(db.String, nullable=False)
    __table_args__ = (
        db.Index('idx_notion_user_id', 'user_id'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": TimeZone.serialize_datetime(self.expires_at),
            "created_at": TimeZone.serialize_datetime(self.created_at),
            "updated_at": TimeZone.serialize_datetime(self.updated_at) if self.updated_at else None,
            "workspace_id": self.workspace_id
        }

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": TimeZone.serialize_datetime(self.expires_at),
            "created_at": TimeZone.serialize_datetime(self.created_at),
            "updated_at": TimeZone.serialize_datetime(self.updated_at) if self.updated_at else None,
            "workspace_id": self.workspace_id
        }

class FieldMapping(db.Model, TimestampMixin):
    __tablename__ = "field_mappings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notion_db_id = db.Column(db.String, nullable=False)
    title_field = db.Column(db.String, nullable=False)
    due_date_field = db.Column(db.String, nullable=True)
    duration_field = db.Column(db.String, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('user_id', 'notion_db_id', name='unique_user_db_mapping'),
        db.Index('idx_field_mapping_user_id', 'user_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'notion_db_id': self.notion_db_id,
            'title_field': self.title_field,
            'due_date_field': self.due_date_field,
            'duration_field': self.duration_field,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class TaskCandidate(db.Model, TimestampMixin):
    __tablename__ = "task_candidates"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notion_db_id = db.Column(db.String, nullable=True)  # CHANGED: Made nullable for pages
    title = db.Column(db.String, nullable=False)
    due_date = db.Column(db.DateTime(timezone=True))
    duration = db.Column(db.Integer, nullable=True)
    confidence = db.Column(db.Float, nullable=False)
    issues = db.Column(db.ARRAY(db.String), nullable=True)
    priority = db.Column(db.String, nullable=True)
    status = db.Column(db.String, nullable=True)
    tags = db.Column(db.ARRAY(db.String), nullable=True)
    alternatives = db.Column(db.JSONB, nullable=True)
    # NEW: Added fields for page extraction
    page_id = db.Column(db.String, nullable=True)
    source_block_ids = db.Column(db.ARRAY(db.String), nullable=True)
    verified = db.Column(db.Boolean, default=False)
    __table_args__ = (
        db.Index('idx_task_candidate_user_id', 'user_id'),
        db.Index('idx_task_candidate_notion_db_id', 'notion_db_id'),
    )
