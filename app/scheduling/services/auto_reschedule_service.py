# app/scheduling/services/auto_reschedule_service.py
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from celery import Celery
from app.entitlements.services.entitlements_service import EntitlementsService
from app.scheduling.services.time_block_generator import TimeBlockGenerator
from app.utils.logging_service import LoggingService
from app.utils.time_zone import TimeZone


class AutoRescheduleService:
    def __init__(self, entitlements_service: EntitlementsService,
                 time_block_generator: TimeBlockGenerator,
                 logging_service: LoggingService):
        self.entitlements_service = entitlements_service
        self.time_block_generator = time_block_generator
        self.logging_service = logging_service
        self.celery = Celery('tasks', broker='redis://localhost:6379')

    def get_reschedule_frequency(self, db: Session, user_id: int) -> Optional[str]:
        tier = self.entitlements_service.get_user_tier(db, user_id)
        limits = EntitlementsService.TIER_LIMITS.get(tier)
        return limits.auto_reschedule if limits else None

    def schedule_next_run(self, db: Session, user_id: int):
        """Schedule next auto-reschedule based on tier"""
        frequency = self.get_reschedule_frequency(db, user_id)

        if not frequency:
            self.logging_service.info(f"No auto-reschedule for user {user_id} (free tier)")
            return

        # Calculate next run time based on frequency
        now = TimeZone.utc_now()
        if frequency == 'daily':
            next_run = now + timedelta(days=1)
        elif frequency == 'hourly':
            next_run = now + timedelta(hours=2)  # Every 2-4 hours
        elif frequency == 'realtime':
            next_run = now + timedelta(minutes=15)  # Check every 15 minutes
        else:
            return

        # Schedule with Celery
        self.celery.send_task(
            'reschedule_user_tasks',
            args=[user_id],
            eta=next_run
        )

        self.logging_service.info(
            f"Scheduled next auto-reschedule for user {user_id}",
            user_id=user_id,
            extra={
                'frequency': frequency,
                'next_run': next_run.isoformat()
            }
        )

    def can_auto_reschedule(self, db: Session, user_id: int) -> bool:
        """Check if user has auto-reschedule capability"""
        return self.entitlements_service.has_capability(db, user_id, 'auto_reschedule')