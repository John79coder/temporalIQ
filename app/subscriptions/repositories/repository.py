# app/subscriptions/repositories/repository.py
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.base import AbstractRepository
from app.subscriptions.models.entities import UserSubscriptions
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class SubscriptionsRepository(AbstractRepository):
    def create_or_update(self, db: Session, subscription: UserSubscriptions) -> UserSubscriptions:
        try:
            existing = db.query(UserSubscriptions).filter_by(user_id=subscription.user_id).first()
            if existing:
                existing.plan_type = subscription.plan_type
                existing.status = subscription.status
                existing.start_date = subscription.start_date
                existing.end_date = subscription.end_date
                existing.stripe_id = subscription.stripe_id
                existing.updated_at = TimeZone.utc_now()
                db.commit()
                db.refresh(existing)
                return existing
            db.add(subscription)
            db.commit()
            db.refresh(subscription)
            return subscription
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to save subscription")

    def get_by_user(self, db: Session, user_id: int) -> Optional[UserSubscriptions]:
        try:
            return db.query(UserSubscriptions).filter_by(user_id=user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve subscription")

    def get_by_stripe_id(self, db: Session, stripe_id: str) -> Optional[UserSubscriptions]:
        try:
            return db.query(UserSubscriptions).filter_by(stripe_id=stripe_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve subscription by stripe_id")
