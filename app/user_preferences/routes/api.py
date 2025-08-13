# app/user_preferences/routes/api.py
from flask import Blueprint, request, jsonify, g, current_app
from pydantic_core import ValidationError as PydanticValidationError

from app.user_preferences.models.schemas import PreferencesCreate, PreferencesOut
from app.user_preferences.settings_validator.service import PreferencesValidator
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, AuthError, DatabaseError
from app.utils.exceptions import make_handled_error_response, ServiceUnavailableError

bp = Blueprint("user", __name__)

validator = PreferencesValidator()


@bp.route("/user/preferences", methods=["POST"])
@verify_jwt
@csrf_protected
def set_preferences():
    try:
        prefs = PreferencesCreate(**request.json)
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    if prefs.user_id != int(g.user_id):
        return make_handled_error_response(AuthError, "Unauthorized access", 403)

    errors = validator.validate(prefs)
    if errors:
        return make_handled_error_response(DataValidationError, str(errors), 400)

    try:
        saved = current_app.extensions['app_context'].get_service('preferences_service').save_preferences(g.db, prefs)
        return jsonify(PreferencesOut.model_validate(saved).model_dump())
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except ServiceUnavailableError as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)


@bp.route("/user/preferences/<int:user_id>", methods=["GET"])
@verify_jwt
def get_preferences(user_id):
    if int(g.user_id) != user_id:
        return make_handled_error_response(AuthError, "Unauthorized access", 403)

    try:
        prefs = current_app.extensions['app_context'].get_service('preferences_service').get_preferences(g.db, user_id)
        return jsonify(PreferencesOut.model_validate(prefs).model_dump())
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(type(e), str(e), 500)


@bp.route("/user/preferences/reset", methods=["POST"])  # Added for Issue 8
@verify_jwt
@csrf_protected
def reset_preferences():
    user_id = int(g.user_id)
    try:
        saved = current_app.extensions['app_context'].get_service('preferences_service').reset_preferences(g.db,
                                                                                                           user_id)
        return jsonify(PreferencesOut.model_validate(saved).model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except ServiceUnavailableError as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)
