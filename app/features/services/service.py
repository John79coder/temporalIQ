# app/features/services/service.py
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.features.models.entities import UserAISettings
from app.features.models.schemas import AISettingsUpdate
from app.features.repositories.repository import FeaturesRepository
from app.subscriptions.services.service import SubscriptionsService
from app.utils.caching import ICacheService
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.logging_service import LoggingService


class FeaturesService:
    def __init__(self, repo: FeaturesRepository, caching_service: ICacheService,
                 subscriptions_service: SubscriptionsService, logging_service: LoggingService):
        self.repo = repo
        self.caching_service = caching_service
        self.subscriptions_service = subscriptions_service
        self.logging_service = logging_service

    def create_default_settings(self, db: Session, user_id: int) -> UserAISettings:
        settings = UserAISettings(user_id=user_id)
        return self.repo.create_or_update(db, settings)

    def get_settings(self, db: Session, user_id: int) -> UserAISettings:
        """Retrieve AI settings for a user from the cache or database."""
        cache_key = f"features:ai_settings:{user_id}"
        cached = self.caching_service.get(cache_key)
        if cached:
            return UserAISettings.from_dict(cached)
        try:
            settings = self.repo.get_by_user(db, user_id)
            if not settings:
                self.logging_service.error("AI settings not found for user", user_id=user_id)
                raise DatabaseError("AI settings not found")
            self._cache_settings(user_id, settings)
            return settings
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to get AI settings", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to get AI settings") from e

    def update_settings(self, db: Session, user_id: int, update_data: AISettingsUpdate) -> UserAISettings:
        """Update AI settings for a user, checking premium status."""
        if not self.subscriptions_service.is_premium(db, user_id):
            raise DatabaseError("Premium subscription required to update AI settings")
        settings = self.get_settings(db, user_id)
        self._update_fields(settings, update_data)
        try:
            saved = self.repo.create_or_update(db, settings)
            self.caching_service.delete(f"features:ai_settings:{user_id}")  # Invalidate cache
            self._cache_settings(user_id, saved)
            return saved
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to update AI settings", user_id=user_id,
                                       extra={"error": str(e), "update_data": update_data.model_dump()})
            raise wrap_external_error(e, DatabaseError, "Failed to update AI settings") from e

    def _update_fields(self, settings: UserAISettings, update_data: AISettingsUpdate):
        """Update individual fields of AI settings."""
        if update_data.use_llm_mapping is not None:
            settings.use_llm_mapping = update_data.use_llm_mapping
        if update_data.use_learned_detector is not None:
            settings.use_learned_detector = update_data.use_learned_detector
        if update_data.use_spacy_heuristics is not None:
            settings.use_spacy_heuristics = update_data.use_spacy_heuristics
        if update_data.use_embedding_similarity is not None:
            settings.use_embedding_similarity = update_data.use_embedding_similarity
        if update_data.use_ml_prioritization is not None:
            settings.use_ml_prioritization = update_data.use_ml_prioritization
        if update_data.use_nlp_urgency is not None:
            settings.use_nlp_urgency = update_data.use_nlp_urgency
        if update_data.use_rl_optimization is not None:
            settings.use_rl_optimization = update_data.use_rl_optimization
        if update_data.urgency_learning_scope is not None:
            settings.urgency_learning_scope = update_data.urgency_learning_scope
        if update_data.duration_learning_scope is not None:
            settings.duration_learning_scope = update_data.duration_learning_scope
        if update_data.mapping_learning_scope is not None:
            settings.mapping_learning_scope = update_data.mapping_learning_scope
        if update_data.slot_ranking_learning_scope is not None:
            settings.slot_ranking_learning_scope = update_data.slot_ranking_learning_scope
        if update_data.use_nlp_scoring is not None:
            settings.use_nlp_scoring = update_data.use_nlp_scoring

    def _cache_settings(self, user_id: int, settings: UserAISettings):
        """Cache AI settings for a user."""
        self.caching_service.set(
            f"features:ai_settings:{user_id}",
            settings.__dict__,
            timeout=3600  # Reduced to 1 hour
        )
