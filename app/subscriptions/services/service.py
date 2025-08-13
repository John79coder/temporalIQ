# app/subscriptions/services/service.py
from datetime import datetime
from typing import Optional

import stripe
from flask import current_app
from sqlalchemy.orm import Session

from app.subscriptions.models.entities import UserSubscriptions
from app.subscriptions.models.schemas import SubscriptionCreate, SubscriptionOut, SubscriptionUpdate
from app.subscriptions.repositories.repository import SubscriptionsRepository
from app.utils.caching import ICacheService
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class SubscriptionsService:
    def __init__(self, repo: SubscriptionsRepository, caching_service: ICacheService):
        self.subscriptions_repo = repo
        self.caching_service = caching_service
        self.stripe_api_key = None

    def initialize_stripe(self):
        """Initialize Stripe API key within an application context."""
        self.stripe_api_key = current_app.config["STRIPE_SECRET_KEY"]
        stripe.api_key = self.stripe_api_key

    def create_subscription(self, db: Session, sub_data: SubscriptionCreate) -> dict:
        self.initialize_stripe()  # Ensure Stripe is initialized
        if sub_data.plan_type == 'premium':
            try:
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price': current_app.config["STRIPE_PRICE_ID_PREMIUM"],
                        'quantity': 1,
                    }],
                    mode='subscription',
                    success_url='http://localhost:5000/success?session_id={CHECKOUT_SESSION_ID}',
                    cancel_url='http://localhost:5000/cancel',
                )
                subscription = UserSubscriptions(
                    user_id=sub_data.user_id,
                    plan_type=sub_data.plan_type,
                    status='pending',
                    start_date=TimeZone.utc_now(),
                    stripe_id=session.id  # Session id temporarily
                )
                saved = self.subscriptions_repo.create_or_update(db, subscription)
                self._cache_subscription(saved.user_id, saved)
                return {'session_id': session.id}
            except stripe.error.StripeError as e:
                raise wrap_external_error(e, DatabaseError, "Stripe error creating session")
        else:
            subscription = UserSubscriptions(
                user_id=sub_data.user_id,
                plan_type=sub_data.plan_type,
                status='active',
                start_date=TimeZone.utc_now(),
                stripe_id=sub_data.stripe_id
            )
            try:
                saved = self.subscriptions_repo.create_or_update(db, subscription)
                self._cache_subscription(saved.user_id, saved)
                return SubscriptionOut.model_validate(saved).model_dump()
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to create subscription")

    def update_subscription(self, db: Session, user_id: int, update_data: SubscriptionUpdate) -> UserSubscriptions:
        subscription = self.get_subscription(db, user_id)
        if not subscription:
            raise DatabaseError("Subscription not found")
        if update_data.plan_type:
            subscription.plan_type = update_data.plan_type
        if update_data.status:
            subscription.status = update_data.status
        if update_data.end_date:
            subscription.end_date = update_data.end_date
        if update_data.stripe_id:
            subscription.stripe_id = update_data.stripe_id
        try:
            saved = self.subscriptions_repo.create_or_update(db, subscription)
            self._cache_subscription(saved.user_id, saved)
            return saved
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to update subscription")

    def get_subscription(self, db: Session, user_id: int) -> Optional[UserSubscriptions]:
        cache_key = f"subscriptions:{user_id}"
        cached = self.caching_service.get(cache_key)
        if cached:
            return UserSubscriptions(**cached)
        try:
            sub = self.subscriptions_repo.get_by_user(db, user_id)
            if sub:
                self._cache_subscription(user_id, sub)
            return sub
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get subscription")

    def is_premium(self, db: Session, user_id: int) -> bool:
        sub = self.get_subscription(db, user_id)
        return sub and sub.plan_type == 'premium' and sub.status == 'active'

    def _cache_subscription(self, user_id: int, sub: UserSubscriptions):
        self.caching_service.set(
            f"subscriptions:{user_id}",
            sub.__dict__,
            timeout=86400  # 1 day
        )

    def handle_webhook(self, db: Session, payload, sig_header):
        self.initialize_stripe()  # Ensure Stripe is initialized
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, current_app.config["STRIPE_WEBHOOK_SECRET"]
            )
        except ValueError:
            raise DatabaseError("Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise DatabaseError("Invalid signature")
        if event["type"] == "checkout.session.completed":
            session = event['data']['object']
            customer_id = session['customer']
            subscription_id = session['subscription']
            sub = self.subscriptions_repo.get_by_stripe_id(db, session['id'])  # Add repo method if needed
            if sub:
                sub.stripe_id = subscription_id
                sub.status = 'active'
                self.subscriptions_repo.create_or_update(db, sub)
        elif event["type"] == "invoice.payment_succeeded":
            subscription_id = event['data']['object']['subscription']
            sub = self.subscriptions_repo.get_by_stripe_id(db, subscription_id)
            if sub:
                sub.status = 'active'
                self.subscriptions_repo.create_or_update(db, sub)
        elif event["type"] == "invoice.payment_failed":
            subscription_id = event['data']['object']['subscription']
            sub = self.subscriptions_repo.get_by_stripe_id(db, subscription_id)
            if sub:
                sub.status = 'past_due'
                self.subscriptions_repo.create_or_update(db, sub)
        elif event["type"] == "customer.subscription.updated":
            subscription = event['data']['object']
            sub = self.subscriptions_repo.get_by_stripe_id(db, subscription['id'])
            if sub:
                sub.plan_type = subscription['items']['data'][0]['plan']['id']  # Assume single item
                sub.status = subscription['status']
                sub.end_date = datetime.fromtimestamp(subscription['current_period_end']) if subscription[
                    'cancel_at_period_end'] else None
                self.subscriptions_repo.create_or_update(db, sub)
        elif event["type"] == "customer.subscription.deleted":
            subscription_id = event['data']['object']['id']
            sub = self.subscriptions_repo.get_by_stripe_id(db, subscription_id)
            if sub:
                sub.status = 'canceled'
                sub.end_date = TimeZone.utc_now()
                self.subscriptions_repo.create_or_update(db, sub)
        return True
