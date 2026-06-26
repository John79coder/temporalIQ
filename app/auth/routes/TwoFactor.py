# app/auth/routes/TwoFactor.py
from datetime import timedelta

import jwt
from flask import request, jsonify, current_app, g, make_response

from app.auth.models.schemas import UserOut
from app.auth.routes.api import bp
from app.extensions import limit, limiter
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, format_error_response
from app.utils.time_zone import TimeZone


@bp.route("/2fa/setup", methods=["GET"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def setup_2fa():
    logging_service = current_app.extensions['app_context'].get_service('logging_service')
    two_factor_service = current_app.extensions["app_context"].get_service("two_factor_service")

    try:
        user_id = g.current_user.id if g.current_user else None
        logging_service.info("Starting 2FA setup", user_id=user_id)

        response = two_factor_service.setup(g.db, g.current_user.id)

        g.db.commit()

        logging_service.info("2FA setup successful", user_id=user_id)
        return jsonify(response), 200

    except AuthError as e:
        logging_service.error(f"AuthError in 2FA setup: {str(e)}", user_id=getattr(g.current_user, 'id', None))
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        logging_service.error(f"DatabaseError in 2FA setup: {str(e)}", user_id=getattr(g.current_user, 'id', None))
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:  # Catch unexpected errors
        logging_service.error(f"Unexpected error in 2FA setup: {str(e)}",
                              user_id=getattr(g.current_user, 'id', None))
        import traceback
        traceback.print_exc()
        error_response, status_code = format_error_response(AuthError("Failed to setup 2FA"), 500)
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/setup/verify", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def verify_two_factor_setup():
    logging_service = current_app.extensions['app_context'].get_service('logging_service')

    try:
        code = request.json.get("code")

        if not code:
            raise DataValidationError("Missing code")

    except Exception as e:
        logging_service.error(f"Validation error in 2FA verify: {str(e)}")
        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        user_id = g.current_user.id if g.current_user else None
        logging_service.info("Starting 2FA verification", user_id=user_id)

        backup_codes = two_factor_service.verify_setup(
            g.db,
            g.current_user.id,
            code,
        )

        g.db.commit()

        logging_service.info("2FA verification successful", user_id=user_id)

        return jsonify(
            {
                "backup_codes": backup_codes
            }
        ), 200

    except AuthError as e:
        logging_service.error(f"AuthError in 2FA verify: {str(e)}",
                             user_id=getattr(g.current_user, 'id', None))
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        logging_service.error(f"DatabaseError in 2FA verify: {str(e)}",
                             user_id=getattr(g.current_user, 'id', None))
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:
        logging_service.error(f"Unexpected error in 2FA verify: {str(e)}",
                             user_id=getattr(g.current_user, 'id', None))
        import traceback
        traceback.print_exc()
        error_response, status_code = format_error_response(AuthError("Failed to verify 2FA"), 500)
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
@csrf_protected
@limiter.limit(limit("10 per minute"))
def verify_two_factor_login():
    logging_service = current_app.extensions['app_context'].get_service('logging_service')

    try:
        code = request.json.get("code")
        user_id = request.json.get("user_id")   # For initial login (no JWT)

        if not code:
            raise DataValidationError("Missing code")

    except Exception as e:
        logging_service.error(f"Validation error in 2FA login verify: {str(e)}")
        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        # Two cases:
        # 1. Initial login (no JWT yet) — use user_id from request
        # 2. Already authenticated (with JWT) — use g.current_user
        if user_id:
            logging_service.info("2FA login verification (initial login)", user_id=user_id)
            verified = two_factor_service.verify_login(
                g.db,
                int(user_id),
                code,
            )
        else:
            # Normal authenticated case
            user_id = g.current_user.id if g.current_user else None
            logging_service.info("2FA login verification", user_id=user_id)
            verified = two_factor_service.verify_login(
                g.db,
                g.current_user.id,
                code,
            )

        if verified:
            # Issue JWT on successful 2FA verification during login
            jwt_token = jwt.encode(
                {
                    "sub": str(user_id),
                    "exp": TimeZone.utc_now() + timedelta(hours=24),
                },
                current_app.config["JWT_SECRET_KEY"],
                algorithm=current_app.config["JWT_ALGORITHM"],
            )

            # Get user for response
            authentication_service = current_app.extensions["app_context"].get_service("authentication_service")
            user = authentication_service.user_repo.get_by_id(g.db, user_id)

            logging_service.info("2FA login successful", user_id=user_id)

            return jsonify({
                "verified": True,
                "user": UserOut.model_validate(user).model_dump() if user else None,
                "jwt": jwt_token,
            }), 200
        else:
            logging_service.error("2FA code invalid", user_id=user_id)
            error_response, status_code = format_error_response(AuthError("Invalid code"), 400)
            return make_response(jsonify(error_response), status_code)

    except AuthError as e:
        logging_service.error(f"AuthError in 2FA login verify: {str(e)}", user_id=user_id)
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:
        logging_service.error(f"DatabaseError in 2FA login verify: {str(e)}", user_id=user_id)
        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:
        logging_service.error(f"Unexpected error in 2FA login verify: {str(e)}", user_id=user_id)
        import traceback
        traceback.print_exc()
        error_response, status_code = format_error_response(AuthError("2FA verification failed"), 500)
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