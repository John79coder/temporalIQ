# app/user_preferences/models/entities.py
from app.extensions import db
from config import Config
from app.utils.time_zone import TimeZone

class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)

class UserPreferences(db.Model, TimestampMixin):
    __tablename__ = "user_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    default_notion_db = db.Column(db.String, nullable=True)
    block_size_minutes = db.Column(db.Integer, default=Config.DEFAULT_BLOCK_MINUTES)
    allow_weekends = db.Column(db.Boolean, default=Config.INCLUDE_WEEKENDS)
    max_blocks_per_day = db.Column(db.Integer, default=Config.DEFAULT_MAX_BLOCKS_PER_DAY)
    work_hours = db.Column(db.Float, default=Config.DEFAULT_WORK_HOURS_PER_DAY)
    time_zone = db.Column(db.String, nullable=True, default="UTC")

    __table_args__ = (
        db.CheckConstraint('block_size_minutes > 0', name='check_block_size_positive'),
        db.CheckConstraint('max_blocks_per_day > 0', name='check_max_blocks_positive'),
        db.CheckConstraint('work_hours > 0', name='check_work_hours_positive'),
        db.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_preferences_user_id'),
        db.Index('idx_user_prefs_user_id', 'user_id'),
    )

    @staticmethod
    def from_dict(data: dict) -> 'UserPreferences':
        user_preferences = UserPreferences()
        user_preferences.id = data.get("id")
        user_preferences.user_id = data.get("user_id")
        user_preferences.default_notion_db = data.get("default_notion_db")
        user_preferences.block_size_minutes = data.get("block_size_minutes")
        user_preferences.allow_weekends = data.get("allow_weekends")
        user_preferences.max_blocks_per_day = data.get("max_blocks_per_day")
        user_preferences.work_hours = data.get("work_hours")
        user_preferences.time_zone = data.get("time_zone")
        user_preferences.created_at = data.get("created_at")
        user_preferences.updated_at = data.get("updated_at")
        return user_preferences