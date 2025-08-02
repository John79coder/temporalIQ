# app/features/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone

class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)

class UserAISettings(db.Model, TimestampMixin):
    __tablename__ = "user_ai_settings"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    use_llm_mapping = db.Column(db.Boolean, default=True)
    use_learned_detector = db.Column(db.Boolean, default=True)
    use_spacy_heuristics = db.Column(db.Boolean, default=True)
    use_embedding_similarity = db.Column(db.Boolean, default=True)
    use_ml_prioritization = db.Column(db.Boolean, default=True)
    use_nlp_urgency = db.Column(db.Boolean, default=True)
    use_rl_optimization = db.Column(db.Boolean, default=True)
    urgency_learning_scope = db.Column(db.String, default='user')  # 'user', 'global', 'off'
    duration_learning_scope = db.Column(db.String, default='user')
    mapping_learning_scope = db.Column(db.String, default='user')
    slot_ranking_learning_scope = db.Column(db.String, default='user')
    use_nlp_scoring = db.Column(db.Boolean, default=True)
    # NEW: Added toggle for AI in page extraction
    use_ai_page_extraction = db.Column(db.Boolean, default=True)
    __table_args__ = (
        db.Index('idx_ai_settings_user_id', 'user_id'),
    )

    @staticmethod
    def from_dict(data: dict) -> 'UserAISettings':
        settings = UserAISettings()
        settings.id = data.get("id")
        settings.user_id = data.get("user_id")
        settings.use_llm_mapping = data.get("use_llm_mapping", True)
        settings.use_learned_detector = data.get("use_learned_detector", True)
        settings.use_spacy_heuristics = data.get("use_spacy_heuristics", True)
        settings.use_embedding_similarity = data.get("use_embedding_similarity", True)
        settings.use_ml_prioritization = data.get("use_ml_prioritization", True)
        settings.use_nlp_urgency = data.get("use_nlp_urgency", True)
        settings.use_rl_optimization = data.get("use_rl_optimization", True)
        settings.urgency_learning_scope = data.get("urgency_learning_scope", 'user')
        settings.duration_learning_scope = data.get("duration_learning_scope", 'user')
        settings.mapping_learning_scope = data.get("mapping_learning_scope", 'user')
        settings.slot_ranking_learning_scope = data.get("slot_ranking_learning_scope", 'user')
        settings.use_nlp_scoring = data.get("use_nlp_scoring", True)
        # NEW: Added in from_dict for new field
        settings.use_ai_page_extraction = data.get("use_ai_page_extraction", True)
        settings.created_at = data.get("created_at")
        settings.updated_at = data.get("updated_at")
        return settings

class AITrainingEvent(db.Model, TimestampMixin):
    __tablename__ = "ai_training_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    event_type = db.Column(db.String, nullable=False)  # e.g., 'urgency_feedback', 'duration_log'
    input_json = db.Column(db.JSON, nullable=True)
    label_json = db.Column(db.JSON, nullable=True)
    source = db.Column(db.String, nullable=False)  # e.g., 'user_confirm', 'model'
    __table_args__ = (
        db.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ai_event_user_id'),
        db.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='fk_ai_event_task_id'),
        db.Index('idx_ai_event_user_id', 'user_id'),
        db.Index('idx_ai_event_task_id', 'task_id'),
        db.Index('idx_ai_event_event_type', 'event_type'),
    )