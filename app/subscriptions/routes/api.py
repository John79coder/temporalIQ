# app/subscriptions/routes/api.py
import stripe
from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError

from app.subscriptions.models.schemas import SubscriptionCreate, SubscriptionOut, SubscriptionUpdate
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, make_handled_error_response, AuthError

bp = Blueprint("subscriptions", __name__, url_prefix="/subscriptions")


@bp.route("/subscribe", methods=["POST"])
@verify_jwt
@csrf_protected
def subscribe():
    try:
        data = SubscriptionCreate(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    if data.user_id != g.current_user.id:
        return make_handled_error_response(AuthError, "Unauthorized", 403)

    try:
        result = current_app.extensions['app_context'].get_service('subscriptions_service').create_subscription(g.db,
                                                                                                                data)
        if data.plan_type == 'premium':
            return jsonify({'session_id': result['session_id']}), 200
        else:
            return jsonify(result), 201
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/status", methods=["GET"])
@verify_jwt
def get_status():
    try:
        sub = current_app.extensions['app_context'].get_service('subscriptions_service').get_subscription(g.db,
                                                                                                          g.current_user.id)
        if not sub:
            return make_handled_error_response(DataValidationError, "Subscription not found", 404)
        return jsonify(SubscriptionOut.model_validate(sub).model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/upgrade", methods=["POST"])
@verify_jwt
@csrf_protected
def upgrade():
    try:
        data = SubscriptionUpdate(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        sub = current_app.extensions['app_context'].get_service('subscriptions_service').update_subscription(g.db,
                                                                                                             g.current_user.id,
                                                                                                             data)
        return jsonify(SubscriptionOut.model_validate(sub).model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/cancel", methods=["POST"])
@verify_jwt
@csrf_protected
def cancel():
    try:
        sub = current_app.extensions['app_context'].get_service('subscriptions_service').get_subscription(g.db,
                                                                                                          g.current_user.id)
        if not sub:
            return make_handled_error_response(DataValidationError, "Subscription not found", 404)
        if sub.plan_type != 'premium':
            return make_handled_error_response(DataValidationError, "No premium subscription to cancel", 400)
        stripe.Subscription.modify(sub.stripe_id, cancel_at_period_end=True)
        update_data = SubscriptionUpdate(status='canceled')
        updated = current_app.extensions['app_context'].get_service('subscriptions_service').update_subscription(g.db,
                                                                                                                 g.current_user.id,
                                                                                                                 update_data)
        return jsonify(SubscriptionOut.model_validate(updated).model_dump()), 200
    except stripe.error.StripeError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    try:
        current_app.extensions['app_context'].get_service('subscriptions_service').handle_webhook(g.db, payload,
                                                                                                  sig_header)
        return jsonify(success=True), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 400)
