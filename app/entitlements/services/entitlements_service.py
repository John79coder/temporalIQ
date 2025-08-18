# app/entitlements/services/entitlements_service.py
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.entitlements.models.entities import SubscriptionTier, CreditPack
from app.entitlements.models.schemas import TierLimits, UsageStatus, QuotaCheckResult
from app.entitlements.repositories.repository import EntitlementsRepository
from app.utils.caching import ICacheService
from app.utils.time_zone import TimeZone
from app.utils.logging_service import LoggingService


class EntitlementsService:
    # Tier configuration
    TIER_LIMITS = {
        'free': TierLimits(
            ai_generations=100,
            calendar_writes=0,
            calendars=2,
            notion_databases=1,
            auto_reschedule=None,
            priority_queue=False,
            webhook_access=False,
            api_access=False
        ),
        'starter': TierLimits(
            ai_generations=500,
            calendar_writes=50,
            calendars=3,
            notion_databases=3,
            auto_reschedule='daily',
            priority_queue=False,
            webhook_access=False,
            api_access=False
        ),
        'pro': TierLimits(
            ai_generations=2000,
            calendar_writes=500,
            calendars=5,
            notion_databases=-1,  # unlimited
            auto_reschedule='hourly',
            priority_queue=True,
            webhook_access=True,
            api_access=True
        ),
        'business': TierLimits(
            ai_generations=-1,  # unlimited
            calendar_writes=-1,
            calendars=-1,
            notion_databases=-1,
            auto_reschedule='realtime',
            priority_queue=True,
            webhook_access=True,
            api_access=True
        )
    }

    # Stripe price IDs for each tier
    STRIPE_PRICES = {
        'starter_monthly': 'price_starter_monthly',
        'starter_annual': 'price_starter_annual',
        'pro_monthly': 'price_pro_monthly',
        'pro_annual': 'price_pro_annual',
        'business_monthly': 'price_business_monthly',
        'business_annual': 'price_business_annual',
    }

    def __init__(self, repository: EntitlementsRepository, caching_service: ICacheService,
                 logging_service: LoggingService):
        self.repository = repository
        self.caching_service = caching_service
        self.logging_service = logging_service

    def get_user_tier(self, db: Session, user_id: int) -> str:
        """Get the current tier for a user, handling trials"""
        cache_key = f"entitlements:tier:{user_id}"
        cached_tier = self.caching_service.get(cache_key)
        if cached_tier:
            return cached_tier

        tier_record = self.repository.get_user_tier(db, user_id)

        if not tier_record:
            # New user - start with free tier
            return 'free'

        # Check if trial is active
        if tier_record.status == 'trial' and tier_record.trial_ends_at:
            if TimeZone.utc_now() < tier_record.trial_ends_at:
                tier = tier_record.tier
            else:
                # Trial expired, downgrade to free
                tier = 'free'
                tier_record.status = 'expired'
                tier_record.tier = 'free'
                self.repository.create_or_update_tier(db, tier_record)
        else:
            tier = tier_record.tier

        self.caching_service.set(cache_key, tier, timeout=300)  # 5 minutes
        return tier

    def has_capability(self, db: Session, user_id: int, capability: str) -> bool:
        """Check if user has access to a specific capability"""
        tier = self.get_user_tier(db, user_id)
        limits = self.TIER_LIMITS.get(tier)

        if not limits:
            return False

        capability_map = {
            'calendar_write': limits.calendar_writes != 0,
            'auto_reschedule': limits.auto_reschedule is not None,
            'webhook_access': limits.webhook_access,
            'api_access': limits.api_access,
            'priority_queue': limits.priority_queue,
            'advanced_notion_sync': tier in ['pro', 'business'],
            'team_features': tier == 'business',
        }

        return capability_map.get(capability, False)

    def check_quota(self, db: Session, user_id: int, metric: str, count: int = 1) -> QuotaCheckResult:
        """Check if user has remaining quota for a metric"""
        tier = self.get_user_tier(db, user_id)
        limits = self.TIER_LIMITS.get(tier)

        if not limits:
            return QuotaCheckResult(allowed=False, remaining=0, limit=0, reset_date=self._get_period_end())

        limit = getattr(limits, metric, 0)

        # Unlimited (-1) always allows
        if limit == -1:
            return QuotaCheckResult(
                allowed=True,
                remaining=-1,
                limit=-1,
                reset_date=self._get_period_end()
            )

        # No access (0) always denies
        if limit == 0:
            return QuotaCheckResult(
                allowed=False,
                remaining=0,
                limit=0,
                reset_date=self._get_period_end(),
                upgrade_options=self._get_upgrade_options_for_metric(metric, tier)
            )

        # Check current usage
        period_start = self._get_period_start()
        usage = self.repository.get_usage_for_period(db, user_id, metric, period_start)
        current_count = usage.count if usage else 0

        # Check credit packs
        credit_pack_credits = self._get_available_credits(db, user_id, metric)
        total_available = limit - current_count + credit_pack_credits

        allowed = total_available >= count

        return QuotaCheckResult(
            allowed=allowed,
            remaining=max(0, total_available),
            limit=limit,
            reset_date=self._get_period_end(),
            upgrade_options=self._get_upgrade_options_for_metric(metric, tier) if not allowed else None,
            credit_pack_available=metric in ['ai_generations', 'calendar_writes']
        )

    def increment_usage(self, db: Session, user_id: int, metric: str, count: int = 1) -> Tuple[bool, Optional[str]]:
        """Increment usage counter, using credit packs if needed"""
        tier = self.get_user_tier(db, user_id)
        limits = self.TIER_LIMITS.get(tier)

        if not limits:
            return False, "Invalid tier"

        limit = getattr(limits, metric, 0)

        # Unlimited usage
        if limit == -1:
            return True, None

        period_start = self._get_period_start()
        period_end = self._get_period_end()

        # First, try to use regular quota
        usage = self.repository.get_usage_for_period(db, user_id, metric, period_start)
        current_count = usage.count if usage else 0

        remaining_quota = limit - current_count
        to_charge_quota = min(count, remaining_quota) if remaining_quota > 0 else 0
        to_charge_credits = count - to_charge_quota

        # Increment regular usage if any
        if to_charge_quota > 0:
            self.repository.increment_usage(db, user_id, metric, to_charge_quota, period_start, period_end)

        # Use credit packs for overflow
        if to_charge_credits > 0:
            credits_consumed = self._consume_credits(db, user_id, metric, to_charge_credits)
            if credits_consumed < to_charge_credits:
                return False, f"Insufficient quota and credits (needed {to_charge_credits}, had {credits_consumed})"

        # Clear cache
        self.caching_service.delete(f"entitlements:usage:{user_id}:{metric}")

        # Log usage for analytics
        self.logging_service.info(
            f"Usage incremented",
            user_id=user_id,
            extra={
                'metric': metric,
                'count': count,
                'tier': tier,
                'from_quota': to_charge_quota,
                'from_credits': to_charge_credits
            }
        )

        return True, None

    def start_reverse_trial(self, db: Session, user_id: int, tier: str = 'pro', days: int = 14) -> SubscriptionTier:
        """Start a reverse trial for a new user"""
        trial_ends_at = TimeZone.utc_now() + timedelta(days=days)

        tier_record = SubscriptionTier(
            user_id=user_id,
            tier=tier,
            status='trial',
            trial_ends_at=trial_ends_at
        )

        saved = self.repository.create_or_update_tier(db, tier_record)

        # Clear cache
        self.caching_service.delete(f"entitlements:tier:{user_id}")

        self.logging_service.info(
            f"Started {days}-day {tier} trial",
            user_id=user_id
        )

        return saved

    def get_usage_status(self, db: Session, user_id: int) -> UsageStatus:
        """Get comprehensive usage status for a user"""
        tier = self.get_user_tier(db, user_id)
        tier_record = self.repository.get_user_tier(db, user_id)
        limits = self.TIER_LIMITS.get(tier)

        # Gather usage for all metrics
        usage_data = {}
        period_start = self._get_period_start()

        for metric in ['ai_generations', 'calendar_writes']:
            usage = self.repository.get_usage_for_period(db, user_id, metric, period_start)
            current_count = usage.count if usage else 0
            limit = getattr(limits, metric, 0)
            credits = self._get_available_credits(db, user_id, metric)

            usage_data[metric] = {
                'used': current_count,
                'limit': limit,
                'credits': credits,
                'reset_date': TimeZone.serialize_datetime(self._get_period_end())
            }

        # Get capabilities
        capabilities = []
        for cap in ['calendar_write', 'auto_reschedule', 'webhook_access', 'api_access', 'advanced_notion_sync']:
            if self.has_capability(db, user_id, cap):
                capabilities.append(cap)

        return UsageStatus(
            tier=tier,
            status=tier_record.status if tier_record else 'active',
            trial_ends_at=tier_record.trial_ends_at if tier_record else None,
            usage=usage_data,
            capabilities=capabilities,
            upgrade_options=self._get_tier_upgrade_options(tier)
        )

    def purchase_credit_pack(self, db: Session, user_id: int, credit_type: str, amount: int,
                             stripe_payment_intent_id: str) -> CreditPack:
        """Record a credit pack purchase"""
        expires_at = TimeZone.utc_now() + timedelta(days=90)  # 90 day expiry

        pack = CreditPack(
            user_id=user_id,
            credit_type=credit_type,
            credits_purchased=amount,
            credits_remaining=amount,
            expires_at=expires_at,
            stripe_payment_intent_id=stripe_payment_intent_id
        )

        db.add(pack)
        db.commit()
        db.refresh(pack)

        self.logging_service.info(
            f"Credit pack purchased",
            user_id=user_id,
            extra={
                'credit_type': credit_type,
                'amount': amount,
                'payment_intent': stripe_payment_intent_id
            }
        )

        return pack

    # Private helper methods
    def _get_period_start(self) -> datetime:
        """Get the start of the current billing period (month)"""
        now = TimeZone.utc_now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _get_period_end(self) -> datetime:
        """Get the end of the current billing period"""
        start = self._get_period_start()
        # Next month, same day
        if start.month == 12:
            return start.replace(year=start.year + 1, month=1)
        return start.replace(month=start.month + 1)

    def _get_available_credits(self, db: Session, user_id: int, metric: str) -> int:
        """Get total available credits from credit packs"""
        packs = self.repository.get_active_credit_packs(db, user_id, metric)
        return sum(pack.credits_remaining for pack in packs)

    def _consume_credits(self, db: Session, user_id: int, metric: str, amount: int) -> int:
        """Consume credits from credit packs, return amount consumed"""
        packs = self.repository.get_active_credit_packs(db, user_id, metric)
        consumed = 0

        for pack in packs:
            if consumed >= amount:
                break

            to_consume = min(pack.credits_remaining, amount - consumed)
            self.repository.consume_credits(db, pack, to_consume)
            consumed += to_consume

        return consumed

    def _get_upgrade_options_for_metric(self, metric: str, current_tier: str) -> List[str]:
        """Get upgrade options for a specific metric"""
        options = []
        tier_order = ['free', 'starter', 'pro', 'business']
        current_index = tier_order.index(current_tier)

        for tier in tier_order[current_index + 1:]:
            limits = self.TIER_LIMITS[tier]
            if getattr(limits, metric, 0) > getattr(self.TIER_LIMITS[current_tier], metric, 0):
                options.append(tier)

        return options

    def _get_tier_upgrade_options(self, current_tier: str) -> List[str]:
        """Get all available upgrade tiers"""
        tier_order = ['free', 'starter', 'pro', 'business']
        current_index = tier_order.index(current_tier)
        return tier_order[current_index + 1:]