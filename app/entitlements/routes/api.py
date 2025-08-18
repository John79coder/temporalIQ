# app/entitlements/routes/api.py
import stripe
from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError
from app.entitlements.models.schemas import CreditPackPurchase, UpgradeRequest
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, DatabaseError, make_handled_error_response, AuthError

bp = Blueprint("entitlements", __name__, url_prefix="/entitlements")


@bp.route("/status", methods=["GET"])
@verify_jwt
def get_entitlement_status():
    """Get the current subscription tier and usage status"""
    try:
        service = current_app.extensions['app_context'].get_service('entitlements_service')
        status = service.get_usage_status(g.db, g.current_user.id)
        return jsonify(status.model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/check-quota", methods=["POST"])
@verify_jwt
def check_quota():
    """Check if an action is allowed based on quota"""
    data = request.get_json()
    metric = data.get('metric')
    count = data.get('count', 1)

    if not metric:
        return make_handled_error_response(DataValidationError, "Missing metric", 400)

    try:
        service = current_app.extensions['app_context'].get_service('entitlements_service')
        result = service.check_quota(g.db, g.current_user.id, metric, count)
        return jsonify(result.model_dump()), 200
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/upgrade", methods=["POST"])
@verify_jwt
@csrf_protected
def upgrade_subscription():
    """Upgrade to a higher tier"""
    try:
        data = UpgradeRequest(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        service = current_app.extensions['app_context'].get_service('entitlements_service')
        current_tier = service.get_user_tier(g.db, g.current_user.id)

        if data.target_tier == current_tier:
            return make_handled_error_response(DataValidationError, "Already on this tier", 400)

        # Create Stripe checkout session
        price_key = f"{data.target_tier}_{'annual' if data.annual_billing else 'monthly'}"
        price_id = service.STRIPE_PRICES.get(price_key)

        if not price_id:
            return make_handled_error_response(DataValidationError, "Invalid tier or billing option", 400)

        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{current_app.config['FRONTEND_BASE_URL']}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{current_app.config['FRONTEND_BASE_URL']}/billing/cancel",
            client_reference_id=str(g.current_user.id),
            metadata={
                'user_id': str(g.current_user.id),
                'target_tier': data.target_tier,
                'annual_billing': str(data.annual_billing),
                'previous_tier': current_tier
            }
        )

        return jsonify({'session_id': session.id, 'checkout_url': session.url}), 200

    except stripe.error.StripeError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/purchase-credits", methods=["POST"])
@verify_jwt
@csrf_protected
def purchase_credits():
    """Purchase a credit pack"""
    try:
        # app/entitlements/routes/api.py (continued)
        data = CreditPackPurchase(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

        # Calculate price (e.g., $5 per 1000 AI generation credits)
        price_cents = (data.amount // 1000) * 500  # $5 per 1000

        payment_intent = stripe.PaymentIntent.create(
            amount=price_cents,
            currency='usd',
            metadata={
                'user_id': str(g.current_user.id),
                'credit_type': data.credit_type,
                'credit_amount': str(data.amount)
            }
        )

        return jsonify({
            'client_secret': payment_intent.client_secret,
            'payment_intent_id': payment_intent.id,
            'amount': data.amount,
            'price': price_cents / 100
        }), 200

    except stripe.error.StripeError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)

@bp.route("/stripe-webhook", methods=["POST"])
def handle_stripe_webhook():
    """Handle Stripe webhook events for entitlements"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config["STRIPE_WEBHOOK_SECRET"]
        )
    except ValueError:
        return make_handled_error_response(DataValidationError, "Invalid payload", 400)
    except stripe.error.SignatureVerificationError:
        return make_handled_error_response(AuthError, "Invalid signature", 400)

    service = current_app.extensions['app_context'].get_service('entitlements_service')

    # Handle different event types
    if event["type"] == "checkout.session.completed":
        session = event['data']['object']
        user_id = int(session['client_reference_id'])
        metadata = session.get('metadata', {})

        # Update user's tier
        from app.entitlements.models.entities import SubscriptionTier
        tier = SubscriptionTier(
            user_id=user_id,
            tier=metadata['target_tier'],
            status='active',
            stripe_subscription_id=session['subscription'],
            stripe_customer_id=session['customer'],
            annual_billing=metadata.get('annual_billing', 'false').lower() == 'true'
        )
        service.repository.create_or_update_tier(g.db, tier)

    elif event["type"] == "payment_intent.succeeded":
        payment_intent = event['data']['object']
        metadata = payment_intent.get('metadata', {})

        if 'credit_type' in metadata:
            # Credit pack purchase
            service.purchase_credit_pack(
                g.db,
                int(metadata['user_id']),
                metadata['credit_type'],
                int(metadata['credit_amount']),
                payment_intent['id']
            )

    elif event["type"] == "customer.subscription.deleted":
        subscription = event['data']['object']
        # Find user by stripe subscription ID and downgrade
        from app.entitlements.models.entities import SubscriptionTier
        tier_record = g.db.query(SubscriptionTier).filter_by(
            stripe_subscription_id=subscription['id']
        ).first()

        if tier_record:
            tier_record.tier = 'free'
            tier_record.status = 'canceled'
            service.repository.create_or_update_tier(g.db, tier_record)

    return jsonify(success=True), 200