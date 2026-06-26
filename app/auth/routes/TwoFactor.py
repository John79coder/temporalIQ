# app/auth/routes/TwoFactor.py

from flask import request, jsonify, current_app, g, make_response

from app.auth.routes.api import bp
from app.extensions import limit, limiter
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, format_error_response


@bp.route("/2fa/setup", methods=["GET"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def setup_2fa():
    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        response = two_factor_service.setup(
            g.db,
            g.current_user.id,
        )

        g.db.commit()

        return jsonify(response), 200

    except AuthError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/setup/verify", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def verify_two_factor_setup():
    try:
        code = request.json.get("code")

        if not code:
            raise DataValidationError("Missing code")

    except Exception as e:
        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        backup_codes = two_factor_service.verify_setup(
            g.db,
            g.current_user.id,
            code,
        )

        g.db.commit()

        return jsonify(
            {
                "backup_codes": backup_codes
            }
        ), 200

    except AuthError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/status", methods=["GET"])
@verify_jwt
@limiter.limit(limit("10 per minute"))
def two_factor_status():
    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        response = two_factor_service.status(
            g.db,
            g.current_user.id,
        )

        return jsonify(response), 200

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa", methods=["DELETE"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("3 per minute"))
def disable_two_factor():
    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        two_factor_service.disable(
            g.db,
            g.current_user.id,
        )

        g.db.commit()

        return jsonify(
            {
                "message": "Two-factor authentication disabled."
            }
        ), 200

    except AuthError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/verify", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("10 per minute"))
def verify_two_factor_login():
    try:
        code = request.json.get("code")

        if not code:
            raise DataValidationError("Missing code")

    except Exception as e:
        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        verified = two_factor_service.verify_login(
            g.db,
            g.current_user.id,
            code,
        )

        return jsonify(
            {
                "verified": verified,
            }
        ), 200

    except AuthError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/backup-codes", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("3 per hour"))
def regenerate_backup_codes():
    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        backup_codes = two_factor_service.regenerate_backup_codes(
            g.db,
            g.current_user.id,
        )

        g.db.commit()

        return jsonify(
            {
                "backup_codes": backup_codes,
            }
        ), 200

    except AuthError as e:
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)