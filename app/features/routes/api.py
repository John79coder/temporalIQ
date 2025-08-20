# app/features/routes/api.py
from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError

from app.features.models.schemas import AISettingsUpdate, AISettingsOut
from app.features.services.ai_settings_config import AISettingsConfiguration
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, make_handled_error_response

bp = Blueprint("features", __name__, url_prefix="/features")


@bp.route("/ai-settings", methods=["GET"])
@verify_jwt
def get_ai_settings():
    """Get current AI settings and customization capabilities"""
    try:
        result = current_app.extensions['app_context'].get_service('features_service').get_settings_with_capabilities(
            g.db, g.current_user.id
        )
        return jsonify(result), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/ai-settings", methods=["POST"])
@verify_jwt
@csrf_protected
def update_ai_settings():
    """Update AI settings (tier-restricted)"""
    try:
        data = AISettingsUpdate(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        settings = current_app.extensions['app_context'].get_service('features_service').update_settings(
            g.db, g.current_user.id, data
        )
        return jsonify(AISettingsOut.model_validate(settings).model_dump()), 200
    except AuthError as e:
        # Return detailed error about which tier is needed
        return jsonify({
            "error": "insufficient_tier",
            "message": str(e),
            "upgrade_url": "/billing/upgrade",
            "settings_info": AISettingsConfiguration.SETTINGS_CONFIG
        }), 403
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/ai-settings/reset", methods=["POST"])
@verify_jwt
@csrf_protected
def reset_ai_settings():
    """Reset AI settings to defaults (all enabled, global learning)"""
    try:
        settings = current_app.extensions['app_context'].get_service('features_service').reset_to_defaults(
            g.db, g.current_user.id
        )
        return jsonify({
            "message": "AI settings reset to defaults",
            "settings": AISettingsOut.model_validate(settings).model_dump()
        }), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/ai-settings/capabilities", methods=["GET"])
@verify_jwt
def get_ai_capabilities():
    """Get which AI settings the user can customize based on their tier"""
    try:
        entitlements = current_app.extensions['app_context'].get_service('entitlements_service')
        tier = entitlements.get_user_tier(g.db, g.current_user.id)

        return jsonify({
            "tier": tier,
            "customizable_settings": list(AISettingsConfiguration.TIER_CUSTOMIZABLE_SETTINGS.get(tier, set())),
            "all_settings": AISettingsConfiguration.SETTINGS_CONFIG,
            "defaults": AISettingsConfiguration.get_default_settings()
        }), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)