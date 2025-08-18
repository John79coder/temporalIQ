# app/entitlements/repositories/repository.py
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.repositories.base import AbstractRepository
from app.entitlements.models.entities import SubscriptionTier, UsageMetrics, CreditPack, TeamWorkspace, TeamMembership
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.time_zone import TimeZone


class EntitlementsRepository(AbstractRepository):
    def get_user_tier(self, db: Session, user_id: int) -> Optional[SubscriptionTier]:
        try:
            return db.query(SubscriptionTier).filter_by(user_id=user_id).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve user tier")

    def create_or_update_tier(self, db: Session, tier: SubscriptionTier) -> SubscriptionTier:
        try:
            existing = db.query(SubscriptionTier).filter_by(user_id=tier.user_id).first()
            if existing:
                existing.tier = tier.tier
                existing.status = tier.status
                existing.trial_ends_at = tier.trial_ends_at
                existing.stripe_subscription_id = tier.stripe_subscription_id
                existing.stripe_customer_id = tier.stripe_customer_id
                existing.annual_billing = tier.annual_billing
                existing.updated_at = TimeZone.utc_now()
                db.commit()
                db.refresh(existing)
                return existing
            db.add(tier)
            db.commit()
            db.refresh(tier)
            return tier
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to save subscription tier")

    def get_usage_for_period(self, db: Session, user_id: int, metric_type: str, period_start: datetime) -> Optional[UsageMetrics]:
        try:
            return db.query(UsageMetrics).filter(
                and_(
                    UsageMetrics.user_id == user_id,
                    UsageMetrics.metric_type == metric_type,
                    UsageMetrics.period_start == period_start
                )
            ).first()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve usage metrics")

    def increment_usage(self, db: Session, user_id: int, metric_type: str, count: int, period_start: datetime, period_end: datetime) -> UsageMetrics:
        try:
            usage = self.get_usage_for_period(db, user_id, metric_type, period_start)
            if usage:
                usage.count += count
                usage.updated_at = TimeZone.utc_now()
            else:
                usage = UsageMetrics(
                    user_id=user_id,
                    metric_type=metric_type,
                    count=count,
                    period_start=period_start,
                    period_end=period_end
                )
                db.add(usage)
            db.commit()
            db.refresh(usage)
            return usage
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to increment usage")

    def get_active_credit_packs(self, db: Session, user_id: int, credit_type: str) -> list[type[CreditPack]]:
        try:
            now = TimeZone.utc_now()
            return db.query(CreditPack).filter(
                and_(
                    CreditPack.user_id == user_id,
                    CreditPack.credit_type == credit_type,
                    CreditPack.credits_remaining > 0,
                    or_(CreditPack.expires_at.is_(None), CreditPack.expires_at > now)
                )
            ).order_by(CreditPack.expires_at.asc().nullsfirst()).all()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve credit packs")

    def consume_credits(self, db: Session, pack: CreditPack, amount: int) -> CreditPack:
        try:
            pack.credits_remaining = max(0, pack.credits_remaining - amount)
            pack.updated_at = TimeZone.utc_now()
            db.commit()
            db.refresh(pack)
            return pack
        except Exception as e:
            db.rollback()
            raise wrap_external_error(e, DatabaseError, "Failed to consume credits")

    def get_team_workspace(self, db: Session, user_id: int) -> Optional[TeamWorkspace]:
        try:
            membership = db.query(TeamMembership).filter_by(user_id=user_id).first()
            if membership:
                return db.query(TeamWorkspace).filter_by(id=membership.workspace_id).first()
            return None
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve team workspace")