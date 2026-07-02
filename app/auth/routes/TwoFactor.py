# app/auth/routes/TwoFactor.py
from flask import request, jsonify, current_app, g, make_response

import logging

from app.auth.routes.api import bp, _serialize_user
from app.extensions import limit, limiter

from app.utils.exceptions import DataValidationError, DatabaseError, AuthError, format_error_response
from app.utils.endpoint_utils import verify_jwt, csrf_protected, set_auth_cookies

logger = logging.getLogger(__name__)

@bp.route("/2fa/setup", methods=["GET"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def setup_2fa():
    two_factor_service = current_app.extensions["app_context"].get_service("two_factor_service")

    try:
        user_id = g.current_user.id if g.current_user else None

        logger.info(
            "Starting 2FA setup",
            extra={
                "event": "auth.2fa.setup.started",
                "user_id": user_id,
            },
        )

        response = two_factor_service.setup(g.db, g.current_user.id)

        g.db.commit()

        logger.info(
            "2FA setup successful",
            extra={
                "event": "auth.2fa.setup.completed",
                "user_id": user_id,
            },
        )

        return jsonify(response), 200

    except AuthError as e:

        logger.warning(
            "2FA setup rejected",
            extra={
                "event": "auth.2fa.setup.auth_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during 2FA setup",
            extra={
                "event": "auth.2fa.setup.database_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:  # Catch unexpected errors

        logger.exception(
            "Unexpected exception during 2FA setup",
            extra={
                "event": "auth.2fa.setup.unexpected_exception",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(AuthError("Failed to setup 2FA"), 500)
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

        logger.warning(
            "2FA setup verification validation failed",
            extra={
                "event": "auth.2fa.setup.validation_error",
                "error": str(e),
            },
        )

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

        logger.info(
            "2FA setup verification started",
            extra={
                "event": "auth.2fa.setup.verification_started",
                "user_id": user_id,
            },
        )

        backup_codes = two_factor_service.verify_setup(
            g.db,
            g.current_user.id,
            code,
        )

        g.db.commit()

        logger.info(
            "2FA setup verification successful",
            extra={
                "event": "auth.2fa.setup.verification_completed",
                "user_id": user_id,
            },
        )

        return jsonify(
            {
                "backup_codes": backup_codes
            }
        ), 200

    except AuthError as e:

        logger.warning(
            "2FA setup verification rejected",
            extra={
                "event": "auth.2fa.setup.auth_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during 2FA setup verification",
            extra={
                "event": "auth.2fa.setup.database_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during 2FA setup verification",
            extra={
                "event": "auth.2fa.setup.unexpected_exception",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

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

        logger.error(
            "Database error retrieving 2FA status",
            extra={
                "event": "auth.2fa.status.database_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception retrieving 2FA status",
            extra={
                "event": "auth.2fa.status.unexpected_exception",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            AuthError("Failed to retrieve 2FA status"),
            500,
        )
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

        logger.info(
            "2FA disabled",
            extra={
                "event": "auth.2fa.disable.success",
                "user_id": g.current_user.id,
            },
        )

        return jsonify(
            {
                "message": "Two-factor authentication disabled."
            }
        ), 200


    except AuthError as e:

        logger.warning(
            "2FA disable rejected",
            extra={
                "event": "auth.2fa.disable.auth_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)


    except DatabaseError as e:

        logger.error(
            "Database error during 2FA disable",
            extra={
                "event": "auth.2fa.disable.database_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during 2FA disable",
            extra={
                "event": "auth.2fa.disable.unexpected_exception",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            AuthError("Failed to disable 2FA"),
            500,
        )
        return make_response(jsonify(error_response), status_code)


@bp.route("/2fa/verify", methods=["POST"])
@csrf_protected
@limiter.limit(limit("10 per minute"))
def verify_two_factor_login():

    try:
        code = request.json.get("code")
        user_id = request.json.get("user_id")   # For initial login (no JWT)

        if not code:
            raise DataValidationError("Missing code")

    except Exception as e:

        logger.warning(
            "2FA login validation failed",
            extra={
                "event": "auth.2fa.login.validation_error",
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            DataValidationError(str(e)),
            400,
        )
        return make_response(jsonify(error_response), status_code)

    two_factor_service = current_app.extensions["app_context"].get_service(
        "two_factor_service"
    )

    try:
        if user_id:

            logger.info(
                "2FA login verification started",
                extra={
                    "event": "auth.2fa.login.started",
                    "user_id": user_id,
                },
            )

            verified = two_factor_service.verify_login(
                g.db,
                int(user_id),
                code,
            )
        else:
            user_id = g.current_user.id if g.current_user else None

            logger.info(
                "2FA login verification started",
                extra={
                    "event": "auth.2fa.login.started",
                    "user_id": user_id,
                },
            )

            verified = two_factor_service.verify_login(
                g.db,
                g.current_user.id,
                code,
            )

        if verified:
            authentication_service = current_app.extensions["app_context"].get_service("authentication_service")
            tokens = authentication_service.issue_token_pair(int(user_id))
            user = authentication_service.user_repo.get_by_id(g.db, user_id)

            logger.info(
                "2FA login successful",
                extra={
                    "event": "auth.2fa.login.success",
                    "user_id": user_id,
                },
            )

            response = make_response(jsonify({
                "verified": True,
                "user": _serialize_user(user) if user else None,
            }), 200)
            set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
            return response
        else:

            logger.warning(
                "Invalid 2FA code",
                extra={
                    "event": "auth.2fa.login.invalid_code",
                    "user_id": user_id,
                },
            )

            error_response, status_code = format_error_response(AuthError("Invalid code"), 400)
            return make_response(jsonify(error_response), status_code)

    except AuthError as e:

        logger.warning(
            "2FA login rejected",
            extra={
                "event": "auth.2fa.login.auth_error",
                "user_id": user_id,
                "error": str(e),
            },
        )
        
        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during 2FA login",
            extra={
                "event": "auth.2fa.login.database_error",
                "user_id": user_id,
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during 2FA login",
            extra={
                "event": "auth.2fa.login.unexpected_exception",
                "user_id": user_id,
                "error": str(e),
            },
        )

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

        logger.info(
            "Backup codes regenerated",
            extra={
                "event": "auth.2fa.backup_codes.regenerated",
                "user_id": g.current_user.id,
            },
        )

        return jsonify(
            {
                "backup_codes": backup_codes,
            }
        ), 200

    except AuthError as e:

        logger.warning(
            "Backup code regeneration rejected",
            extra={
                "event": "auth.2fa.backup_codes.auth_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 400)
        return make_response(jsonify(error_response), status_code)

    except DatabaseError as e:

        logger.error(
            "Database error during backup code regeneration",
            extra={
                "event": "auth.2fa.backup_codes.database_error",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(e, 500)
        return make_response(jsonify(error_response), status_code)

    except Exception as e:

        logger.exception(
            "Unexpected exception during backup code regeneration",
            extra={
                "event": "auth.2fa.backup_codes.unexpected_exception",
                "user_id": getattr(g.current_user, "id", None),
                "error": str(e),
            },
        )

        error_response, status_code = format_error_response(
            AuthError("Failed to regenerate backup codes"),
            500,
        )
        return make_response(jsonify(error_response), status_code)