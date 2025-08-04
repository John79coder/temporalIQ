# app/scheduling/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)

class TimeBlock(db.Model, TimestampMixin):
    __tablename__ = "time_blocks"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    calendar_id = db.Column(db.String, nullable=False)
    start = db.Column(db.DateTime(timezone=True), nullable=False)
    end = db.Column(db.DateTime(timezone=True), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    __table_args__ = (
        db.Index('idx_time_block_user_id', 'user_id'),
        db.Index('idx_time_block_calendar_id', 'calendar_id'),
        {'extend_existing': True}
    )

class Task(db.Model, TimestampMixin):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notion_db_id = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False)
    due_date = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    duration = db.Column(db.Integer, nullable=True)
    priority = db.Column(db.String, nullable=True)
    status = db.Column(db.String, nullable=True)
    urgency = db.Column(db.Float, nullable=True)  # NEW: Added float urgency for consistency in ML/computations
    __table_args__ = (
        db.Index('idx_task_user_id', 'user_id'),
        db.Index('idx_task_notion_db_id', 'notion_db_id'),
        {'extend_existing': True}
    )

class TaskCompletion(db.Model):
    __tablename__ = 'task_completions'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    success = db.Column(db.Boolean, default=True)
    __table_args__ = (
        db.Index('idx_task_completion_task_id', 'task_id'),
    )