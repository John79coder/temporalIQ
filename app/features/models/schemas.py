# app/features/models/schemas.py
from pydantic import BaseModel, field_validator, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.utils.time_zone import TimeZone

class BaseOutModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={datetime: TimeZone.serialize_datetime}
    )

class AISettingsUpdate(BaseModel):
    use_llm_mapping: Optional[bool] = None
    use_learned_detector: Optional[bool] = None
    use_spacy_heuristics: Optional[bool] = None
    use_embedding_similarity: Optional[bool] = None
    use_ml_prioritization: Optional[bool] = None
    use_nlp_urgency: Optional[bool] = None
    use_rl_optimization: Optional[bool] = None
    urgency_learning_scope: Optional[str] = None
    duration_learning_scope: Optional[str] = None
    mapping_learning_scope: Optional[str] = None
    slot_ranking_learning_scope: Optional[str] = None
    use_nlp_scoring: Optional[bool] = None

    @field_validator("urgency_learning_scope", "duration_learning_scope", "mapping_learning_scope", "slot_ranking_learning_scope")
    def validate_scope(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ['user', 'global', 'off']:
            raise ValueError("Scope must be 'user', 'global', or 'off'")
        return v

class AISettingsOut(BaseOutModel):
    id: int
    user_id: int
    use_llm_mapping: bool
    use_learned_detector: bool
    use_spacy_heuristics: bool
    use_embedding_similarity: bool
    use_ml_prioritization: bool
    use_nlp_urgency: bool
    use_rl_optimization: bool
    urgency_learning_scope: str
    duration_learning_scope: str
    mapping_learning_scope: str
    slot_ranking_learning_scope: str
    use_nlp_scoring: bool
    created_at: datetime
    updated_at: Optional[datetime]

class AITrainingEventIn(BaseModel):
    user_id: Optional[int] = None
    task_id: Optional[int] = None
    event_type: str = Field(min_length=1)
    input_json: dict
    label_json: dict
    source: str = Field(min_length=1)

    @field_validator("input_json", "label_json")
    def validate_json(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("JSON fields must be dictionaries")
        return v

class AITrainingEventOut(BaseOutModel):
    id: int
    user_id: Optional[int]
    task_id: Optional[int]
    event_type: str
    input_json: dict
    label_json: dict
    source: str
    created_at: datetime
    updated_at: Optional[datetime]

class DurationLogInput(BaseModel):
    num_events: int
    day_length_hours: float
    urgency: float

class DurationLogLabel(BaseModel):
    duration_minutes: float

class SlotChoiceInput(BaseModel):
    slot_start: str
    urgency: Optional[str]
    duration: float

class SlotChoiceLabel(BaseModel):
    selected: bool

class MappingFeedbackInput(BaseModel):
    field_name: str

class MappingFeedbackLabel(BaseModel):
    concept: str

class UrgencyFeedbackInput(BaseModel):
    title: str

class UrgencyFeedbackLabel(BaseModel):
    urgency_score: float