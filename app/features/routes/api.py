from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError

from app.features.models.schemas import AISettingsUpdate, AISettingsOut
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, make_handled_error_response

bp = Blueprint("features", __name__, url_prefix="/features")


@bp.route("/ai-settings", methods=["GET"])
@verify_jwt
def get_ai_settings():
    try:
        settings = current_app.extensions['app_context'].get_service('features_service').get_settings(g.db,
                                                                                                      g.current_user.id)
        return jsonify(AISettingsOut.model_validate(settings).model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/ai-settings", methods=["POST"])
@verify_jwt
@csrf_protected
def update_ai_settings():
    try:
        data = AISettingsUpdate(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        settings = current_app.extensions['app_context'].get_service('features_service').update_settings(g.db,
                                                                                                         g.current_user.id,
                                                                                                         data)
        return jsonify(AISettingsOut.model_validate(settings).model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
