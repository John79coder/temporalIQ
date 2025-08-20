# app/features/services/service.py
from typing import Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.features.models.entities import UserAISettings
from app.features.models.schemas import AISettingsUpdate, AISettingsOut
from app.features.repositories.repository import FeaturesRepository
from app.features.services.ai_settings_config import AISettingsConfiguration
from app.entitlements.services.entitlements_service import EntitlementsService
from app.utils.caching import ICacheService
from app.utils.exceptions import DatabaseError, wrap_external_error, AuthError
from app.utils.logging_service import LoggingService


class FeaturesService:
    def __init__(self, repo: FeaturesRepository, caching_service: ICacheService,
                 entitlements_service: EntitlementsService, logging_service: LoggingService):
        self.repo = repo
        self.caching_service = caching_service
        self.entitlements_service = entitlements_service
        self.logging_service = logging_service

    def create_default_settings(self, db: Session, user_id: int) -> UserAISettings:
        """Create default AI settings for a new user (all enabled, global learning)"""
        default_values = AISettingsConfiguration.get_default_settings()
        settings = UserAISettings(user_id=user_id, **default_values)
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
                # Create default settings if none exist
                self.logging_service.info(f"Creating default AI settings for user {user_id}")
                settings = self.create_default_settings(db, user_id)
            self._cache_settings(user_id, settings)
            return settings
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to get AI settings", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to get AI settings") from e

    def get_settings_with_capabilities(self, db: Session, user_id: int) -> Dict[str, Any]:
        """Get AI settings along with customization capabilities based on tier"""
        settings = self.get_settings(db, user_id)
        tier = self.entitlements_service.get_user_tier(db, user_id)

        capabilities = AISettingsConfiguration.get_tier_capabilities(tier)

        return {
            'settings': AISettingsOut.model_validate(settings).model_dump(),
            'tier': tier,
            'customizable': capabilities,
            'defaults': AISettingsConfiguration.get_default_settings()
        }

    def update_settings(self, db: Session, user_id: int, update_data: AISettingsUpdate) -> UserAISettings:
        """Update AI settings for a user, checking tier capabilities for each setting."""
        tier = self.entitlements_service.get_user_tier(db, user_id)

        # Check if user can customize AI settings at all
        if tier == 'free':
            raise AuthError(
                "Customizing AI settings requires a paid subscription. "
                "Upgrade to Starter or higher to customize AI behavior."
            )

        # Validate each setting being updated
        errors = []
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if value is not None and not AISettingsConfiguration.can_customize_setting(tier, field):
                required_tier = AISettingsConfiguration.get_required_tier_for_setting(field)
                setting_config = AISettingsConfiguration.SETTINGS_CONFIG.get(field)
                display_name = setting_config.display_name if setting_config else field
                errors.append(f"{display_name} requires {required_tier.title()} tier")

        if errors:
            raise AuthError(
                f"Your {tier.title()} plan cannot customize: {', '.join(errors)}. "
                f"Upgrade to access these advanced AI features."
            )

        settings = self.get_settings(db, user_id)
        self._update_fields(settings, update_data)

        try:
            saved = self.repo.create_or_update(db, settings)
            self.caching_service.delete(f"features:ai_settings:{user_id}")
            self._cache_settings(user_id, saved)

            # Log the update for analytics
            self.logging_service.info(
                "AI settings updated",
                user_id=user_id,
                extra={
                    'tier': tier,
                    'updated_fields': list(update_data.model_dump(exclude_unset=True).keys())
                }
            )

            return saved
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to update AI settings", user_id=user_id,
                                       extra={"error": str(e), "update_data": update_data.model_dump()})
            raise wrap_external_error(e, DatabaseError, "Failed to update AI settings") from e

    def reset_to_defaults(self, db: Session, user_id: int) -> UserAISettings:
        """Reset AI settings to defaults"""
        settings = self.get_settings(db, user_id)
        default_values = AISettingsConfiguration.get_default_settings()

        for key, value in default_values.items():
            setattr(settings, key, value)

        try:
            saved = self.repo.create_or_update(db, settings)
            self.caching_service.delete(f"features:ai_settings:{user_id}")
            self._cache_settings(user_id, saved)

            self.logging_service.info("AI settings reset to defaults", user_id=user_id)
            return saved
        except SQLAlchemyError as e:
            self.logging_service.error("Failed to reset AI settings", user_id=user_id, extra={"error": str(e)})
            raise wrap_external_error(e, DatabaseError, "Failed to reset AI settings") from e

    def _update_fields(self, settings: UserAISettings, update_data: AISettingsUpdate):
        """Update individual fields of AI settings."""
        for field, value in update_data.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(settings, field, value)

    def _cache_settings(self, user_id: int, settings: UserAISettings):
        """Cache AI settings for a user."""
        self.caching_service.set(
            f"features:ai_settings:{user_id}",
            settings.__dict__,
            timeout=3600  # 1 hour
        )